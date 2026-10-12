"""Browse pages: the monster list (GET /monsters), NPC shops grouped by town
(GET /shops), and the counts on the home page.
"""

from collections import defaultdict
from pathlib import Path
from urllib.parse import urlencode

from sqlalchemy import func, select

from app.models import Drop, Item, Monster, Npc, ShopItem
from app.services.filters import in_level_range, level_range_value, level_ranges, parse_level
from app.services.queries import npc_ref, visible_monsters

NO_TOWN = "Other"  # heading for NPCs without a town


# ---------- home ----------

def home_counts(db):
    """{items, monsters, shops}. A "shop" is an NPC that sells at least 1 item.
    Test/unreleased (hidden) monsters are not counted."""
    return {
        "items": db.scalar(select(func.count()).select_from(Item)),
        "monsters": db.scalar(visible_monsters(select(func.count()).select_from(Monster))),
        "shops": db.scalar(select(func.count(func.distinct(ShopItem.npc_id)))),
    }


# ---------- monsters ----------

def monsters_url(level):
    return "/monsters" + ("?" + urlencode({"level": level}) if level else "")


def lowest_level_monster(monsters):
    """Picture for a level button: the lowest-level monster in it."""
    if not monsters:
        return None
    return min(monsters, key=lambda m: (m["level"] or 0, m["id"]))["id"]


def monster_level_option(monsters, label, value, active):
    matching = [m for m in monsters if in_level_range(m["level"], value)]
    return {
        "label": label,
        "value": value,
        "count": len(matching),
        "icon_item_id": None,  # monsters use icon_monster_id instead
        "icon_monster_id": lowest_level_monster(matching),
        "active": active,
        "url": monsters_url(value),
    }


def browse_monsters(db, level=""):
    """Every template variable for GET /monsters."""
    if parse_level(level or "") is None:
        level = ""

    # How many items each monster drops, in one query.
    drop_counts = dict(db.execute(
        select(Drop.monster_id, func.count()).group_by(Drop.monster_id)
    ).all())

    monsters = [
        {"id": m.id, "name": m.name, "level": m.level, "hp": m.hp, "exp": m.exp,
         "maps": m.maps or [], "drop_count": drop_counts.get(m.id, 0)}
        for m in db.scalars(visible_monsters(select(Monster)))  # skips test/unreleased mobs
    ]
    monsters.sort(key=lambda m: (m["level"] or 0, m["name"]))

    # Level buttons: "All levels" first, then ranges that have monsters.
    options = [monster_level_option(monsters, "All levels", "", level == "")]
    max_level = max((m["level"] or 0 for m in monsters), default=0)
    for lo, hi in level_ranges(max_level):
        value = level_range_value(lo, hi)
        option = monster_level_option(monsters, f"Lv. {lo}-{hi}", value, level == value)
        if option["count"] > 0:
            options.append(option)

    shown = [m for m in monsters if in_level_range(m["level"], level)]
    return {
        "monsters": shown,
        "level_options": options,
        "filters": {"level": level},
        "total": len(shown),
    }


def home_monster_field(db, per_band=1):
    """Monsters for the home page "Hunt monsters" field: the lowest-level monster
    of each level band, so the row climbs from Snail upward.

    Returns {total, bands: [{label, url, monster: {id, name, level}}]}.
    Only monsters with a sprite file are picked, so the field never shows placeholders.
    """
    sprite_dir = Path(__file__).resolve().parents[1] / "static" / "img" / "monsters"
    monsters = [{"id": m.id, "name": m.name, "level": m.level or 0}
                for m in db.scalars(visible_monsters(select(Monster)))]  # no test/unreleased mobs
    total = len(monsters)
    monsters = [m for m in monsters if not m["name"].startswith("Tutorial")]  # not real hunting mobs
    with_art = [m for m in monsters if (sprite_dir / f"{m['id']}.webp").exists()] or monsters
    bands = []
    max_level = max((m["level"] for m in with_art), default=0)
    for lo, hi in level_ranges(max_level):
        in_band = sorted((m for m in with_art if lo <= m["level"] <= hi), key=lambda m: (m["level"], m["id"]))
        if in_band:
            value = level_range_value(lo, hi)
            bands.append({"label": f"Lv. {lo}-{hi}", "url": monsters_url(value), "monster": in_band[0]})
    return {"total": total, "bands": bands}


# ---------- shops ----------

def shops_by_town(db):
    """Every template variable for GET /shops: NPC shops grouped by town."""
    item_counts = dict(db.execute(
        select(ShopItem.npc_id, func.count()).group_by(ShopItem.npc_id)
    ).all())
    npcs = db.scalars(select(Npc).where(Npc.id.in_(item_counts.keys()))).all()

    by_town = defaultdict(list)
    for npc in npcs:
        # Some scraped rows say "None" as text; treat that like a missing town.
        town = npc.town if npc.town and npc.town != "None" else NO_TOWN
        by_town[town].append({"npc": npc_ref(npc), "item_count": item_counts[npc.id]})

    # Towns A-Z with "Other" last; shops A-Z inside each town.
    town_names = sorted(by_town, key=lambda t: (t == NO_TOWN, t))
    towns = [
        {"town": t,
         "shop_count": len(by_town[t]),
         "shops": sorted(by_town[t], key=lambda s: s["npc"]["name"])}
        for t in town_names
    ]
    return {"towns": towns, "total_shops": len(npcs)}
