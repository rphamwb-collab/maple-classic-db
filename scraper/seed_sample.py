"""Fill the database with FAKE sample data so the website can be built and tested.

Run from the maple-classic-db folder:
    .venv\\Scripts\\python -m scraper.seed_sample

WARNING: this deletes everything in data/maple.db and refills it.
None of this is real game data. Every record is tagged with the source "sample".
"""
import random
from datetime import timedelta

from sqlalchemy import func, select

from app.db import SessionLocal, engine, init_db
from app.models import (
    AuditFinding,
    Base,
    Drop,
    DropReport,
    Item,
    Map,
    Monster,
    MonsterMap,
    Npc,
    NpcMap,
    PriceReport,
    QuestReward,
    Recipe,
    RecipeIngredient,
    ShopItem,
    Source,
    utc_now,
)

# Same "random" numbers every run, so the sample data is repeatable.
random.seed(42)

WORLDS = ["Scania", "Bera", "Broa"]

# ---------------------------------------------------------------------------
# Items: (id, name, category, sub_type, level_req, job, stats, npc_sell_price, description)
# ---------------------------------------------------------------------------
ITEMS = [
    # --- Equips ---
    (1302000, "Sword", "equip", "One-Handed Sword", 0, "Warrior", {"weapon_attack": 17, "slots": 7}, 1, "A basic sword."),
    (1312004, "Hand Axe", "equip", "One-Handed Axe", 10, "Warrior", {"str": 1, "weapon_attack": 25, "slots": 7}, 500, None),
    (1372005, "Wooden Wand", "equip", "Wand", 8, "Magician", {"int": 1, "weapon_attack": 13, "magic_attack": 23, "slots": 7}, 400, None),
    (1382000, "Wooden Staff", "equip", "Staff", 10, "Magician", {"weapon_attack": 20, "magic_attack": 30, "slots": 7}, 600, None),
    (1452002, "War Bow", "equip", "Bow", 10, "Bowman", {"dex": 1, "weapon_attack": 33, "slots": 7}, 700, None),
    (1472000, "Garnier", "equip", "Claw", 10, "Thief", {"luk": 1, "weapon_attack": 15, "slots": 7}, 500, None),
    (1332000, "Fruit Knife", "equip", "Dagger", 10, "Thief", {"weapon_attack": 28, "slots": 7}, 550, None),
    (1002008, "Brown Bamboo Hat", "equip", "Hat", 5, "Any", {"weapon_def": 6, "slots": 7}, 50, None),
    (1040002, "White Undershirt", "equip", "Top", 0, "Any", {"weapon_def": 3, "slots": 7}, 10, None),
    (1060002, "Blue Jean Shorts", "equip", "Bottom", 0, "Any", {"weapon_def": 2, "slots": 7}, 10, None),
    (1072001, "Red Rubber Boots", "equip", "Shoes", 0, "Any", {"weapon_def": 2, "slots": 5}, 10, None),
    (1082002, "Work Gloves", "equip", "Gloves", 10, "Any", {"weapon_def": 2, "slots": 5}, 200, "Every new player wants a pair."),
    (1402000, "Two-Handed Sword", "equip", "Two-Handed Sword", 10, "Warrior", {"weapon_attack": 30, "slots": 7}, 600, None),
    (1002043, "Bronze Bandana", "equip", "Hat", 12, "Warrior/Thief", {"weapon_def": 9, "slots": 7}, 300, "Worn by warriors and thieves alike."),
    # --- Use: potions, food, ammo ---
    (2000000, "Red Potion", "use", "Potion", None, None, {"heal_hp": 50}, 25, "Restores 50 HP."),
    (2000001, "Orange Potion", "use", "Potion", None, None, {"heal_hp": 150}, 80, "Restores 150 HP."),
    (2000002, "White Potion", "use", "Potion", None, None, {"heal_hp": 300}, 160, "Restores 300 HP."),
    (2000003, "Blue Potion", "use", "Potion", None, None, {"heal_mp": 100}, 100, "Restores 100 MP."),
    (2000006, "Mana Elixir", "use", "Potion", None, None, {"heal_mp": 300}, 310, "Restores 300 MP."),
    (2010000, "Apple", "use", "Food", None, None, {"heal_hp": 30}, 1, "A crunchy apple."),
    (2060000, "Arrow for Bow", "use", "Arrow", None, "Bowman", {"weapon_attack": 1}, 0, None),
    (2070000, "Subi Throwing-Stars", "use", "Throwing Star", 10, "Thief", {"weapon_attack": 15}, 250, None),
    # --- Use: scrolls ---
    (2040804, "Scroll for Gloves for ATT 60%", "use", "Scroll", None, None, {"success_rate": 60, "weapon_attack": 2}, 25, None),
    (2040805, "Scroll for Gloves for ATT 10%", "use", "Scroll", None, None, {"success_rate": 10, "weapon_attack": 3}, 25, None),
    (2043001, "Scroll for One-Handed Sword for ATT 60%", "use", "Scroll", None, None, {"success_rate": 60, "weapon_attack": 2}, 25, None),
    (2044501, "Scroll for Bow for ATT 60%", "use", "Scroll", None, None, {"success_rate": 60, "weapon_attack": 2}, 25, None),
    # npc_sell_price None = can't sell to NPCs (like real scrolls in the client)
    (2040002, "Scroll for Helmet for DEF 60%", "use", "Scroll", None, None, {"success_rate": 60, "weapon_def": 2}, None, None),
    # --- Etc (monster drops) ---
    (4000019, "Snail Shell", "etc", "Monster Drop", None, None, None, 1, None),
    (4000000, "Blue Snail Shell", "etc", "Monster Drop", None, None, None, 2, None),
    (4000016, "Red Snail Shell", "etc", "Monster Drop", None, None, None, 3, None),
    (4000001, "Orange Mushroom Cap", "etc", "Monster Drop", None, None, None, 5, None),
    (4000004, "Squishy Liquid", "etc", "Monster Drop", None, None, None, 4, None),
    (4000002, "Pig's Ribbon", "etc", "Monster Drop", None, None, None, 5, None),
    (4000003, "Tree Branch", "etc", "Monster Drop", None, None, None, 4, None),
    # --- Setup ---
    (3010000, "The Relaxer", "setup", "Chair", None, None, None, 1, "Sit down and recover HP faster."),
]

