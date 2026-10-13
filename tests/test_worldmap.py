"""World map + "show on map" tests, on the seeded sample maps (scraper/seed_sample.py).

Seeded maps (from data-engineer's seed):
- 10001000 Henesys (Victoria Island, town, exact spot)
- 10001100 Henesys Hunting Ground I (Victoria Island, exact)
- 10001101 Pig Park (Victoria Island, NOT exact -> drawn at Henesys's spot)
- 40000 Snail Hunting Ground I, 1000000 Amherst (Maple Island, exact)
- 90000000 Sample Event Map (no world, no spot)
"""

from sqlalchemy import select

from app.models import Map, Monster, Npc

SNAIL = 100100            # on 40000 (Maple Island) and 10001100 (Victoria Island)
PIG = 1210100             # only on Pig Park (fallback spot)
ORANGE_MUSHROOM = 1210102  # only on the event map (no spot)
PIA = 1011000             # shop NPC in Henesys
HENESYS = 10001000
HHG1 = 10001100
PIG_PARK = 10001101
SNAIL_HG = 40000
EVENT_MAP = 90000000

SPOT_KEYS = {"x", "y", "label", "is_town", "exact", "maps", "monsters", "npcs"}
PING_KEYS = {"world", "x", "y", "map_id", "map_name", "map_names", "exact"}


# ---------- GET /api/world/{world} ----------

def test_world_api_shape(client):
    for world in ("maple-island", "victoria-island"):
        r = client.get(f"/api/world/{world}")
        assert r.status_code == 200
        data = r.json()
        assert set(data) == {"world", "name", "image_url", "width", "height", "spots"}
        assert data["world"] == world
        assert data["image_url"].startswith("/static/img/worldmap/")
        assert data["spots"], world
        for spot in data["spots"]:
            assert set(spot) == SPOT_KEYS
            assert spot["maps"] and all(set(m) == {"id", "name", "exact"} for m in spot["maps"])
            assert all(set(m) == {"id", "name", "level"} for m in spot["monsters"])
            assert all(set(n) == {"id", "name", "has_shop"} for n in spot["npcs"])


def test_unknown_world_404(client):
    assert client.get("/api/world/narnia").status_code == 404


def test_maps_sharing_a_spot_are_grouped(client, db):
    """Pig Park falls back to Henesys's spot, so both maps are in ONE spot labelled Henesys."""
    henesys = db.get(Map, HENESYS)
    spots = client.get("/api/world/victoria-island").json()["spots"]
    at_henesys = [s for s in spots if (s["x"], s["y"]) == (henesys.spot_x, henesys.spot_y)]
    assert len(at_henesys) == 1
    spot = at_henesys[0]
    assert spot["label"] == "Henesys"
    assert spot["is_town"] is True
    assert spot["exact"] is True  # Henesys itself really is there
    map_ids = {m["id"] for m in spot["maps"]}
    assert {HENESYS, PIG_PARK} <= map_ids
    assert next(m for m in spot["maps"] if m["id"] == PIG_PARK)["exact"] is False
    assert any(n["id"] == PIA and n["has_shop"] for n in spot["npcs"])
    assert any(m["id"] == PIG for m in spot["monsters"])
    # No two spots share the same position.
    assert len({(s["x"], s["y"]) for s in spots}) == len(spots)


def test_unplaced_maps_are_not_spots(client):
    all_ids = set()
    for world in ("maple-island", "victoria-island"):
        for spot in client.get(f"/api/world/{world}").json()["spots"]:
            all_ids |= {m["id"] for m in spot["maps"]}
    assert EVENT_MAP not in all_ids


# ---------- GET /api/locate ----------

def test_snail_pings_on_both_islands(client, db):
    data = client.get("/api/locate", params={"monster": SNAIL}).json()
    assert data["kind"] == "monster" and data["id"] == SNAIL and data["name"] == "Snail"
    assert data["worlds"] == ["maple-island", "victoria-island"]
    for ping in data["pings"]:
        assert set(ping) == PING_KEYS
    # The ping coordinates are the seeded spots of the Snail's two maps.
    expected = set()
    for map_id in (SNAIL_HG, HHG1):
        m = db.get(Map, map_id)
        expected.add((m.world, m.spot_x, m.spot_y))
    assert {(p["world"], p["x"], p["y"]) for p in data["pings"]} == expected
    assert all(p["exact"] for p in data["pings"])


