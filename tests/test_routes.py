"""Page, JSON and form tests against the seeded sample data."""

from sqlalchemy import func, select

from app.models import Drop, DropReport, Npc, PriceReport
from app.services import queries

GLOVES_60 = 2040804   # has absurd outliers in the sample price data
SNAIL = 100100        # monster with drops + drop reports
HTMX = {"HX-Request": "true"}


# ---------- every page returns 200 ----------

def test_home(client):
    assert client.get("/").status_code == 200


def test_search_page(client):
    r = client.get("/search", params={"q": "snail"})
    assert r.status_code == 200
    assert "Snail" in r.text


def test_search_blank(client):
    assert client.get("/search").status_code == 200


def test_search_suggestions_html_and_json(client):
    assert client.get("/api/search", params={"q": "po"}).status_code == 200
    data = client.get("/api/search", params={"q": "snail", "format": "json"}).json()
    assert any(m["id"] == SNAIL for m in data["monsters"])


def test_item_page(client):
    r = client.get(f"/items/{GLOVES_60}")
    assert r.status_code == 200


def test_monster_page(client):
    assert client.get(f"/monsters/{SNAIL}").status_code == 200


def test_every_seeded_page_returns_200(client, db):
    from app.models import Item, Monster
    for item_id in db.scalars(select(Item.id)):
        assert client.get(f"/items/{item_id}").status_code == 200, item_id
    for monster_id in db.scalars(select(Monster.id)):
        assert client.get(f"/monsters/{monster_id}").status_code == 200, monster_id
    for npc_id in db.scalars(select(Npc.id)):
        assert client.get(f"/npcs/{npc_id}").status_code == 200, npc_id


def test_missing_pages_404(client):
    assert client.get("/items/1").status_code == 404
    assert client.get("/monsters/1").status_code == 404
    assert client.get("/npcs/1").status_code == 404


# ---------- data built for the pages ----------

def test_item_median_ignores_outliers(db):
    stats = queries.item_price_stats(db, GLOVES_60)
    # True price is around 1.5M; the 999,999,999 and 1 meso troll reports must not count.
    assert stats["high"] < 999_999_999
    assert stats["low"] > 1
    assert stats["outliers_removed"] >= 1


def test_unknown_rate_shows_unknown(db):
    unknown = db.scalar(select(Drop).where(Drop.drop_rate.is_(None)))
    assert unknown is not None, "sample data should have at least one unknown rate"
    data = queries.monster_detail(db, unknown.monster_id)
    row = next(d for d in data["drops"] if d["item"]["id"] == unknown.item_id)
    assert row["rate_label"] == "unknown"
    assert row["rate_percent"] is None


# ---------- price history JSON ----------

def test_price_history(client):
    days = client.get(f"/api/items/{GLOVES_60}/price-history").json()
    assert 0 < len(days) <= 31
    assert set(days[0]) == {"date", "median", "low", "high", "count"}
    assert days == sorted(days, key=lambda d: d["date"])
    # The outlier should not show up as any day's high.
    assert max(d["high"] for d in days) < 999_999_999


def test_price_history_missing_item(client):
    assert client.get("/api/items/1/price-history").status_code == 404


# ---------- forms ----------

def count_prices(db, item_id):
    return db.scalar(select(func.count()).select_from(PriceReport).where(PriceReport.item_id == item_id))


def test_submit_price_ok(client, db):
    before = count_prices(db, GLOVES_60)
    r = client.post(f"/items/{GLOVES_60}/prices",
                    data={"price": "1500000", "quantity": "1", "world": "Scania"}, headers=HTMX)
    assert r.status_code == 200
    assert "Price saved" in r.text
    assert count_prices(db, GLOVES_60) == before + 1


def test_submit_price_rejects_zero_and_bad_world(client, db):
    before = count_prices(db, GLOVES_60)
    for form in ({"price": "0", "world": "Scania"},
                 {"price": "-5", "world": "Scania"},
                 {"price": "abc", "world": "Scania"},
                 {"price": "100", "quantity": "999999", "world": "Scania"},
                 {"price": "100", "world": "Not A World"}):
        r = client.post(f"/items/{GLOVES_60}/prices", data=form, headers=HTMX)
        assert r.status_code == 200          # always 200; the snippet says what went wrong
        assert "saved" not in r.text.lower()
    assert count_prices(db, GLOVES_60) == before


def test_submit_price_without_htmx_redirects(client):
    r = client.post(f"/items/{GLOVES_60}/prices", data={"price": "100", "world": "Bera"},
                    follow_redirects=False)
    assert r.status_code == 303
    assert r.headers["location"] == f"/items/{GLOVES_60}"


def test_rate_limit(client):
    form = {"price": "1500000", "world": "Scania"}
    results = [client.post(f"/items/{GLOVES_60}/prices", data=form, headers=HTMX).text for _ in range(6)]
    assert all("Price saved" in t for t in results[:5])
    assert "Too many reports" in results[5]


def test_submit_drop_ok(client, db):
    item_id = db.scalar(select(Drop.item_id).where(Drop.monster_id == SNAIL))
    before = db.scalar(select(func.count()).select_from(DropReport))
    r = client.post(f"/monsters/{SNAIL}/drops",
                    data={"item_id": str(item_id), "kills": "200", "drops": "3", "world": "Bera"},
                    headers=HTMX)
    assert r.status_code == 200
    assert "Drop report saved" in r.text
    assert db.scalar(select(func.count()).select_from(DropReport)) == before + 1


def test_submit_drop_rejects_bad_input(client):
    bad_forms = [
        {"item_id": "2040804", "kills": "100", "drops": "1"},   # not a Snail drop
        {"item_id": "4000019", "kills": "0", "drops": "0"},     # no kills
        {"item_id": "4000019", "kills": "10", "drops": "11"},   # more drops than kills
    ]
    for form in bad_forms:
        r = client.post(f"/monsters/{SNAIL}/drops", data=form, headers=HTMX)
        assert r.status_code == 200
        assert "saved" not in r.text.lower()


# ---------- versioned CSS/JS links (so phones don't keep stale copies) ----------

def test_css_link_is_versioned_by_content(client):
    import hashlib
    from pathlib import Path
    css = Path(__file__).resolve().parents[1] / "app" / "static" / "css" / "site.css"
    expected = hashlib.md5(css.read_bytes()).hexdigest()[:10]
    r = client.get("/")
    assert f'/static/css/site.css?v={expected}"' in r.text
    assert "/static/js/worldmap.js?v=" in r.text


def test_versioned_static_url_still_serves_the_file(client):
    assert client.get("/static/css/site.css?v=anything").status_code == 200
