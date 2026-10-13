"""Load REAL game data into data/maple.db.

    .venv\\Scripts\\python -m scraper.run              # OSMS + MapleStory Quest pages from data/cache/ ONLY
                                                 # (never goes online; uncached pages are skipped)
    .venv\\Scripts\\python -m scraper.run --no-scrape  # OSMS only (no drops/shops/scroll prices)
    .venv\\Scripts\\python -m scraper.run --online     # ALSO download uncached MSQ pages (~18 min if
                                                 # the cache is empty). Only when you mean to.

What it does:
1. Rebuilds every table from scratch, EXCEPT price_reports and drop_reports
   (players' reports are kept through a data refresh).
2. Loads items, scrolls, monsters, NPCs, crafting recipes and quest rewards from the
   OSMS datamine (data/raw/osms/).
3. Scrapes drop tables, NPC shops and scroll NPC prices from MapleStory Quest
   (cached in data/cache/, so re-running is fast and doesn't hit the site again).
4. Loads maps (with world map spots from the maplestory.io cache in data/raw/worldmap/,
   made by `python -m scraper.world_map`), plus which maps each monster / NPC is on.
5. Records where OSMS and MapleStory Quest disagree in the audit_findings table
   (see `python -m scraper.audit` for a readable report).

To go back to fake sample data instead: .venv\\Scripts\\python -m scraper.seed_sample
"""
import argparse
from datetime import datetime, timezone
from pathlib import Path

from sqlalchemy import text

from app.db import SessionLocal, engine
from app.models import (AuditFinding, Base, Drop, Item, Map, Monster, MonsterMap, Npc, NpcMap,
                        QuestReward, Recipe, RecipeIngredient, ShopItem, Source)
from scraper import corrections, world_map
from scraper.sources import msquest, osms


def now() -> datetime:
    return datetime.now(timezone.utc).replace(tzinfo=None)


def apply_shop_corrections(shops: dict[int, list[dict]],
                           findings: list | None = None) -> dict[int, list[dict]]:
    """Move shops recorded on the wrong NPC, then drop items the Classic shop doesn't sell.
    The lists live in scraper/corrections.py.
    If a `findings` list is given, each fix is also recorded there as a
    "shop_correction" AuditFinding (a place where MapleStory Quest's data was wrong for Classic)."""
    findings = findings if findings is not None else []
    for wrong_id, right_id in corrections.SHOP_MOVED_TO.items():
        stock = shops.pop(wrong_id, [])
        if stock and not shops.get(right_id):
            shops[right_id] = stock
            print(f"  moved shop from NPC {wrong_id} to NPC {right_id} ({len(stock)} items)")
            findings.append(AuditFinding(
                check="shop_correction", npc_id=right_id,
                detail=f"MapleStory Quest lists this shop ({len(stock)} items) on NPC {wrong_id}, a different "
                       f"NPC with the same name; moved to NPC {right_id} (hand-checked fix in scraper/corrections.py)"))
    for npc_id, remove in corrections.NOT_IN_CLASSIC_SHOPS.items():
        stock = shops.get(npc_id, [])
        for row in stock:
            if row["item_id"] in remove:
                findings.append(AuditFinding(
                    check="shop_correction", npc_id=npc_id, item_id=row["item_id"],
                    detail=f"MapleStory Quest's shop list for NPC {npc_id} includes "
                           f"'{row.get('item_name') or row['item_id']}' (older v83 list); the Classic shop "
                           f"does not sell it, so it was removed (hand-checked fix in scraper/corrections.py)"))
        shops[npc_id] = [s for s in stock if s["item_id"] not in remove]
        print(f"  NPC {npc_id}: removed {len(stock) - len(shops[npc_id])} items not in the Classic shop")
    return shops


def apply_monster_and_npc_corrections(monsters: list[dict], npcs: list[dict]) -> None:
    """Add name labels, hidden flags and notes from scraper/corrections.py (changes the lists in place)."""
    for m in monsters:
        suffix = corrections.MONSTER_NAME_SUFFIX.get(m["id"])
        if suffix:
            m["name"] = f"{m['name']} ({suffix})"
        m["maps"] = [name for name in (m.get("maps") or []) if name] or None  # drop blank map names
        m["hidden"] = m["id"] in corrections.HIDDEN_MONSTERS
        m["note"] = corrections.MONSTER_NOTES.get(m["id"])
    for n in npcs:
        n.update(corrections.NPC_OVERRIDES.get(n["id"], {}))
    npcs[:] = [n for n in npcs if n["id"] not in corrections.HIDDEN_NPCS]


