# MapleStory Classic DB

Look up MapleStory Classic items, monster drops, NPC shops, and live market prices.

> Phase 2: running on **sample data**. Real game data will be added once source permissions are confirmed (see `../output/source-audit.md`).

## First-time setup (Windows, PowerShell)
Run these from inside the `maple-classic-db` folder:

```powershell
py -m venv .venv                          # create a private Python environment
.venv\Scripts\python -m pip install -r requirements.txt
```

## Fill the database with real game data
```powershell
.venv\Scripts\python -m scraper.run              # ~11 min the first time (polite scraping), seconds after (cached)
.venv\Scripts\python -m scraper.run --no-scrape  # items/monsters/NPCs only, no drops or shops
```
- Items, monsters, NPCs: OSMS Data Explorer client datamine (`data/raw/osms/`)
- Drop tables and NPC shops: MapleStory Quest (robots-allowed pages, 1 request / 2s, cached in `data/cache/`)
- Henesys.gg and MeowDB are **never** scraped (see `../output/source-audit.md`)

**Pictures** (item icons, monster sprites, NPC portraits) are already in `app/static/img/`. To refresh them after a game patch:
```powershell
git clone --depth 1 https://github.com/ohmi69/osms_datamine_dashboard.git C:\temp\osms
.venv\Scripts\python -m scraper.icons C:\temp\osms
.venv\Scripts\python -m scraper.run     # links items to their icons
```

To go back to fake sample data instead: `.venv\Scripts\python -m scraper.seed_sample`

## Run the website
```powershell
.venv\Scripts\python -m uvicorn app.main:app --reload
```
Then open http://localhost:8000 in your browser. Press Ctrl+C in the terminal to stop it.

## Run the tests
```powershell
.venv\Scripts\python -m pytest
```

## Folder guide
| Folder / file | What it is |
|---|---|
| `app/models.py`, `app/db.py` | Database tables and connection |
| `app/main.py`, `app/services/` | Website routes and logic (search, price math) |
| `app/templates/`, `app/static/` | The pages people see (HTML, CSS, JS) |
| `scraper/` | Data loading: sample data now, real sources later |
| `data/` | The database file (`maple.db`) |
| `docs/` | Shared contracts the team agreed on (tables, routes) |

## Data credits
Game data © Nexon. Fan project, not affiliated with Nexon.