def test_fallback_ping_is_not_exact(client, db):
    """Pig only lives on Pig Park, which has no own spot: the ping sits on Henesys, exact=False."""
    henesys = db.get(Map, HENESYS)
    data = client.get("/api/locate", params={"monster": PIG}).json()
    assert len(data["pings"]) == 1
    ping = data["pings"][0]
    assert (ping["world"], ping["x"], ping["y"]) == ("victoria-island", henesys.spot_x, henesys.spot_y)
    assert ping["exact"] is False
    assert ping["map_id"] == PIG_PARK


def test_monster_without_spots_gets_empty_pings(client):
    data = client.get("/api/locate", params={"monster": ORANGE_MUSHROOM}).json()
    assert data["pings"] == [] and data["worlds"] == []
    assert data["unplaced"] == ["Sample Event Map"]


def test_locate_npc_and_map(client, db):
    henesys = db.get(Map, HENESYS)
    npc = client.get("/api/locate", params={"npc": PIA}).json()
    assert [(p["x"], p["y"]) for p in npc["pings"]] == [(henesys.spot_x, henesys.spot_y)]
    m = client.get("/api/locate", params={"map": HENESYS}).json()
    assert m["kind"] == "map" and m["name"] == "Henesys" and m["worlds"] == ["victoria-island"]


def test_locate_unknown_ids_404(client):
    assert client.get("/api/locate", params={"monster": 1}).status_code == 404
    assert client.get("/api/locate", params={"npc": 1}).status_code == 404
    assert client.get("/api/locate", params={"map": 1}).status_code == 404


def test_locate_bad_params_400(client):
    assert client.get("/api/locate").status_code == 400
    assert client.get("/api/locate", params={"monster": "abc"}).status_code == 400
    assert client.get("/api/locate", params={"monster": SNAIL, "npc": PIA}).status_code == 400


# ---------- data added to pages ----------

def test_home_world_maps_data(db):
    """The home page gets both islands (same data as the API), Maple Island first."""
    from app.services import worldmap
    maps = worldmap.all_world_maps(db)
    assert [w["world"] for w in maps] == ["maple-island", "victoria-island"]
    assert all(w["spots"] for w in maps)


def test_monster_found_in(db):
    from app.services import queries
    data = queries.monster_detail(db, SNAIL)
    assert data["has_pings"] is True
    assert {f["map_id"] for f in data["found_in"]} == {SNAIL_HG, HHG1}
    for f in data["found_in"]:
        assert set(f) == {"map_id", "name", "world", "x", "y", "exact"}

    mushroom = queries.monster_detail(db, ORANGE_MUSHROOM)
    assert mushroom["has_pings"] is False
    assert mushroom["found_in"][0]["world"] is None


def test_item_drop_rows_have_monster_id(db):
    from app.models import Drop
    from app.services import queries
    drop = db.scalars(select(Drop).where(Drop.monster_id == SNAIL)).first()
    rows = queries.item_detail(db, drop.item_id)["drops"]
    snail_row = next(r for r in rows if r["monster"]["id"] == SNAIL)
    assert snail_row["monster_id"] == SNAIL
    assert snail_row["has_pings"] is True


def test_npc_ref_has_map(db):
    from app.services import queries
    ref = queries.npc_ref(db.get(Npc, PIA))
    assert ref["map_id"] == HENESYS and ref["world"] == "victoria-island"


def test_every_page_still_200(client, db):
    for path in ("/", "/items", "/monsters", "/shops", "/search?q=snail", "/audit"):
        assert client.get(path).status_code == 200, path
    for monster_id in db.scalars(select(Monster.id)):
        assert client.get(f"/monsters/{monster_id}").status_code == 200, monster_id
    for npc_id in db.scalars(select(Npc.id)):
        assert client.get(f"/npcs/{npc_id}").status_code == 200, npc_id
