"""Data audit: find gaps and disagreements in our data.

Each check is one function that takes (db, limit=None) and returns
(rows, count):
  - count = how many problems there are in total
  - rows  = plain dicts describing them (only the first `limit` if given)

The /audit page and the CLI report (scraper/audit.py) both use these.
Row shapes are documented in docs/api-contract.md ("v2.5: Data audit").
"""

from sqlalchemy import exists, func, or_, select

from app.models import (AuditFinding, Drop, DropReport, Item, Monster, Npc, QuestReward, Recipe, ShopItem,
                        Source)
from app.services.queries import drop_info, item_ref, monster_ref, npc_ref, observed_for, visible_monsters
from app.services.stats import is_player_confirmed

# MapleStory Quest home page (same as scraper/sources/msquest.py BASE_URL).
MSQ_URL = "https://maplestory.quest"

# Friendly names for the audit_findings "check" values.
FINDING_LABELS = {
    "name_mismatch": "Name differs",
    "unknown_item_ref": "Unknown item ID",
    "npc_shop_rejected": "Shop page skipped",
    "shop_correction": "Shop data corrected",  # a hand fix in scraper/corrections.py
}

# A rate mismatch needs at least this many reported kills to be trusted...
MISMATCH_MIN_KILLS = 100
# ...and the player rate must be this many times higher or lower than ours.
MISMATCH_FACTOR = 3
# Seeing zero of a rare drop is normal. Only call "zero seen" a mismatch when
# we would have expected at least this many drops (kills x listed rate).
MISMATCH_MIN_EXPECTED_DROPS = 3

# Every check, in the order the page shows them.
CHECKS = [
    {"slug": "no-source", "label": "No way to get it",
     "description": "Items with no monster drop, shop, crafting recipe or quest reward."},
    {"slug": "mobs-no-drops", "label": "Monsters with no drops",
     "description": "Monsters (not test/unreleased ones) that have no drops listed."},
    {"slug": "unknown-rates", "label": "Unknown or old rates",
     "description": "Drops with no known rate, or a rate estimated from the older v83 version."},
    {"slug": "source-mismatch", "label": "Sources disagree",
     "description": "Places where the game client data (OSMS) and MapleStory Quest disagree."},
    {"slug": "player-confirmed", "label": "Player-confirmed",
     "description": "Older-version drops that players have now seen drop in Classic."},
    {"slug": "rate-mismatch", "label": "Rate mismatch",
     "description": f"At least {MISMATCH_MIN_KILLS} kills reported and the player rate is more than "
                    f"{MISMATCH_FACTOR}x higher or lower than ours."},
    {"slug": "reported-not-listed", "label": "Reported but not listed",
     "description": "Players reported a drop that is not in our drop table (queued for review)."},
]


# ---------- small helpers ----------

def _cut(rows, limit):
    """Return the first `limit` rows (all of them when limit is None)."""
    return rows if limit is None else rows[:limit]


def _drop_row(db, drop):
    """One drop as a dict: monster, item and all the rate fields the item page uses.

    It has the same keys as an item-page drop, so the template's rate_pill(row)
    and observed_pill(row.observed) work on it directly.
    """
    return {"monster": monster_ref(drop.monster), "item": item_ref(drop.item), **drop_info(db, drop)}


def _report_totals():
    """A subquery: total kills and drops seen per (monster, item) from player reports.

    Reports with no item (item_id None) are left out.
    """
    return (
        select(DropReport.monster_id, DropReport.item_id,
               func.sum(DropReport.kills).label("kills"),
               func.sum(DropReport.drops_seen).label("drops_seen"))
        .where(DropReport.item_id.is_not(None))
        .group_by(DropReport.monster_id, DropReport.item_id)
        .subquery()
    )


# ---------- check 1: no way to get it ----------

def no_source_items(db, limit=None):
    """Items with no drop (from a visible monster), shop, recipe or quest reward."""
    # A drop only counts when the monster is a real, visible one.
    dropped = (select(Drop.id).join(Monster, Drop.monster_id == Monster.id)
               .where(Drop.item_id == Item.id))
    dropped = visible_monsters(dropped)
    sold = select(ShopItem.id).where(ShopItem.item_id == Item.id)
    crafted = select(Recipe.id).where(Recipe.output_item_id == Item.id)
    quest = select(QuestReward.id).where(QuestReward.item_id == Item.id)

    condition = (~exists(dropped) & ~exists(sold) & ~exists(crafted) & ~exists(quest))
    count = db.scalar(select(func.count()).select_from(Item).where(condition))

    query = select(Item).where(condition).order_by(Item.name, Item.id)
    if limit is not None:
        query = query.limit(limit)
    rows = [{"item": item_ref(item)} for item in db.scalars(query)]
    return rows, count