# Tables holding what PLAYERS reported. A data refresh must never delete these.
KEEP_TABLES = {"price_reports", "drop_reports"}


def rebuild_tables(bind=None) -> None:
    """Drop and re-create every table (so new columns exist), EXCEPT the player
    report tables in KEEP_TABLES, which are left exactly as they are.

    Note: because the report tables are never dropped, a NEW column added to them
    later won't appear automatically; that would need a small migration."""
    bind = bind or engine
    game_tables = [t for t in Base.metadata.sorted_tables if t.name not in KEEP_TABLES]
    Base.metadata.drop_all(bind=bind, tables=game_tables)
    Base.metadata.create_all(bind=bind)  # re-creates the dropped tables; leaves the kept ones alone


def find_disagreements(items: dict[int, dict], drops: dict, shops: dict,
                       rejected: list[dict]) -> list[AuditFinding]:
    """Compare MapleStory Quest's drop/shop rows with OSMS. Returns AuditFinding rows:
    - name_mismatch:     same item ID, different name (one row per item)
    - unknown_item_ref:  MSQ row points at an item ID OSMS doesn't have (one row per page + item)
    - npc_shop_rejected: MSQ NPC page was about a different NPC, so its shop was ignored
    `items` must already include the extra items added from the client's name list."""
    findings: list[AuditFinding] = []
    seen_names: set[int] = set()
    # every MSQ row, tagged with the page it came from
    rows = [("monster", mid, d) for mid, ds in drops.items() for d in ds]
    rows += [("npc", nid, r) for nid, rs in shops.items() for r in rs]
    for kind, page_id, row in rows:
        item_id = row["item_id"]
        where = {"monster_id": page_id} if kind == "monster" else {"npc_id": page_id}
        page = f"{kind} {page_id}"
        msq_name = row.get("item_name") or "?"
        if item_id not in items:
            findings.append(AuditFinding(
                check="unknown_item_ref", item_id=item_id, **where,
                detail=f"MapleStory Quest ({page}) lists item {item_id} '{msq_name}', "
                       f"but OSMS has no item with that ID"))
            continue
        osms_name = items[item_id]["name"]
        if (item_id not in seen_names and msq_name != "?"
                and osms._name_key(msq_name) != osms._name_key(osms_name)):
            seen_names.add(item_id)
            findings.append(AuditFinding(
                check="name_mismatch", item_id=item_id, **where,
                detail=f"OSMS calls it '{osms_name}', MapleStory Quest ({page}) calls it '{msq_name}'"))
    for r in rejected:
        findings.append(AuditFinding(
            check="npc_shop_rejected", npc_id=r["npc_id"],
            detail=f"MapleStory Quest NPC page {r['npc_id']} has a shop, but it is a different NPC: "
                   f"{r['reason']}. Shop not used."))
    return findings


