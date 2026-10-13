"""Tests for the data audit (app/services/audit.py) and the /audit page.

They use the shared sample database (tests/conftest.py). Tests that need
extra rows add them and delete them again afterwards, so other tests still
see the normal sample data.
"""

import pytest
from sqlalchemy import delete

from app.models import Drop, DropReport, Item, Monster
from app.services import audit
from app.services.stats import is_player_confirmed

# IDs used only by these tests (not in the sample data).
TEST_MOB = 9_990_001       # visible monster with no drops
HIDDEN_MOB = 9_990_002     # hidden test monster with no drops
TEST_ITEM = 4_999_001      # item only "dropped" by the hidden monster


@pytest.fixture
def extra_rows(db):
    """Add a few rows the sample data doesn't have, then remove them after the test."""
    db.add_all([
        Monster(id=TEST_MOB, name="Audit Test Mob", level=99, source_id=1),
        Monster(id=HIDDEN_MOB, name="Audit Hidden Mob", level=99, hidden=True, source_id=1),
        Item(id=TEST_ITEM, name="Audit Test Item", category="etc", source_id=1),
    ])
    db.flush()
    db.add(Drop(monster_id=HIDDEN_MOB, item_id=TEST_ITEM, drop_rate=None, source_id=1))
    # Reports: one for a pair we DON'T list, and 1000 Octopus kills with
    # 120 Mana Elixirs (listed at 3%, so 12% is 4x higher = a mismatch).
    # Octopus + Mana Elixir has no sample reports, so the totals are exactly these.
    db.add_all([
        DropReport(monster_id=TEST_MOB, item_id=TEST_ITEM, kills=50, drops_seen=2, world="Scania"),
        DropReport(monster_id=1120100, item_id=2000006, kills=1000, drops_seen=120, world="Scania"),
    ])
    db.commit()
    yield
    db.execute(delete(DropReport).where(DropReport.monster_id == TEST_MOB))
    db.execute(delete(DropReport).where(DropReport.monster_id == 1120100, DropReport.item_id == 2000006))
    db.execute(delete(Drop).where(Drop.monster_id == HIDDEN_MOB))
    db.execute(delete(Monster).where(Monster.id.in_([TEST_MOB, HIDDEN_MOB])))
    db.execute(delete(Item).where(Item.id == TEST_ITEM))
    db.commit()


def ids(rows, key):
    return [r[key]["id"] for r in rows]


def pairs(rows):
    return {(r["monster"]["id"], r["item"]["id"]) for r in rows}


# ---------- pure helpers ----------

def test_is_player_confirmed():
    assert is_player_confirmed("estimated", 1) is True
    assert is_player_confirmed("estimated", 0) is False
    assert is_player_confirmed("verified", 5) is False
    assert is_player_confirmed("unverified", 5) is False


def observed(kills, seen):
    return {"kills": kills, "drops_seen": seen, "rate_percent": seen / kills * 100 if kills else None}


def test_mismatch_ratio_rules():
    # Listed 1%: players see 4% over 200 kills -> 4x higher.
    assert audit.mismatch_ratio(1.0, observed(200, 8)) == (4.0, "higher")
    # Players see 0.25% -> 4x lower.
    ratio, direction = audit.mismatch_ratio(1.0, observed(400, 1))
    assert direction == "lower" and ratio == pytest.approx(0.25)
    # Within 3x either way -> fine.
    assert audit.mismatch_ratio(1.0, observed(200, 4)) is None   # 2x
    assert audit.mismatch_ratio(1.0, observed(300, 1)) is None   # 1/3x exactly is not "more than"
    # Too few kills, or no listed rate -> can't judge.
    assert audit.mismatch_ratio(1.0, observed(99, 50)) is None
    assert audit.mismatch_ratio(None, observed(500, 5)) is None
    # Zero seen of a rare drop: normal unless we expected at least 3.
    assert audit.mismatch_ratio(0.05, observed(1000, 0)) is None          # expected 0.5
    assert audit.mismatch_ratio(1.0, observed(1000, 0)) == (0.0, "lower")  # expected 10


# ---------- each check on the sample data ----------

def test_no_source_items(db):
    rows, count = audit.no_source_items(db)
    # Sample items with no drop, shop, recipe or quest (checked by hand in seed_sample.py).
    assert sorted(ids(rows, "item")) == [1002043, 1402000, 3010000]
    assert count == 3
    # Items with a way to get them are not listed.
    assert 1002008 not in ids(rows, "item")  # Brown Bamboo Hat: shop + recipe + drop
    assert 2043001 not in ids(rows, "item")  # quest reward + drop


def test_no_source_ignores_hidden_monster_drops(db, extra_rows):
    rows, _ = audit.no_source_items(db)
    assert TEST_ITEM in ids(rows, "item")  # only dropped by a hidden test mob


def test_mobs_without_drops(db, extra_rows):
    rows, count = audit.mobs_without_drops(db)
    assert ids(rows, "monster") == [TEST_MOB]  # every sample mob has drops; hidden mob skipped
    assert count == 1