# ---------------------------------------------------------------------------
# v2 equip info: item_id -> (equip_slot, weapon_type, jobs)
# Items not listed here are non-equips: equip_slot None, weapon_type None, jobs [].
# jobs [] on an equip = any class / beginner can wear it.
# ---------------------------------------------------------------------------
EQUIP_INFO = {
    1302000: ("Weapon", "1H Sword", ["Warrior"]),
    1312004: ("Weapon", "1H Axe", ["Warrior"]),
    1402000: ("Weapon", "2H Sword", ["Warrior"]),
    1372005: ("Weapon", "Wand", ["Magician"]),
    1382000: ("Weapon", "Staff", ["Magician"]),
    1452002: ("Weapon", "Bow", ["Bowman"]),
    1472000: ("Weapon", "Claw", ["Thief"]),
    1332000: ("Weapon", "Dagger", ["Thief"]),
    1002008: ("Hat", None, []),
    1002043: ("Hat", None, ["Warrior", "Thief"]),  # multi-class equip
    1040002: ("Top", None, []),
    1060002: ("Bottom", None, []),
    1072001: ("Shoes", None, []),
    1082002: ("Glove", None, []),
}

# ---------------------------------------------------------------------------
# v2 crafting recipes: (recipe_id, output_item_id, result_count, discipline, discipline_level,
#                       req_level, craft_exp, meso_cost, [(item_id or None, item_name, count), ...])
# item_id None = ingredient name we couldn't match to an item (shown as plain text).
# ---------------------------------------------------------------------------
RECIPES = [
    (1, 1002008, 1, "Smithing", 1, 1, 20, 500,
     [(4000019, "Snail Shell", 10), (4000003, "Tree Branch", 5)]),
    (2, 1082002, 1, "Tailoring", 2, 10, 40, 1200,
     [(4000004, "Squishy Liquid", 3), (None, "Processed Leather", 2)]),
]