# ---------- check 2: monsters with no drops ----------

def mobs_without_drops(db, limit=None):
    """Visible (not hidden) monsters that have zero drop rows."""
    has_drop = select(Drop.id).where(Drop.monster_id == Monster.id)
    base = visible_monsters(select(Monster).where(~exists(has_drop)))

    count = db.scalar(select(func.count()).select_from(base.subquery()))
    query = base.order_by(Monster.level, Monster.name)
    if limit is not None:
        query = query.limit(limit)
    rows = [{"monster": monster_ref(m)} for m in db.scalars(query)]
    return rows, count


# ---------- check 3: unknown or old rates ----------

def unknown_rates(db, limit=None):
    """Drops (from visible monsters) with no rate, or an older-version 'estimated' rate."""
    base = (select(Drop).join(Monster, Drop.monster_id == Monster.id).join(Item, Drop.item_id == Item.id)
            .where(or_(Drop.drop_rate.is_(None), Drop.confidence == "estimated")))
    base = visible_monsters(base)

    count = db.scalar(select(func.count()).select_from(base.subquery()))
    query = base.order_by(Monster.level, Monster.name, Item.name)
    if limit is not None:
        query = query.limit(limit)

    rows = []
    for drop in db.scalars(query):
        row = _drop_row(db, drop)
        row["reason"] = "Unknown rate" if drop.drop_rate is None else "Older-version estimate"
        rows.append(row)
    return rows, count


# ---------- check 4: OSMS vs MapleStory Quest disagreements ----------

def source_mismatches(db, limit=None):
    """Rows of the audit_findings table, written by `scraper.run` (rebuilt every run)."""
    count = db.scalar(select(func.count()).select_from(AuditFinding))
    query = select(AuditFinding).order_by(AuditFinding.check, AuditFinding.id)
    if limit is not None:
        query = query.limit(limit)

    rows = []
    for f in db.scalars(query):
        # No relationships on this table, so look each thing up by its id.
        # item_id may point at an item we don't have (that's the "unknown_item_ref" problem).
        item = db.get(Item, f.item_id) if f.item_id is not None else None
        monster = db.get(Monster, f.monster_id) if f.monster_id is not None else None
        npc = db.get(Npc, f.npc_id) if f.npc_id is not None else None
        rows.append({
            "kind": f.check,
            "kind_label": FINDING_LABELS.get(f.check, f.check),
            "item": item_ref(item) if item else None,
            "item_id": f.item_id,
            "monster": monster_ref(monster) if monster else None,
            "npc": npc_ref(npc) if npc else None,
            "detail": f.detail,
            "source_url": _msq_url(f),
        })
    return rows, count


def _msq_url(finding):
    """Link to the MapleStory Quest page the finding came from (a link only; we never fetch it)."""
    if finding.monster_id is not None:
        return f"{MSQ_URL}/monsters/{finding.monster_id}"
    if finding.npc_id is not None:
        return f"{MSQ_URL}/npcs/{finding.npc_id}"
    if finding.item_id is not None:
        return f"{MSQ_URL}/items/{finding.item_id}"
    return None


# ---------- check 5: player-confirmed drops ----------

def player_confirmed(db, limit=None):
    """'estimated' drops that players reported seeing (drops_seen > 0).

    Worked out from drop_reports every time, so it survives data refreshes.
    """
    totals = _report_totals()
    query = (select(Drop)
             .join(totals, (totals.c.monster_id == Drop.monster_id) & (totals.c.item_id == Drop.item_id))
             .where(Drop.confidence == "estimated", totals.c.drops_seen > 0))
    rows = [_drop_row(db, drop) for drop in db.scalars(query)]
    # Double-check with the same rule the item page uses.
    rows = [r for r in rows if is_player_confirmed(r["confidence"], r["observed"]["drops_seen"])]
    rows.sort(key=lambda r: (r["monster"]["name"], r["item"]["name"]))
    return _cut(rows, limit), len(rows)


# ---------- check 6: rate mismatch ----------

