# MapleStory Classic DB: Project Status

_Last updated: 2026-10-12. Claude updates this at the end of every phase._

## What the site does today
- **Item lookup:** stats, NPC sell price, and how to get each item (buy, drop, craft or quest), plus what it's used in.
- **Item browser** (`/items`): class tabs (All, Beginner, Warrior, Magician, Bowman, Thief) and picture filters (type, slot, weapon, level).
- **Monsters** (`/monsters`): drops with rates. Most rates are older-version (v83) estimates until players confirm them.
- **NPC shops** (`/shops`): what each shop sells and for how much.
- **Market:** players report prices on each item page. The page shows the median, the usual range and a 30-day chart. Each item page also links to MesoWatch for live Windia prices (link only, no data copied).
- **Data quality** (`/audit`): automatic checks of our data plus player reports.
- **World map** (home page): Maple Island and Victoria Island, with the game's own v83 map art. Click a spot to see its maps, monsters and NPCs.
- **📍 Show on map:** pings on monster "Found in" maps, item "Dropped by" monsters, NPC pages and `/shops`.
- **Admin** (`/admin`): delete bad reports.

## Finished phases
| Phase | Date | What |
|---|---|---|
| 1 | 2026-10-11 | Source audit: which sites we may use ([output/source-audit.md](../output/source-audit.md)) |
| 2 | 2026-10-11 | First working site on sample data (agent team) |
| 2b | 2026-10-11 | Real data: OSMS client data plus MapleStory Quest drops and shops |
| 3 | 2026-10-11 | "Maple World UI" redesign, item browser, crafting and quest data (agent team) |
| 4 | 2026-10-12 | MesoWatch link, `/audit` page and report, player reports now survive data refreshes (agent team) |
| 4b | 2026-10-12 | Class hometown backgrounds (real v83 town art with buildings) on the home cards and an `/items` banner; all class characters drawn at the same size |
| 5 | 2026-10-12 | Interactive world map on the home page plus "📍 Show on map" pings (agent team) |

## Notes on the world map
- **Coverage:** 168 of 305 maps sit on an exact spot of the game map. 92 are placed at the nearest connected spot, shown as "approximate". 45 (event, KPQ and dev maps) have no spot.
- **No map location for 15 monsters:** the Glowshroom/Rafflesia set (their map has no name in the client data) and the KPQ monsters, King Slime included.
- **Places not in Classic:** the v83 map art also shows Kerning Square, Florina Beach and Nautilus. They have no spots.

## Waiting on you
- [ ] Click-test the world map, especially on your phone (Victoria Island has 78 spots, so it's busy on a small screen).
- [ ] Paste one MesoWatch item URL so each item page can link straight to that item.
- [ ] Hide tutorial and test monsters (Tutorial Jr. Sentinel, Fairy 2 and 3)? Fairy 2 currently shows in the Henesys spot on the world map.
- [ ] Add a "report a drop we don't list" form? (The audit check for these always shows 0 without it.)
- [ ] Delete leftover test reports on `/admin` if any appear.

## Ideas for later
- More market features (trending items, per-world prices).
- Moving to Postgres for the public launch.
- MeowDB as a third data source (we'd need to email for permission first).

## Data source rules
| Source | Use |
|---|---|
| OSMS Data Explorer (client datamine) | ✅ Main source for items, monsters, NPCs, recipes and quests |
| MapleStory Quest | ✅ Drops and shops, from pages saved locally (refresh is offline by default) |
| maplestory.io | ✅ Class characters, town art and world maps (downloaded once, credited in the footer) |
| MesoWatch | 🔗 Link only. Its terms ban scraping and copying |
| MeowDB / NiaDB | ❌ Needs permission |
| Henesys.gg | ❌ Bans scraping |

## How to run (from the `maple-classic-db` folder)
- **Start the site:** `.venv\Scripts\python -m uvicorn app.main:app --reload`, then open http://127.0.0.1:8000 (if new pages 404 after big changes, stop it and start it again; auto-reload can get stuck)
- **Run the tests:** `.venv\Scripts\python -m pytest` (129 passing)
- **Refresh game data (offline):** `.venv\Scripts\python -m scraper.run` (add `--online` only to fetch new pages)
- **Data audit report:** `.venv\Scripts\python -m scraper.audit` writes the report to `output/`
- **Town backgrounds:** `.venv\Scripts\python -m scraper.town_backgrounds`
- **World map data:** `.venv\Scripts\python -m scraper.world_map` (prints the match rate)

## Where the details live
- **Technical contracts:** [docs/data-contract.md](docs/data-contract.md) and [docs/api-contract.md](docs/api-contract.md)
- **Design:** [docs/design-plan.md](docs/design-plan.md) and [docs/design-audit.md](docs/design-audit.md), [docs/design-worldmap.md](docs/design-worldmap.md)
- **Reports:** [output/](../output/)
- **Agent team guide and lessons:** [resources/agent-information-docs.md](../resources/agent-information-docs.md)