# ---------------------------------------------------------------------------
# v2 quest rewards: (quest_id, quest_name, npc_name, region, level_min, item_id, count, reward_type, job)
# ---------------------------------------------------------------------------
QUEST_REWARDS = [
    (2050, "Sabitrama's Herb", "Sabitrama", "Victoria Island", 10, 2000001, 3, "guaranteed", None),
    (10104, "Pia and the Blue Mushroom", "Pia", "Victoria Island", 16, 2043001, 1, "random", None),
    (10401, "A Gift for the Brave", "Rina", "Victoria Island", 20, 2044501, 1, "choice", "Bowman"),
]

# ---------------------------------------------------------------------------
# Monsters: (id, name, level, hp, exp, maps)
# ---------------------------------------------------------------------------
MONSTERS = [
    (100100, "Snail", 1, 8, 3, ["Maple Island", "Henesys Hunting Ground I"]),
    (100101, "Blue Snail", 2, 15, 4, ["Maple Island", "Henesys Hunting Ground I"]),
    (130101, "Red Snail", 4, 45, 8, ["Henesys Hunting Ground I"]),
    (120100, "Shroom", 2, 20, 5, ["Maple Island"]),
    (210100, "Slime", 6, 50, 10, ["Ellinia: The Tree That Grew"]),
    (1210100, "Pig", 7, 80, 12, ["Henesys: Pig Park"]),
    (1210102, "Orange Mushroom", 8, 80, 15, ["Henesys Hunting Ground II"]),
    (1130100, "Axe Stump", 17, 200, 32, ["Perion: Rocky Mountain"]),
    (1110100, "Green Mushroom", 15, 125, 26, ["Henesys Hunting Ground II"]),
    (1120100, "Octopus", 12, 150, 24, ["Kerning City Subway"]),
]

# ---------------------------------------------------------------------------
# Drops: monster_id -> list of (item_id, drop_rate or None)
# None = rate unknown (on purpose, to test the "Unknown" label).
# ---------------------------------------------------------------------------
DROPS = {
    100100: [(4000019, 0.60), (2000000, 0.10), (1040002, None)],
    100101: [(4000000, 0.55), (2000000, 0.10), (1060002, None)],
    130101: [(4000016, 0.50), (2000001, 0.05), (1072001, 0.01)],
    120100: [(4000001, None), (2010000, 0.15)],
    210100: [(4000004, 0.50), (2000003, 0.05), (1372005, None), (2044501, 0.0005)],
    1210100: [(4000002, 0.50), (2000001, 0.08), (1082002, 0.002), (1002008, None)],
    1210102: [(4000001, 0.55), (2000002, 0.04), (2040804, 0.0003), (1452002, None)],
    1130100: [(4000003, 0.55), (1312004, 0.004), (2043001, None)],
    1110100: [(2000002, 0.06), (2040002, 0.0005), (1382000, None)],
    1120100: [(2000006, 0.03), (2070000, 0.002), (1472000, 0.003), (2040805, None)],
}

