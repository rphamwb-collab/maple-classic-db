"""The website: every page and form route lives here.

Run it with:  .venv\\Scripts\\python -m uvicorn app.main:app --reload
The heavy lifting is in app/services/; this file just wires URLs to it.
Template variables are documented in docs/api-contract.md.
"""

from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import Depends, FastAPI, Form, HTTPException, Request
from fastapi.responses import JSONResponse, RedirectResponse, Response
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from sqlalchemy.orm import Session

from app.db import get_db, init_db
from app.models import Item, Monster
from app.services import admin, audit, browse, filters, queries, worldmap
from app.services.reports import WORLDS, ReportError, save_drop_report, save_price_report

APP_DIR = Path(__file__).parent


@asynccontextmanager
async def lifespan(app):
    # Make sure the database tables exist before the first request.
    init_db()
    yield


app = FastAPI(title="MapleStory Classic DB", lifespan=lifespan)
app.mount("/static", StaticFiles(directory=APP_DIR / "static", check_dir=False), name="static")
templates = Jinja2Templates(directory=APP_DIR / "templates")


def render(request, template_name, **context):
    """Render a template. `request` is always passed (templates need it for url_for)."""
    return templates.TemplateResponse(request, template_name, context)


def client_ip(request):
    """The visitor's IP address (used for rate limiting)."""
    return request.client.host if request.client else "unknown"


def is_htmx(request):
    """HTMX adds this header to its requests; plain form posts don't have it."""
    return request.headers.get("HX-Request") == "true"


# ---------- pages ----------

@app.get("/")
def home(request: Request, db: Session = Depends(get_db)):
    return render(request, "home.html", page_title="MapleStory Classic DB", q="",
                  counts=browse.home_counts(db), class_tabs=filters.home_class_tabs(db),
                  classes=filters.home_classes(db), monster_field=browse.home_monster_field(db),
                  world_maps=worldmap.all_world_maps(db))


@app.get("/items")
def items_browser(request: Request, db: Session = Depends(get_db)):
    """Item browser. Filters come from the URL (?class=warrior&type=equip...),
    so any view can be bookmarked. HTMX requests get just the results partial."""
    data = filters.browse_items(db, request.query_params)
    template = "partials/item_results.html" if is_htmx(request) else "items.html"
    return render(request, template, page_title="Items", **data)


@app.get("/monsters")
def monsters_list(request: Request, level: str = "", db: Session = Depends(get_db)):
    return render(request, "monsters.html", page_title="Monsters", **browse.browse_monsters(db, level))


@app.get("/shops")
def shops_list(request: Request, db: Session = Depends(get_db)):
    return render(request, "shops.html", page_title="NPC Shops", **browse.shops_by_town(db))


@app.get("/npcs")
def npcs_list():
    # The NPC list IS the shop list, so send people there.
    return RedirectResponse("/shops", status_code=307)


@app.get("/search")
def search_page(request: Request, q: str = "", db: Session = Depends(get_db)):
    q = q.strip()
    results = queries.search(db, q)
    total = sum(len(v) for v in results.values())
    title = f"Search: {q}" if q else "Search"
    return render(request, "search.html", page_title=title, q=q, results=results, total=total)


@app.get("/api/search")
def search_suggestions(request: Request, q: str = "", format: str = "html",
                       db: Session = Depends(get_db)):
    """Autocomplete for the search box: an HTML snippet for HTMX, or JSON."""
    q = q.strip()
    results = queries.search(db, q, limit=8)
    if format == "json":
        return JSONResponse(results)
    return render(request, "partials/search_suggestions.html", q=q, results=results)


@app.get("/items/{item_id}")
def item_page(request: Request, item_id: int, db: Session = Depends(get_db)):
    data = queries.item_detail(db, item_id)
    if data is None:
        raise HTTPException(status_code=404, detail="Item not found")
    return render(request, "item.html", page_title=data["item"]["name"], worlds=WORLDS, **data)


@app.get("/monsters/{monster_id}")
def monster_page(request: Request, monster_id: int, db: Session = Depends(get_db)):
    data = queries.monster_detail(db, monster_id)
    if data is None:
        raise HTTPException(status_code=404, detail="Monster not found")
    return render(request, "monster.html", page_title=data["monster"]["name"], worlds=WORLDS, **data)


@app.get("/npcs/{npc_id}")
def npc_page(request: Request, npc_id: int, db: Session = Depends(get_db)):
    data = queries.npc_detail(db, npc_id)
    if data is None:
        raise HTTPException(status_code=404, detail="NPC not found")
    return render(request, "npc.html", page_title=data["npc"]["name"], **data)