def test_unknown_rates(db):
    rows, count = audit.unknown_rates(db)
    # Every sample drop is either unknown (None) or "estimated".
    assert count == 33 and len(rows) == 33
    reasons = {(r["monster"]["id"], r["item"]["id"]): r["reason"] for r in rows}
    assert reasons[(100100, 1040002)] == "Unknown rate"
    assert reasons[(100100, 4000019)] == "Older-version estimate"
    # Rows have what the rate pills need.
    assert {"rate_percent", "rate_label", "confidence", "observed"} <= rows[0].keys()


def test_limit_cuts_rows_but_not_count(db):
    rows, count = audit.unknown_rates(db, limit=5)
    assert len(rows) == 5 and count == 33


def test_source_mismatches(db):
    rows, count = audit.source_mismatches(db)
    assert count == 4  # seed_sample adds one row per kind
    kinds = {r["kind"] for r in rows}
    assert kinds == {"name_mismatch", "unknown_item_ref", "npc_shop_rejected", "shop_correction"}
    assert all(r["kind_label"] != r["kind"] for r in rows)  # every kind has a friendly label
    for r in rows:
        assert r["detail"] and r["kind_label"]
        assert r["source_url"].startswith("https://maplestory.quest/")
    unknown = next(r for r in rows if r["kind"] == "unknown_item_ref")
    assert unknown["item"] is None and unknown["item_id"] is not None  # item isn't in our table
    rejected = next(r for r in rows if r["kind"] == "npc_shop_rejected")
    assert rejected["npc"]["id"] == 1011000
    corrected = next(r for r in rows if r["kind"] == "shop_correction")
    assert corrected["npc"]["id"] == 1011000 and corrected["item"]["id"] == 2000001


def test_player_confirmed(db):
    rows, count = audit.player_confirmed(db)
    assert count == len(rows) > 0
    for r in rows:
        assert r["confidence"] == "estimated" and r["observed"]["drops_seen"] > 0
        assert r["player_confirmed"] is True
    # Unknown-rate drops are never "estimated", so never listed here.
    assert (100100, 1040002) not in pairs(rows)


def test_rate_mismatch(db, extra_rows):
    rows, count = audit.rate_mismatches(db)
    octopus = [r for r in rows if (r["monster"]["id"], r["item"]["id"]) == (1120100, 2000006)]
    assert len(octopus) == 1
    row = octopus[0]
    assert row["direction"] == "higher" and row["ratio"] == pytest.approx(4.0)
    assert row["observed"]["kills"] == 1000
    assert count == len(rows)


def test_reported_not_listed(db, extra_rows):
    rows, count = audit.reported_not_listed(db)
    assert pairs(rows) == {(TEST_MOB, TEST_ITEM)}
    assert count == 1
    assert rows[0]["observed"]["kills"] == 50


def test_reported_not_listed_empty_on_sample(db):
    # The report form only accepts known drops, so the sample data has none.
    assert audit.reported_not_listed(db) == ([], 0)


def test_summary_matches_checks(db):
    counts = audit.summary(db)
    assert list(counts) == [c["slug"] for c in audit.CHECKS]
    for slug, n in counts.items():
        assert audit.run_check(db, slug)[1] == n


def test_run_check_unknown_slug(db):
    with pytest.raises(KeyError):
        audit.run_check(db, "nope")


# ---------- page data and routes ----------

def test_audit_page_overview(db):
    data = audit.audit_page(db)
    assert data["active"] == ""
    assert len(data["checks"]) == len(data["sections"]) == 7
    unknown = next(s for s in data["sections"] if s["slug"] == "unknown-rates")
    assert unknown["shown"] == 10 and unknown["more_url"] == "/audit?check=unknown-rates"


def test_audit_page_one_check(db):
    data = audit.audit_page(db, "unknown-rates")
    assert data["active"] == "unknown-rates"
    assert [s["slug"] for s in data["sections"]] == ["unknown-rates"]
    assert data["sections"][0]["shown"] == 33 and data["sections"][0]["more_url"] is None
    assert [c["active"] for c in data["checks"]].count(True) == 1


def test_audit_page_unknown_check_shows_overview(db):
    assert audit.audit_page(db, "bogus")["active"] == ""


@pytest.mark.parametrize("url", ["/audit"] + [f"/audit?check={c['slug']}" for c in audit.CHECKS]
                         + ["/audit?check=bogus"])
def test_audit_route_200(client, url):
    assert client.get(url).status_code == 200


def test_item_and_monster_drops_have_player_confirmed(db):
    from app.services import queries
    item = queries.item_detail(db, 4000002)  # Pig's Ribbon: estimated + reported by players
    pig = next(d for d in item["drops"] if d["monster"]["id"] == 1210100)
    assert pig["player_confirmed"] == (pig["observed"]["drops_seen"] > 0)
    monster = queries.monster_detail(db, 100100)
    for d in monster["drops"]:
        assert d["player_confirmed"] == is_player_confirmed(d["confidence"], d["observed"]["drops_seen"])