# ---------------------------------------------------------------------------
# NPC shops: (npc_id, name, town, map_name, [(item_id, buy_price), ...])
# ---------------------------------------------------------------------------
NPCS = [
    (1011000, "Pia", "Henesys", "Henesys Market",
     [(2000000, 50), (2000001, 160), (2000002, 320), (2000003, 200), (2060000, 1), (2010000, 3)]),
    (1012003, "Rina", "Henesys", "Henesys Weapon Store",
     [(1452002, 3000), (1302000, 50), (1082002, 1000), (1002008, 200)]),
    (1032000, "Arwen", "Ellinia", "Ellinia Magic Shop",
     [(2000003, 200), (2000006, 620), (1372005, 2000), (1382000, 3000)]),
    (1022001, "Mr. Smith", "Perion", "Perion Weapon Store",
     [(1312004, 2500), (1302000, 50), (2000001, 160), (1072001, 50)]),
    (1052000, "Don Hwang", "Kerning City", "Kerning City Shop",
     [(1472000, 2400), (1332000, 2600), (2070000, 1000), (2000002, 320), (1040002, 30), (1060002, 30)]),
]

# ---------------------------------------------------------------------------
# v4 world map: (map_id, name, street_name, region, map_mark, is_town, return_map_id,
#                world, spot_x, spot_y, spot_exact)
# Spots are pixels from the top-left of app/static/img/worldmap/{world}.png. Pixel values are
# copied from the real world map so pings land somewhere sensible; the map IDs are made up.
# ---------------------------------------------------------------------------
MAPS = [
    (10001000, "Henesys", "Victoria Road", "Victoria Island", "Henesys", True, None,
     "victoria-island", 292, 377, True),
    (10001100, "Henesys Hunting Ground I", "Victoria Road", "Victoria Island", "Henesys", False, 10001000,
     "victoria-island", 240, 374, True),
    # no spot of its own: uses Henesys's spot (spot_exact False)
    (10001101, "Pig Park", "Hidden Street", "Victoria Island", "Henesys", False, 10001000,
     "victoria-island", 292, 377, False),
    (40000, "Snail Hunting Ground I", "Maple Road", "Maple Island", "Amherst", False, 1000000,
     "maple-island", 140, 146, True),
    (1000000, "Amherst", "Rainbow Street", "Maple Island", "Amherst", True, None,
     "maple-island", 301, 220, True),
    # an event map: not on any world map picture (world and spot all None)
    (90000000, "Sample Event Map", "Event", "Event", "Event", False, None, None, None, None, None),
]

# (monster_id, map_id, spawn_count)
MONSTER_MAPS = [
    (100100, 40000, 12),      # Snail: Maple Island ...
    (100100, 10001100, 8),    # ... and Victoria Island
    (100101, 40000, 6),       # Blue Snail
    (1210100, 10001101, 10),  # Pig: on a fallback-spot map
    (1210102, 90000000, 5),   # Orange Mushroom: on a map with no spot
]

# (npc_id, map_id)
NPC_MAPS = [(1011000, 10001000), (1012003, 10001000)]  # Pia + Rina in Henesys

# ---------------------------------------------------------------------------
# Market price reports: item_id -> typical price (mesos per unit) and daily drift
# ---------------------------------------------------------------------------
MARKET_ITEMS = {
    2040804: 1_500_000,  # Gloves ATT 60%
    2040805: 120_000,    # Gloves ATT 10%
    1082002: 40_000,     # Work Gloves
    2070000: 1_100,      # Subi Throwing-Stars
    2000006: 650,        # Mana Elixir
    3010000: 60_000,     # The Relaxer
}
DAYS_OF_HISTORY = 60


def fake_ip() -> str:
    """A made-up private IP address (10.x.x.x), never a real person's."""
    return f"10.0.{random.randint(0, 20)}.{random.randint(1, 254)}"


def wipe_database() -> None:
    """Drop every table and create them again, empty."""
    Base.metadata.drop_all(bind=engine)
    init_db()