def mismatch_ratio(listed_percent, observed):
    """Compare a player-observed rate with our listed rate.

    Returns (ratio, direction) when they are more than MISMATCH_FACTOR apart,
    or None when they roughly agree (or there isn't enough data).
    ratio = observed / listed, so 4.0 means players see it 4x as often.
    """
    if listed_percent is None or listed_percent <= 0:
        return None  # nothing to compare against
    if observed["kills"] < MISMATCH_MIN_KILLS or observed["rate_percent"] is None:
        return None  # too few kills to judge

    ratio = observed["rate_percent"] / listed_percent
    if ratio > MISMATCH_FACTOR:
        return ratio, "higher"
    if ratio < 1 / MISMATCH_FACTOR:
        if observed["drops_seen"] == 0:
            # Seeing none is only strange if we expected a few.
            expected = observed["kills"] * listed_percent / 100
            if expected < MISMATCH_MIN_EXPECTED_DROPS:
                return None
        return ratio, "lower"
    return None


def rate_mismatches(db, limit=None):
    """Drops with a known rate where players see it more than 3x more or less often."""
    totals = _report_totals()
    query = (select(Drop)
             .join(totals, (totals.c.monster_id == Drop.monster_id) & (totals.c.item_id == Drop.item_id))
             .where(Drop.drop_rate.is_not(None), totals.c.kills >= MISMATCH_MIN_KILLS))

    rows = []
    for drop in db.scalars(query):
        row = _drop_row(db, drop)
        result = mismatch_ratio(row["rate_percent"], row["observed"])
        if result is None:
            continue
        row["ratio"], row["direction"] = result
        rows.append(row)

    # Furthest off first (4x higher and 4x lower count the same).
    def how_far_off(r):
        return r["ratio"] if r["ratio"] >= 1 else (1 / r["ratio"] if r["ratio"] > 0 else float("inf"))
    rows.sort(key=how_far_off, reverse=True)
    return _cut(rows, limit), len(rows)


# ---------- check 7: reported but not in our drop table ----------

def reported_not_listed(db, limit=None):
    """Drop reports for a (monster, item) pair that has no Drop row.

    Note: the report form only accepts known drops, so this is normally empty.
    It fills up if a data refresh removes a drop that players reported on.
    """
    totals = _report_totals()
    listed = select(Drop.id).where(Drop.monster_id == totals.c.monster_id, Drop.item_id == totals.c.item_id)
    pairs = db.execute(select(totals.c.monster_id, totals.c.item_id).where(~exists(listed))).all()

    rows = []
    for monster_id, item_id in pairs:
        monster, item = db.get(Monster, monster_id), db.get(Item, item_id)
        if monster is None or item is None:
            continue  # the monster or item itself is gone
        rows.append({"monster": monster_ref(monster), "item": item_ref(item),
                     "observed": observed_for(db, monster_id, item_id)})
    rows.sort(key=lambda r: (r["monster"]["name"], r["item"]["name"]))
    return _cut(rows, limit), len(rows)


# ---------- all checks together ----------

CHECK_FUNCTIONS = {
    "no-source": no_source_items,
    "mobs-no-drops": mobs_without_drops,
    "unknown-rates": unknown_rates,
    "source-mismatch": source_mismatches,
    "player-confirmed": player_confirmed,
    "rate-mismatch": rate_mismatches,
    "reported-not-listed": reported_not_listed,
}


def run_check(db, slug, limit=None):
    """Run one check by its slug. Raises KeyError for an unknown slug."""
    return CHECK_FUNCTIONS[slug](db, limit)


def summary(db):
    """{slug: count} for every check."""
    return {c["slug"]: run_check(db, c["slug"], limit=0)[1] for c in CHECKS}


def last_run(db):
    """When the data was last refreshed ("YYYY-MM-DD"), or None."""
    when = db.scalar(select(func.max(Source.last_scraped)))
    return when.strftime("%Y-%m-%d") if when else None


def audit_page(db, check=""):
    """Everything the /audit page needs (see docs/api-contract.md).

    Overview (no check): every check with up to 10 rows.
    One check selected: just that check with up to 500 rows.
    """
    active = check if check in CHECK_FUNCTIONS else ""
    counts = summary(db)
    checks = [{**c, "count": counts[c["slug"]], "url": f"/audit?check={c['slug']}",
               "active": c["slug"] == active} for c in CHECKS]

    sections = []
    for c in checks:
        if active and c["slug"] != active:
            continue
        rows, count = run_check(db, c["slug"], limit=500 if active else 10)
        more = c["url"] if (not active and count > len(rows)) else None
        sections.append({"slug": c["slug"], "label": c["label"], "description": c["description"],
                         "count": count, "rows": rows, "shown": len(rows), "more_url": more})

    return {"active": active, "checks": checks, "all_url": "/audit",
            "sections": sections, "last_run": last_run(db)}
