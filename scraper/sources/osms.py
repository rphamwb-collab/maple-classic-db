"""Read game data from the OSMS Data Explorer datamine.

OSMS (https://osmsdataexplorer.com, GitHub: ohmi69/osms_datamine_dashboard)
extracts its data straight from the MapleStory Classic game client.
We keep a copy of the JSON files we need in data/raw/osms/.

To refresh them after a game patch:
    git clone --depth 1 https://github.com/ohmi69/osms_datamine_dashboard.git <somewhere>
    then copy data/current/{items,monsters,maps,lookups,overview,crafting,quests}.json into data/raw/osms/

This module only READS those files and turns them into plain dicts that
match our tables (see docs/data-contract.md). It does not touch the database.
"""
import json
import re
from pathlib import Path

RAW_DIR = Path(__file__).resolve().parents[2] / "data" / "raw" / "osms"

SOURCE_NAME = "OSMS Data Explorer"
SOURCE_URL = "https://osmsdataexplorer.com/"

# OSMS category -> our category (equip / use / etc / setup)
CATEGORY_MAP = {"Equipment": "equip", "Consumable": "use", "Etc": "etc", "Setup": "setup"}

# OSMS stat key -> our lowercase snake_case stat key
STAT_KEY_MAP = {
    "incSTR": "str", "incDEX": "dex", "incINT": "int", "incLUK": "luk",
    "incMHP": "hp", "incMMP": "mp",
    "incPAD": "weapon_attack", "incMAD": "magic_attack",
    "incPDD": "weapon_def", "incMDD": "magic_def",
    "incACC": "accuracy", "incEVA": "avoid",
    "incSpeed": "speed", "incJump": "jump",
    "incCRT": "crit_rate", "incCRD": "crit_damage",
    "tuc": "slots", "attackSpeed": "attack_speed",
    "reqSTR": "req_str", "reqDEX": "req_dex", "reqINT": "req_int", "reqLUK": "req_luk",
    "reqPOP": "req_fame", "slotMax": "max_stack",
}


# OSMS sub_category values that are equipment slots (kept exactly, e.g. "Hat")
EQUIP_SLOTS = {"Hat", "Top", "Bottom", "Overall", "Shoes", "Glove", "Shield", "Cape", "Earring", "Weapon"}

# Class names in the order we always list them
CLASS_ORDER = ["Warrior", "Magician", "Bowman", "Thief"]


def _load(name: str):
    return json.loads((RAW_DIR / name).read_text(encoding="utf-8"))


def parse_jobs(label: str | None) -> list[str]:
    """'Warrior/Thief' -> ['Warrior', 'Thief'];  'All' or missing -> []  (= any class).
    OSMS says 'Mage'; we use the in-game class name 'Magician'."""
    if not label or label == "All":
        return []
    found = {"Magician" if part.strip() == "Mage" else part.strip() for part in label.split("/")}
    return [c for c in CLASS_ORDER if c in found]