@app.get("/audit")
def audit_page(request: Request, check: str = "", db: Session = Depends(get_db)):
    """Data quality page: gaps and disagreements in our data. ?check=<slug> shows one check."""
    return render(request, "audit.html", page_title="Data quality", **audit.audit_page(db, check))


# ---------- JSON for the price chart ----------

@app.get("/api/items/{item_id}/price-history")
def price_history(item_id: int, db: Session = Depends(get_db)):
    if db.get(Item, item_id) is None:
        raise HTTPException(status_code=404, detail="Item not found")
    return queries.price_history(db, item_id)


# ---------- JSON for the world map ----------

@app.get("/api/world/{world}")
def world_api(world: str, db: Session = Depends(get_db)):
    """One island's picture + clickable spots (maps, monsters, NPCs at each)."""
    data = worldmap.world_map(db, world)
    if data is None:
        raise HTTPException(status_code=404, detail="Unknown world")
    return data


@app.get("/api/locate")
def locate_api(monster: str = "", npc: str = "", map: str = "", db: Session = Depends(get_db)):
    """Pings for "Show on map". Give exactly one of ?monster=ID, ?npc=ID or ?map=ID."""
    given = {kind: value for kind, value in (("monster", monster), ("npc", npc), ("map", map))
             if value.strip()}
    if len(given) != 1:
        raise HTTPException(status_code=400, detail="Give exactly one of monster, npc or map.")
    kind, value = next(iter(given.items()))
    try:
        thing_id = int(value)
    except ValueError:
        raise HTTPException(status_code=400, detail="The id must be a number.")
    data = worldmap.locate(db, kind, thing_id)
    if data is None:
        raise HTTPException(status_code=404, detail=f"{kind.capitalize()} not found")
    return data


# ---------- forms (user reports) ----------
# Fields are read as text so we can give friendly error messages
# instead of FastAPI's automatic "422 Unprocessable" error.

@app.post("/items/{item_id}/prices")
def report_price(request: Request, item_id: int,
                 price: str = Form(""), quantity: str = Form("1"), world: str = Form(""),
                 db: Session = Depends(get_db)):
    if db.get(Item, item_id) is None:
        raise HTTPException(status_code=404, detail="Item not found")

    try:
        save_price_report(db, item_id, price, quantity, world, client_ip(request))
        ok, message = True, "Thanks! Price saved."
    except ReportError as e:
        ok, message = False, str(e)

    if not is_htmx(request):
        return RedirectResponse(f"/items/{item_id}", status_code=303)
    return render(request, "partials/report_result.html", ok=ok, message=message,
                  price_stats=queries.item_price_stats(db, item_id))


@app.post("/monsters/{monster_id}/drops")
def report_drop(request: Request, monster_id: int,
                item_id: str = Form(""), kills: str = Form(""), drops: str = Form("0"),
                world: str = Form(""), db: Session = Depends(get_db)):
    if db.get(Monster, monster_id) is None:
        raise HTTPException(status_code=404, detail="Monster not found")

    observed = None
    try:
        report = save_drop_report(db, monster_id, item_id, kills, drops, world, client_ip(request))
        ok, message = True, "Thanks! Drop report saved."
        observed = queries.observed_for(db, monster_id, report.item_id)
    except ReportError as e:
        ok, message = False, str(e)

    if not is_htmx(request):
        return RedirectResponse(f"/monsters/{monster_id}", status_code=303)
    return render(request, "partials/report_result.html", ok=ok, message=message, observed=observed)


# ---------- admin: delete bad reports ----------

def require_admin(request: Request):
    """404 when the admin page is off (no ADMIN_PASSWORD), the browser's
    password box when not logged in."""
    if not admin.admin_password():
        raise HTTPException(status_code=404)
    if not admin.check_login(request.headers.get("Authorization")):
        raise HTTPException(status_code=401, headers={"WWW-Authenticate": 'Basic realm="Maple Classic DB admin"'})


@app.get("/admin")
def admin_page(request: Request, db: Session = Depends(get_db), _=Depends(require_admin)):
    return render(request, "admin.html", page_title="Admin", **admin.recent_reports(db))


@app.post("/admin/{kind}/{report_id}/delete")
def admin_delete(request: Request, kind: str, report_id: int,
                 db: Session = Depends(get_db), _=Depends(require_admin)):
    if kind not in ("prices", "drops"):
        raise HTTPException(status_code=404)
    if not admin.same_site(request.headers.get("Origin"), request.headers.get("Referer"),
                           request.headers.get("Host")):
        raise HTTPException(status_code=403, detail="Delete from the admin page.")
    admin.delete_report(db, kind, report_id)
    if is_htmx(request):
        return Response("")  # HTMX removes the table row
    return RedirectResponse("/admin", status_code=303)