def load_maps(db, source_id: int, monster_ids: set[int], npc_ids: set[int]) -> tuple[int, int, int, str]:
    """Add the maps, monster_maps and npc_maps rows (offline: reads only cached files).
    Returns (maps, monster_maps, npc_maps, match report)."""
    try:
        rows = world_map.map_rows(cache_only=True)
        report = world_map.match_report(rows)
    except world_map.NotCached as missing:
        print(f"  world map files not cached ({missing}); maps get no spots. "
              f"Run `python -m scraper.world_map` once to download them.")
        rows = world_map.map_rows(spots=False)
        report = "no spots: world map cache missing"
    db.add_all(Map(**r, source_id=source_id) for r in rows)
    db.flush()
    map_ids = {r["id"] for r in rows}
    # Only keep links whose monster/NPC and map both exist (hidden NPCs were removed).
    mm = [r for r in osms.load_monster_maps() if r["monster_id"] in monster_ids and r["map_id"] in map_ids]
    nm = [r for r in osms.load_npc_maps() if r["npc_id"] in npc_ids and r["map_id"] in map_ids]
    db.add_all(MonsterMap(**r) for r in mm)
    db.add_all(NpcMap(**r) for r in nm)
    return len(rows), len(mm), len(nm), report


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--no-scrape", action="store_true", help="skip MapleStory Quest (no drops/shops/scroll prices)")
    parser.add_argument("--online", action="store_true",
                        help="allow downloading MapleStory Quest pages that aren't cached yet "
                             "(default: cache only, never go online)")
    args = parser.parse_args()

    rebuild_tables()
    db = SessionLocal()
    try:
        # --- 1. OSMS: items, monsters, NPCs, recipes, quest rewards --------
        osms_src = Source(name=osms.SOURCE_NAME, url=osms.SOURCE_URL, last_scraped=now(),
                          notes="Client datamine (Public Release), data/raw/osms/")
        db.add(osms_src)
        db.flush()  # gives osms_src an id

        items = {it["id"]: it for it in osms.load_items()}
        monsters = osms.load_monsters()
        npcs = osms.load_npcs()
        recipes, unmatched = osms.load_recipes(osms.name_to_id_lookup(set(items)))
        quest_rewards = osms.load_quest_rewards()
        apply_monster_and_npc_corrections(monsters, npcs)
        print(f"OSMS: {len(items)} items, {len(monsters)} monsters, {len(npcs)} NPCs, "
              f"{len(recipes)} recipes, {len(quest_rewards)} quest rewards")
        if unmatched:
            print(f"  {len(unmatched)} recipe ingredient names had no item match: {unmatched}")

        # --- 2. MapleStory Quest: drops, shops, scroll prices --------------
        drops, shops, scroll_prices, rejected = {}, {}, {}, []
        correction_findings: list[AuditFinding] = []  # filled by apply_shop_corrections
        if not args.no_scrape:
            cache_only = not args.online  # the default is the safe, offline mode
            mode = "cache only, no network" if cache_only else "ONLINE allowed, 2s apart, cached"
            print(f"Reading MapleStory Quest ({len(monsters) + len(npcs)} pages, {mode})...")
            npc_info = {n["id"]: (n["name"], n["map_name"]) for n in npcs}
            drops, shops, rejected = msquest.scrape([m["id"] for m in monsters], [n["id"] for n in npcs],
                                                    npc_info=npc_info, cache_only=cache_only)
            shops = apply_shop_corrections(shops, correction_findings)
            scroll_ids = osms.scroll_ids()
            print(f"Fetching {len(scroll_ids)} scroll item pages for NPC prices (cached)...")
            scroll_prices = msquest.scrape_item_prices(scroll_ids, cache_only=cache_only)
            for item_id, price in scroll_prices.items():
                if price is not None and item_id in items:
                    items[item_id]["npc_sell_price"] = price
        # Scrolls with no price anywhere sell for 1 meso (confirmed in game, see corrections.py).
        for item_id in osms.scroll_ids():
            if item_id in items and items[item_id].get("npc_sell_price") is None:
                items[item_id]["npc_sell_price"] = corrections.SCROLL_SELL_PRICE

        # Drops/shops/recipes/quests may mention items OSMS didn't list in items.json;
        # add those as basic entries using the client's full name list.
        names = osms.item_name_lookup()
        referenced = (
            {d["item_id"] for ds in drops.values() for d in ds}
            | {s["item_id"] for ss in shops.values() for s in ss}
            | {r["output_item_id"] for r in recipes}
            | {g["item_id"] for r in recipes for g in r["ingredients"] if g["item_id"]}
            | {q["item_id"] for q in quest_rewards}
        )
        missing = sorted(i for i in referenced if i not in items)
        for item_id in missing:
            if item_id in names:
                items[item_id] = osms.basic_item(item_id, names[item_id])
        skipped = [i for i in missing if i not in items]

        # icons copied by `python -m scraper.icons` live at app/static/img/items/{id}.png
        icon_dir = Path(__file__).resolve().parents[1] / "app" / "static" / "img" / "items"
        for it in items.values():
            if (icon_dir / f"{it['id']}.png").exists():
                it["icon_url"] = f"/static/img/items/{it['id']}.png"

        db.add_all(Item(**it, source_id=osms_src.id) for it in items.values())
        db.add_all(Monster(**m, source_id=osms_src.id) for m in monsters)
        db.add_all(Npc(**n, source_id=osms_src.id) for n in npcs)
        db.flush()

        # Recipes (+ their ingredients) and quest rewards
        n_recipes = n_ingredients = n_quest = 0
        for r in recipes:
            if r["output_item_id"] not in items:
                continue
            ingredients = [RecipeIngredient(item_id=g["item_id"] if g["item_id"] in items else None,
                                            item_name=g["item_name"], count=g["count"])
                           for g in r["ingredients"]]
            fields = {k: v for k, v in r.items() if k != "ingredients"}
            db.add(Recipe(**fields, ingredients=ingredients, source_id=osms_src.id))
            n_recipes += 1
            n_ingredients += len(ingredients)
        for q in quest_rewards:
            if q["item_id"] in items:
                db.add(QuestReward(**q, source_id=osms_src.id))
                n_quest += 1

        n_drops = n_shop = 0
        if drops or shops:
            msq_src = Source(name=msquest.SOURCE_NAME, url=msquest.SOURCE_URL, last_scraped=now(),
                             notes="Drop tables (older version rates), NPC shop stock, scroll NPC prices")
            db.add(msq_src)
            db.flush()
            for monster_id, rows in drops.items():
                for d in rows:
                    if d["item_id"] in items:
                        db.add(Drop(monster_id=monster_id, item_id=d["item_id"], drop_rate=d["drop_rate"],
                                    rate_source=msquest.RATE_SOURCE if d["drop_rate"] is not None else None,
                                    confidence=d["confidence"], source_id=msq_src.id))
                        n_drops += 1
            for npc_id, rows in shops.items():
                for s in rows:
                    if s["item_id"] in items:
                        db.add(ShopItem(npc_id=npc_id, item_id=s["item_id"], buy_price=s["buy_price"], source_id=msq_src.id))
                        n_shop += 1

        # --- 3. Maps + world map spots, and who is on which map -----------
        n_maps, n_monster_maps, n_npc_maps, map_report = load_maps(
            db, osms_src.id, {m["id"] for m in monsters}, {n["id"] for n in npcs})

        # --- 4. Audit: where OSMS and MapleStory Quest disagree ------------
        findings = find_disagreements(items, drops, shops, rejected) + correction_findings
        db.add_all(findings)

        db.commit()
        priced = sum(1 for p in scroll_prices.values() if p is not None)
        print("Done. Loaded:")
        print(f"  items              {len(items)}  ({len(missing) - len(skipped)} added from name list)")
        print(f"  monsters           {len(monsters)}")
        print(f"  npcs               {len(npcs)}  ({sum(1 for v in shops.values() if v)} with shops)")
        print(f"  drops              {n_drops}")
        print(f"  shop_items         {n_shop}")
        print(f"  recipes            {n_recipes}")
        print(f"  recipe_ingredients {n_ingredients}  ({sum(1 for r in recipes for g in r['ingredients'] if not g['item_id'])} unmatched)")
        print(f"  quest_rewards      {n_quest}")
        print(f"  maps               {n_maps}  ({map_report})")
        print(f"  monster_maps       {n_monster_maps}")
        print(f"  npc_maps           {n_npc_maps}")
        if scroll_prices:
            print(f"  scroll NPC prices  {priced} of {len(scroll_prices)} scroll pages had one")
        if skipped:
            print(f"  skipped {len(skipped)} unknown item IDs: {skipped[:10]}")
        by_check: dict[str, int] = {}
        for f in findings:
            by_check[f.check] = by_check.get(f.check, 0) + 1
        print(f"  audit_findings     {len(findings)}  {by_check}")
        kept = {name: db.execute(text(f"SELECT COUNT(*) FROM {name}")).scalar() for name in sorted(KEEP_TABLES)}
        print(f"  kept player reports {kept}")
    finally:
        db.close()


if __name__ == "__main__":
    main()