def category_from_id(item_id: int) -> str:
    """Game item IDs start with a digit that tells the inventory tab."""
    return {1: "equip", 2: "use", 3: "setup", 4: "etc"}.get(item_id // 1_000_000, "etc")


def _convert_stats(raw_stats: dict, spec: dict | None) -> dict | None:
    stats = {}
    for key, value in (raw_stats or {}).items():
        new_key = STAT_KEY_MAP.get(key)
        if new_key and isinstance(value, (int, float)) and value:
            stats[new_key] = int(value)
    # "spec" holds potion effects, e.g. {"hp": 100}
    for key, value in (spec or {}).items():
        if key in ("hp", "mp") and isinstance(value, (int, float)):
            stats["heal_" + key] = int(value)
    return stats or None


def load_items() -> list[dict]:
    """All items + scrolls, shaped like our `items` table."""
    data = _load("items.json")
    items: dict[int, dict] = {}

    for it in data["items"]:
        raw_stats = it.get("stats") or {}
        job = it.get("req_job_label")
        slot = it.get("sub_category") if it["category"] == "Equipment" else None
        slot = slot if slot in EQUIP_SLOTS else None
        items[it["id"]] = {
            "id": it["id"],
            "name": it["name"],
            "category": CATEGORY_MAP.get(it["category"], category_from_id(it["id"])),
            "sub_type": it.get("weapon_type") or it.get("sub_category"),
            "level_req": raw_stats.get("reqLevel") or None,
            "job": "Any" if job == "All" else job,
            "stats": _convert_stats(raw_stats, it.get("spec")),
            "description": it.get("description"),
            # what an NPC pays you when you sell it
            "npc_sell_price": it.get("price") or raw_stats.get("price"),
            "equip_slot": slot,
            "weapon_type": it.get("weapon_type") if slot == "Weapon" else None,
            "jobs": parse_jobs(job) if slot else [],
        }

    for sc in data["scrolls"]:
        desc = sc.get("description") or ""
        stats = {}
        rate = re.search(r"Success rate:\s*(\d+)%", desc)
        if rate:
            stats["success_rate"] = int(rate.group(1))
        bonus = re.search(r",\s*([A-Za-z .]+?)\s*\+(\d+)", desc)
        if bonus:
            stats[bonus.group(1).strip().lower().replace(" ", "_").replace(".", "")] = int(bonus.group(2))
        items.setdefault(sc["id"], {
            "id": sc["id"],
            "name": sc["name"],
            "category": "use",
            "sub_type": "Scroll",
            "level_req": None,
            "job": None,
            "stats": stats or None,
            "description": desc or None,
            # OSMS scroll entries have no price field (checked 2026-10-12), so this stays
            # None = "unknown" unless MapleStory Quest has one (see run.py). Never guess.
            "npc_sell_price": None,
            "equip_slot": None,
            "weapon_type": None,
            "jobs": [],
        })
    return list(items.values())


def basic_item(item_id: int, name: str) -> dict:
    """A bare-bones item row for IDs that only appear in the client's name list."""
    return {"id": item_id, "name": name, "category": category_from_id(item_id), "sub_type": None,
            "level_req": None, "job": None, "stats": None, "description": None, "npc_sell_price": None,
            "equip_slot": None, "weapon_type": None, "jobs": []}


def scroll_ids() -> list[int]:
    return [sc["id"] for sc in _load("items.json")["scrolls"]]


def _name_key(name: str) -> str:
    """Compare names loosely: lowercase, single spaces."""
    return " ".join(name.lower().split())


def name_to_id_lookup(preferred_ids: set[int]) -> dict[str, int]:
    """Item name -> item ID, using the client's full name list.
    If several IDs share a name, prefer one that is in `preferred_ids` (our items table)."""
    best: dict[str, int] = {}
    for item_id, name in item_name_lookup().items():
        key = _name_key(name)
        current = best.get(key)
        if current is None:
            best[key] = item_id
        elif item_id in preferred_ids and current not in preferred_ids:
            best[key] = item_id
        elif (item_id in preferred_ids) == (current in preferred_ids) and item_id < current:
            best[key] = item_id  # tie: lowest ID, so results are repeatable
    return best


def load_recipes(name_to_id: dict[str, int]) -> tuple[list[dict], list[str]]:
    """Crafting recipes from crafting.json.
    Returns (recipes, unmatched ingredient names). Each recipe has an 'ingredients' list."""
    data = _load("crafting.json")
    recipes, unmatched = [], set()
    for disc in data["disciplines"]:
        for output_type in disc["output_types"]:
            for level in output_type["levels"]:
                for r in level["recipes"]:
                    ingredients = []
                    for ing in r.get("ingredients") or []:
                        item_id = name_to_id.get(_name_key(ing["item_name"]))
                        if item_id is None:
                            unmatched.add(ing["item_name"])
                        ingredients.append({"item_id": item_id, "item_name": ing["item_name"],
                                            "count": ing.get("count") or 1})
                    recipes.append({
                        "id": r["id"],
                        "output_item_id": r["output_id"],
                        "result_count": r.get("result_count") or 1,
                        "discipline": disc["discipline"],
                        "discipline_level": level["level"],
                        "req_level": r.get("req_level"),
                        "craft_exp": r.get("craft_exp"),
                        "meso_cost": r.get("meso_cost"),
                        "ingredients": ingredients,
                    })
    return recipes, sorted(unmatched)


def load_quest_rewards() -> list[dict]:
    """Item rewards from quests.json, one dict per (quest, item, class).

    OSMS stores rewards in two places:
    - quest["rewards"]: entries with type "item". guaranteed=True means you always get it;
      guaranteed=False means it's one of a weighted random pool.
    - quest["reward_choices"]: "choose one" groups (the player picks).
    """
    data = _load("quests.json")
    rows: dict[tuple, dict] = {}
    for q in data["quests"]:
        base = {"quest_id": int(q["id"]), "quest_name": q["name"], "npc_name": q.get("npc_name"),
                "region": q.get("region"), "level_min": q.get("level_min")}

        def add(item_id, count, reward_type, job):
            key = (base["quest_id"], item_id, job)
            rows.setdefault(key, {**base, "item_id": item_id, "count": count or 1,
                                  "reward_type": reward_type, "job": job})

        # Choices first: the same items also appear in "rewards" (with prop -1),
        # and we want them labelled "choice", not "random".
        for choice in q.get("reward_choices") or []:
            for group in choice.get("groups") or []:
                job = group.get("job_name")
                for it in group.get("items") or []:
                    add(it["id"], it.get("count"), "choice", None if job in (None, "Any Class") else job)
        for r in q.get("rewards") or []:
            if r.get("type") == "item" and r.get("id"):
                job = r.get("job_name")
                add(r["id"], r.get("count"), "guaranteed" if r.get("guaranteed") else "random",
                    None if job in (None, "Any Class") else job)
    return list(rows.values())


def load_monsters() -> list[dict]:
    data = _load("monsters.json")
    return [
        {
            "id": m["id"],
            "name": m["name"],
            "level": m.get("level"),
            "hp": m.get("hp"),
            "exp": m.get("exp"),
            "maps": [mp["name"] for mp in m.get("maps", [])] or None,
        }
        for m in data["monsters"]
    ]


def load_monster_maps() -> list[dict]:
    """Where each monster spawns, by Classic map ID: [{monster_id, map_id, spawn_count}].
    (load_monsters keeps only the names; names repeat, so IDs are needed for the world map.)
    If a monster lists the same map twice, the counts are added together."""
    rows: dict[tuple[int, int], dict] = {}
    for m in _load("monsters.json")["monsters"]:
        for mp in m.get("maps") or []:
            if mp.get("id") is None:
                continue
            key = (m["id"], int(mp["id"]))
            row = rows.setdefault(key, {"monster_id": key[0], "map_id": key[1], "spawn_count": None})
            if mp.get("count") is not None:
                row["spawn_count"] = (row["spawn_count"] or 0) + int(mp["count"])
    return list(rows.values())


def load_npc_maps() -> list[dict]:
    """Which maps each NPC stands on: [{npc_id, map_id}] (from maps.json `npcs`)."""
    pairs = set()
    for region in _load("maps.json")["regions"]:
        for mp in region["maps"]:
            for npc_id in mp.get("npcs") or []:
                pairs.add((int(npc_id), mp["id"]))
    return [{"npc_id": n, "map_id": m} for n, m in sorted(pairs)]


def load_npcs() -> list[dict]:
    """NPC names come from maps.json; we also record the first map/town they stand in."""
    data = _load("maps.json")
    where: dict[int, tuple[str, str]] = {}
    for region in data["regions"]:
        for mp in region["maps"]:
            for npc_id in mp.get("npcs") or []:
                where.setdefault(int(npc_id), (mp.get("map_mark") or region["region"], mp["name"]))

    npcs = []
    for npc_id, info in data["npc_lookup"].items():
        town, map_name = where.get(int(npc_id), (None, None))
        npcs.append({"id": int(npc_id), "name": info["name"], "town": _nice_town(town), "map_name": map_name})
    return npcs


def _nice_town(mark: str | None) -> str | None:
    """'KerningCity' -> 'Kerning City'."""
    if not mark:
        return None
    return re.sub(r"(?<=[a-z])(?=[A-Z])", " ", mark)


def item_name_lookup() -> dict[int, str]:
    """Every item ID the client knows -> name (used to fill gaps)."""
    return {int(k): v for k, v in _load("lookups.json")["item_names"].items()}