def make_price_reports(now) -> list[PriceReport]:
    reports = []
    for item_id, start_price in MARKET_ITEMS.items():
        price = float(start_price)
        for days_ago in range(DAYS_OF_HISTORY, 0, -1):
            # The "true" price wanders a little each day (random walk, +/- 3%).
            price *= random.uniform(0.97, 1.03)
            for _ in range(random.randint(1, 5)):  # 1-5 reports per day
                when = now - timedelta(days=days_ago, hours=random.randint(0, 23), minutes=random.randint(0, 59))
                reports.append(PriceReport(
                    item_id=item_id,
                    price=max(1, round(price * random.uniform(0.9, 1.1))),
                    quantity=random.choice([1, 1, 1, 5, 10, 100]) if item_id in (2070000, 2000006) else 1,
                    world=random.choice(WORLDS),
                    reported_at=when,
                    reporter_ip=fake_ip(),
                    status="ok",
                ))

    # Absurd outliers left as "ok" so the backend's outlier filter has something to catch.
    outliers = [
        (2040804, 999_999_999, 3),  # way too high
        (2040804, 1, 10),           # way too low
        (1082002, 50_000_000, 20),  # troll price
        (2000006, 1, 5),            # troll price
    ]
    for item_id, bad_price, days_ago in outliers:
        reports.append(PriceReport(item_id=item_id, price=bad_price, quantity=1, world="Scania",
                                   reported_at=now - timedelta(days=days_ago), reporter_ip=fake_ip(), status="ok"))

    # A couple already flagged by a moderator (should be hidden from charts).
    for item_id, bad_price, days_ago in [(3010000, 123_456_789, 7), (2070000, 2, 15)]:
        reports.append(PriceReport(item_id=item_id, price=bad_price, quantity=1, world="Bera",
                                   reported_at=now - timedelta(days=days_ago), reporter_ip=fake_ip(), status="flagged"))
    return reports


def make_drop_reports(now) -> list[DropReport]:
    """Fake kill logs. Observed counts loosely follow the sample drop rates."""
    reports = []
    picks = [
        (100100, 4000019), (100100, 2000000), (1210100, 4000002), (1210100, 1082002),
        (1210102, 4000001), (1210102, 2040804), (1120100, 2070000), (210100, 4000004),
    ]
    rates = {(m, i): r for m, drops in DROPS.items() for i, r in drops}
    for monster_id, item_id in picks:
        for _ in range(random.randint(1, 3)):
            kills = random.choice([50, 100, 200, 500, 1000])
            rate = rates.get((monster_id, item_id)) or 0.01
            seen = sum(1 for _ in range(kills) if random.random() < rate)
            reports.append(DropReport(monster_id=monster_id, item_id=item_id, kills=kills, drops_seen=seen,
                                      world=random.choice(WORLDS),
                                      reported_at=now - timedelta(days=random.randint(0, 30)),
                                      reporter_ip=fake_ip()))
    # A "killed some, logged no specific item" report (item_id is None).
    reports.append(DropReport(monster_id=1130100, item_id=None, kills=300, drops_seen=0, world="Broa",
                              reported_at=now - timedelta(days=2), reporter_ip=fake_ip()))
    return reports


def make_audit_findings() -> list[AuditFinding]:
    """One fake OSMS-vs-MapleStory-Quest disagreement per check, so the /audit page has rows."""
    return [
        AuditFinding(check="name_mismatch", item_id=2000000, monster_id=100100,
                     detail="OSMS calls it 'Red Potion', MapleStory Quest (monster 100100) calls it 'Red Potion (sample)'"),
        AuditFinding(check="unknown_item_ref", item_id=4999999, monster_id=100100,
                     detail="MapleStory Quest (monster 100100) lists item 4999999 'Sample Mystery Item', "
                            "but OSMS has no item with that ID"),
        AuditFinding(check="npc_shop_rejected", npc_id=1011000,
                     detail="MapleStory Quest NPC page 1011000 has a shop, but it is a different NPC: "
                            "name differs (MSQ 'Sample' vs OSMS 'Pia'). Shop not used."),
        AuditFinding(check="shop_correction", npc_id=1011000, item_id=2000001,
                     detail="MapleStory Quest's shop list for NPC 1011000 includes 'Orange Potion' (older v83 list); "
                            "the Classic shop does not sell it, so it was removed (sample row)"),
    ]


