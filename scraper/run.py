"""Load REAL game data into data/maple.db.

    .venv\\Scripts\\python -m scraper.run              # OSMS + scrape MapleStory Quest (~18 min first time)
    .venv\\Scripts\\python -m scraper.run --no-scrape  # OSMS only (no drops/shops/scroll prices)

What it does:
1. Rebuilds every table from scratch (this also removes the fake sample price/drop reports).
2. Loads items, scrolls, monsters, NPCs, crafting recipes and quest rewards from the
   OSMS datamine (data/raw/osms/).
3. Scrapes drop tables, NPC shops and scroll NPC prices from MapleStory Quest
   (cached in data/cache/, so re-running is fast and doesn't hit the site again).

To go back to fake sample data instead: .venv\\Scripts\\python -m scraper.seed_sample
"""
import argparse
from datetime import datetime, timezone
from pathlib import Path

from app.db import SessionLocal, engine, init_db
from app.models import (Base, Drop, Item, Monster, Npc, QuestReward, Recipe, RecipeIngredient,
                        ShopItem, Source)
from scraper import corrections
from scraper.sources import msquest, osms


def now() -> datetime:
    return datetime.now(timezone.utc).replace(tzinfo=None)


def apply_shop_corrections(shops: dict[int, list[dict]]) -> dict[int, list[dict]]:
    """Move shops recorded on the wrong NPC, then drop items the Classic shop doesn't sell.
    The lists live in scraper/corrections.py."""
    for wrong_id, right_id in corrections.SHOP_MOVED_TO.items():
        stock = shops.pop(wrong_id, [])
        if stock and not shops.get(right_id):
            shops[right_id] = stock
            print(f"  moved shop from NPC {wrong_id} to NPC {right_id} ({len(stock)} items)")
    for npc_id, remove in corrections.NOT_IN_CLASSIC_SHOPS.items():
        before = len(shops.get(npc_id, []))
        shops[npc_id] = [s for s in shops.get(npc_id, []) if s["item_id"] not in remove]
        print(f"  NPC {npc_id}: removed {before - len(shops[npc_id])} items not in the Classic shop")
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


def rebuild_tables() -> None:
    """Drop and re-create every table, so new columns (like items.jobs) exist."""
    Base.metadata.drop_all(bind=engine)
    init_db()


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--no-scrape", action="store_true", help="skip MapleStory Quest (no drops/shops/scroll prices)")
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
        drops, shops, scroll_prices = {}, {}, {}
        if not args.no_scrape:
            print(f"Scraping MapleStory Quest ({len(monsters) + len(npcs)} pages, 2s apart, cached)...")
            npc_info = {n["id"]: (n["name"], n["map_name"]) for n in npcs}
            drops, shops = msquest.scrape([m["id"] for m in monsters], [n["id"] for n in npcs], npc_info=npc_info)
            shops = apply_shop_corrections(shops)
            scroll_ids = osms.scroll_ids()
            print(f"Fetching {len(scroll_ids)} scroll item pages for NPC prices (cached)...")
            scroll_prices = msquest.scrape_item_prices(scroll_ids)
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
        if scroll_prices:
            print(f"  scroll NPC prices  {priced} of {len(scroll_prices)} scroll pages had one")
        if skipped:
            print(f"  skipped {len(skipped)} unknown item IDs: {skipped[:10]}")
    finally:
        db.close()


if __name__ == "__main__":
    main()
