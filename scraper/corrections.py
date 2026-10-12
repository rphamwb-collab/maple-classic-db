"""Hand-checked fixes applied on top of the scraped data.

Why this file exists: our sources are good but not perfect. When we find a
mistake (for example during the MeowDB cross-check, output/meowdb-crosscheck.md),
we write the fix here instead of editing the database by hand. scraper/run.py
applies these every time it rebuilds the DB, so a re-scrape stays correct.

Rule: this file only says which of OUR rows to move, remove or label.
It never contains prices, stats or names copied from another site.
"""

# --- NPC shops ---------------------------------------------------------------

# MapleStory Quest records some shops on the wrong NPC when two NPCs share a name.
# {npc id the shop was recorded on: npc id that really runs the shop}
# - Sam #9 is the Maple Island quest giver (Snail Hunting Ground I) and has no shop.
#   The armor shop belongs to Sam #211 in Henesys.
SHOP_MOVED_TO = {
    9: 211,
}

# Items our source lists in a shop that the Classic launch shop does NOT sell.
# They are higher-tier (level 30) gear from the older v83 shop lists.
# Verified against NiaMeowDB launch shop lists, 2026-10-11
# (Karl, Harry, Don Hwang from the cross-check report; Sam, River, Serabi checked
#  on their MeowDB NPC pages; Cutthroat Manny and Flora by matching item counts).
# {npc id: {item ids to remove}}   (npc ids are AFTER the SHOP_MOVED_TO fix)
NOT_IN_CLASSIC_SHOPS = {
    210: {1452004, 1462004},  # Karl: Ryden, Eagle Crow
    508: {  # Harry
        1002104,                             # Jousting Helmet
        1040040, 1040041,                    # Red / Green Hwarang Shirt
        1050011,                             # Black Dragon Robe
        1051005, 1051006, 1051007, 1051008,  # Dark / Red / Blue / Yellow Engrit
        1060030, 1060031, 1060032, 1060033,  # Martial Arts Pants (4 colours)
    },
    409: {  # Don Hwang
        1002115, 1002116,                    # Red / Dark Guise
        1040047, 1040048,                    # Stealer tops
        1041053, 1041056,                    # Steal tops
        1060040, 1060041,                    # Stealer pants
        1061048, 1061051,                    # Steal pants
    },
    211: {  # Sam (Henesys armor shop)
        1002110, 1002114,                    # Green / Dark Hawkeye
        1040042, 1040045,                    # Green / Dark Hunter's Armor
        1041051, 1041052,                    # Green / Black Huntress Armor
        1060034, 1060037,                    # Green / Dark Hunter's Pants
        1061045, 1061046,                    # Green / Black Huntress Pants
    },
    311: {  # Serabi the Fairy
        1002105, 1002109,                    # Blue / Green Jester
        1041048, 1041049,                    # Blue / Green Fairy Top
        1050012, 1050015,                    # Blue / Green Wizard Robe
        1061042, 1061043,                    # Blue / Green Fairy Skirt
    },
    507: {  # River
        1302008, 1332009, 1312005, 1322013,  # Gladius, Cass, Fireman's Axe, War Hammer
        1402005, 1412004, 1422004,           # Scimitar, Blue Axe, Mithril Maul
        1432003, 1442004, 1092010,           # Forked Spear, Mithril Pole Arm, Red Cross Shield
    },
    408: {1332010, 1472010},  # Cutthroat Manny: Reef Claw, Adamantium Guards
    310: {1372004},           # Flora the Fairy: Mithril Wand
}

# --- NPC details -------------------------------------------------------------

# Extra info for NPCs. Keys are Npc column names.
# - Luma: the Public Release client puts her on no map. In Closed Online Test 2 she
#   stood in Cave Fairy Department Store next to the Forgotten Hollow NPCs, and her
#   shop sells "Return Scroll to Forgotten Hollow" (MapleStory Quest NPC page 700).
# - 701-714 (Zelya, Myen, Myra, the Bluebells, Nyroth...) are the other Cave Fairy /
#   Forgotten Hollow NPCs. The client puts them on no map; NiaMeowDB's Zelya page says
#   Cave Fairy Sanctuary is inaccessible until Grand Launch (output/meowdb-crosscheck-2.md).
FORGOTTEN_HOLLOW = {"town": "Forgotten Hollow", "note": "Not open in this release"}
NPC_OVERRIDES = {
    700: FORGOTTEN_HOLLOW,
    **{npc_id: FORGOTTEN_HOLLOW for npc_id in range(701, 715)},
}

# NPCs left out of the site entirely. Mr. Wang has no map, no shop and no page
# on NiaMeowDB: an unused / event NPC in the client files.
HIDDEN_NPCS = {9090000}

# --- Items -------------------------------------------------------------------

# Scrolls have no sell price in the client files or on MapleStory Quest.
# The site owner sold one to an NPC in game for 1 meso (2026-10-12), matching the
# 5 scrolls checked on NiaMeowDB, so every scroll gets 1.
SCROLL_SELL_PRICE = 1

# --- Monsters ----------------------------------------------------------------

# Monsters that share a name with a normal mob get a label so people can tell
# them apart. Checked against OSMS maps:
# - 800000-800002 spawn in "1st Accompaniment" maps = Kerning City Party Quest.
# - 800010-800017 spawn in the 2nd job advancement test maps
#   (Ant Tunnel For Bowman, Magician's Tree Dungeon, Thief's Construction Site,
#    Warrior's Rocky Mountain).
MONSTER_NAME_SUFFIX = {
    **{mob_id: "KPQ" for mob_id in range(800000, 800003)},
    **{mob_id: "2nd Job Test" for mob_id in range(800010, 800018)},
}

# Test / unreleased monsters, hidden from normal lists.
# None of these spawn on any Public Release map (OSMS), except Ultra Jr. Necki,
# which only appears in the Coconut Harvest event and can't be killed.
HIDDEN_MONSTERS = {
    9990000, 9990001, 9990002, 9990003, 9990004, 9990005,  # Test(Basic/Fire/...), 2.1 billion HP
    94,      # Ultra Jr. Necki 1
    700005,  # Crimson Balrog
    900000,  # Orange Slime
    25,      # Fairy 1
}

# Notes shown on a monster's page. Super mobs 90-93 are flagged "invincible" in
# the OSMS data: they are obstacles in jump quests and the Physical Fitness Test.
INVINCIBLE_NOTE = "Invincible obstacle (can't be killed)"
MONSTER_NOTES = {mob_id: INVINCIBLE_NOTE for mob_id in (90, 91, 92, 93)}

# Lv 39-59 mobs 54-63 (Glowshroom ... Sporewood) spawn on no map in this release's
# client. They are the Forgotten Hollow mobs; NiaMeowDB says "we don't know where
# it spawns yet" for Glowshroom and Sporewood.
NOT_OPEN_NOTE = "No spawn map in this release (likely Forgotten Hollow, not open yet)"
MONSTER_NOTES.update({mob_id: NOT_OPEN_NOTE for mob_id in range(54, 64)})