def seed() -> None:
    wipe_database()
    now = utc_now()

    with SessionLocal() as db:
        sample = Source(name="sample", url=None, last_scraped=now,
                        notes="Fake sample data for development. Not real game data.")
        db.add(sample)
        db.flush()  # gives `sample` its id

        for (item_id, name, cat, sub, lvl, job, stats, sell, desc) in ITEMS:
            slot, weapon_type, jobs = EQUIP_INFO.get(item_id, (None, None, []))
            db.add(Item(id=item_id, name=name, category=cat, sub_type=sub, level_req=lvl, job=job,
                        stats=stats, description=desc, npc_sell_price=sell, icon_url=None,
                        equip_slot=slot, weapon_type=weapon_type, jobs=jobs,
                        source_id=sample.id))

        for (mob_id, name, lvl, hp, exp, maps) in MONSTERS:
            db.add(Monster(id=mob_id, name=name, level=lvl, hp=hp, exp=exp, maps=maps, source_id=sample.id))
        db.flush()

        for mob_id, drop_list in DROPS.items():
            for item_id, rate in drop_list:
                db.add(Drop(monster_id=mob_id, item_id=item_id, drop_rate=rate,
                            rate_source="sample" if rate is not None else None,
                            confidence="estimated" if rate is not None else "unverified",
                            source_id=sample.id))

        for (npc_id, name, town, map_name, stock) in NPCS:
            db.add(Npc(id=npc_id, name=name, town=town, map_name=map_name, source_id=sample.id))
            for item_id, price in stock:
                db.add(ShopItem(npc_id=npc_id, item_id=item_id, buy_price=price, source_id=sample.id))

        for (map_id, name, street, region, mark, town, ret, world, x, y, exact) in MAPS:
            db.add(Map(id=map_id, name=name, street_name=street, region=region, map_mark=mark, is_town=town,
                       return_map_id=ret, world=world, spot_x=x, spot_y=y, spot_exact=exact,
                       v83_map_id=None, source_id=sample.id))
        db.flush()  # maps must exist before the rows that point at them
        for (mob_id, map_id, count) in MONSTER_MAPS:
            db.add(MonsterMap(monster_id=mob_id, map_id=map_id, spawn_count=count))
        for (npc_id, map_id) in NPC_MAPS:
            db.add(NpcMap(npc_id=npc_id, map_id=map_id))

        for (rid, out_id, n_out, disc, disc_lvl, req_lvl, exp, cost, ings) in RECIPES:
            db.add(Recipe(id=rid, output_item_id=out_id, result_count=n_out, discipline=disc,
                          discipline_level=disc_lvl, req_level=req_lvl, craft_exp=exp, meso_cost=cost,
                          source_id=sample.id,
                          ingredients=[RecipeIngredient(item_id=i, item_name=nm, count=c) for i, nm, c in ings]))

        for (qid, qname, npc, region, lvl, item_id, count, rtype, job) in QUEST_REWARDS:
            db.add(QuestReward(quest_id=qid, quest_name=qname, npc_name=npc, region=region, level_min=lvl,
                               item_id=item_id, count=count, reward_type=rtype, job=job, source_id=sample.id))

        db.add_all(make_price_reports(now))
        db.add_all(make_drop_reports(now))
        db.add_all(make_audit_findings())
        db.commit()

        # Print row counts so we can see it worked.
        print("Seeded data/maple.db with sample data:")
        for model in (Source, Item, Monster, Drop, Npc, ShopItem, PriceReport, DropReport,
                      Recipe, RecipeIngredient, QuestReward, AuditFinding, Map, MonsterMap, NpcMap):
            count = db.scalar(select(func.count()).select_from(model))
            print(f"  {model.__tablename__:<14} {count}")


if __name__ == "__main__":
    seed()
