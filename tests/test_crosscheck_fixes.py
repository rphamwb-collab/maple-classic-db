"""Tests for the fixes from the MeowDB cross-check (v2.4):
unknown sell prices, older-version drop wording, hidden test monsters, and notes.

The hidden/note database tests skip themselves until data-engineer adds
Monster.hidden, Monster.note and Npc.note to app/models.py.
"""

import pytest
from fastapi import Request
from sqlalchemy import select

from app.main import app, templates
from app.models import Item, Monster, Npc
from app.services import browse, queries

HAS_HIDDEN = hasattr(Monster, "hidden")
HAS_NOTES = hasattr(Monster, "note") and hasattr(Npc, "note")


def render(name, **context):
    """Render a template with made-up data (no database). The pages call
    url_for, so they need a small fake request that knows the app's routes."""
    scope = {"type": "http", "method": "GET", "path": "/", "query_string": b"", "headers": [],
             "scheme": "http", "server": ("testserver", 80), "root_path": "",
             "app": app, "router": app.router}
    return templates.get_template(name).render(request=Request(scope), **context)


# ---------- 1. sell price: NULL means unknown, not "can't sell" ----------

def test_unknown_sell_price(db):
    unknown = db.scalar(select(Item).where(Item.npc_sell_price.is_(None)))
    assert unknown is not None, "sample data should have an item with no NPC sell price"
    assert queries.item_detail(db, unknown.id)["sellable"] is None
    known = db.scalar(select(Item).where(Item.npc_sell_price.is_not(None)))
    assert queries.item_detail(db, known.id)["sellable"] is True


def test_item_page_shows_unknown_not_cant_sell(client, db):
    unknown = db.scalar(select(Item).where(Item.npc_sell_price.is_(None)))
    r = client.get(f"/items/{unknown.id}")
    assert r.status_code == 200
    assert "NPC sell price: Unknown" in r.text
    assert "Can't be sold to NPCs" not in r.text


# ---------- 2. older-version drop wording ----------

def test_estimated_drops_say_older_version(client, db):
    snail = db.scalar(select(Monster).where(Monster.name == "Snail"))
    drops = queries.monster_detail(db, snail.id)["drops"]
    assert any(d["confidence"] == "estimated" for d in drops), "sample snail drops should be estimated"
    r = client.get(f"/monsters/{snail.id}")
    assert "Older-version estimate. May not drop in Classic." in r.text
    assert "Older-version estimate</span>" in r.text  # the pill next to the rate


# ---------- 3. notes and the hidden label (template only, always runs) ----------

def test_notes_render_in_templates():
    npc = {"id": 1, "name": "Luma", "town": None, "map_name": None, "location": None,
           "note": "Not open in this release"}
    html = render("npc.html", npc=npc, shop=[], sources=[])
    assert "Not open in this release" in html

    shops = render("shops.html", towns=[{"town": "Other", "shop_count": 1,
                                         "shops": [{"npc": npc, "item_count": 13}]}], total_shops=1)
    assert "Not open in this release" in shops

    monster = {"id": 9, "name": "Test", "level": 1, "hp": 1, "exp": 1, "maps": [],
               "hidden": True, "note": "Invincible jump quest obstacle"}
    html = render("monster.html", monster=monster, drops=[], worlds=[], sources=[])
    assert "Test/unreleased monster" in html and "Invincible jump quest obstacle" in html


def test_no_notice_when_no_note():
    npc = {"id": 1, "name": "Pan", "town": "Henesys", "map_name": None, "location": "Henesys", "note": None}
    assert 'class="notice"' not in render("npc.html", npc=npc, shop=[], sources=[])


# ---------- 4. hidden monsters (needs the new column) ----------

@pytest.fixture
def hidden_monster(db):
    """Mark one sample monster as hidden for a test, then put it back."""
    if not HAS_HIDDEN:
        pytest.skip("Monster.hidden not added yet")
    monster = db.scalar(select(Monster).where(Monster.name == "Snail"))
    old = monster.hidden
    monster.hidden = True
    db.commit()
    yield monster
    monster.hidden = old
    db.commit()


def test_hidden_monster_left_out_of_lists(client, db, hidden_monster):
    listed = [m["id"] for m in browse.browse_monsters(db)["monsters"]]
    assert hidden_monster.id not in listed
    found = [m["id"] for m in queries.search(db, hidden_monster.name)["monsters"]]
    assert hidden_monster.id not in found
    field = [b["monster"]["id"] for b in browse.home_monster_field(db)["bands"]]
    assert hidden_monster.id not in field
    assert browse.home_counts(db)["monsters"] == len(listed)
    assert browse.home_monster_field(db)["total"] == len(listed)
    # The /monsters page and search suggestions agree.
    assert hidden_monster.id not in [m["id"] for m in client.get("/monsters").context["monsters"]]
    suggestions = client.get("/api/search", params={"q": hidden_monster.name, "format": "json"}).json()
    assert hidden_monster.id not in [m["id"] for m in suggestions["monsters"]]


def test_hidden_monster_page_still_loads(client, hidden_monster):
    r = client.get(f"/monsters/{hidden_monster.id}")
    assert r.status_code == 200
    assert r.context["monster"]["hidden"] is True
    assert "Test/unreleased monster" in r.text


# ---------- 5. notes from the database (needs the new columns) ----------

@pytest.mark.skipif(not HAS_NOTES, reason="Monster.note / Npc.note not added yet")
def test_db_notes_rendered(client, db):
    monster = db.scalar(select(Monster).where(Monster.name == "Snail"))
    npc = db.scalar(select(Npc).where(Npc.shop_items.any()))
    old_m, old_n = monster.note, npc.note
    monster.note, npc.note = "Monster test note", "NPC test note"
    db.commit()
    try:
        assert "Monster test note" in client.get(f"/monsters/{monster.id}").text
        assert "NPC test note" in client.get(f"/npcs/{npc.id}").text
        assert "NPC test note" in client.get("/shops").text
    finally:
        monster.note, npc.note = old_m, old_n
        db.commit()
