"""Database reads that build the data for each page.

Every function returns plain dicts/lists (see docs/api-contract.md), so the
templates never depend on database column names.
"""

from collections import defaultdict
from datetime import datetime, timedelta, timezone

from sqlalchemy import func, select

from app.models import DropReport, Item, Monster, Npc, PriceReport
from app.services.stats import format_percent, iqr_bounds, observed_rate, price_stats

HISTORY_DAYS = 30
RECENT_REPORTS = 20


# ---------- small helpers that turn database rows into dicts ----------

def utc_now():
    """Current UTC time without timezone info (matches how the DB stores times)."""
    return datetime.now(timezone.utc).replace(tzinfo=None)


def item_ref(item):
    return {"id": item.id, "name": item.name, "category": item.category}


def monster_ref(monster):
    return {"id": monster.id, "name": monster.name, "level": monster.level}


# Test/unreleased monsters have Monster.hidden = True. They stay out of lists,
# search and counts, but their own page still loads.
# getattr keeps this working on an older database that has no `hidden` column yet.

def is_hidden(monster):
    return bool(getattr(monster, "hidden", False))


def visible_monsters(query):
    """Add "not hidden" to a select(Monster) query (does nothing before the column exists)."""
    if hasattr(Monster, "hidden"):
        query = query.where(Monster.hidden.is_not(True))  # NULL counts as visible
    return query


def npc_ref(npc):
    # Build a readable location like "Henesys Market, Henesys".
    parts = [p for p in (npc.map_name, npc.town) if p]
    return {
        "id": npc.id,
        "name": npc.name,
        "town": npc.town,
        "map_name": npc.map_name,
        "location": ", ".join(parts) or None,
        "note": getattr(npc, "note", None),  # e.g. "Not open in this release"
    }


def source_list(*rows):
    """Collect the unique data sources behind the given rows (for credits)."""
    seen = {}
    for row in rows:
        src = getattr(row, "source", None)
        if src is not None and src.id not in seen:
            seen[src.id] = {
                "name": src.name,
                "url": src.url,
                "last_scraped": src.last_scraped.strftime("%Y-%m-%d") if src.last_scraped else None,
            }
    return list(seen.values())


def observed_for(db, monster_id, item_id):
    """Total up user drop reports for one monster + item pair."""
    kills, drops_seen = db.execute(
        select(func.coalesce(func.sum(DropReport.kills), 0),
               func.coalesce(func.sum(DropReport.drops_seen), 0))
        .where(DropReport.monster_id == monster_id, DropReport.item_id == item_id)
    ).one()
    return observed_rate(kills, drops_seen)


def drop_info(db, drop):
    """Known rate (if any) + observed rate for one Drop row."""
    rate_percent = drop.drop_rate * 100 if drop.drop_rate is not None else None
    return {
        "rate_percent": rate_percent,
        "rate_label": format_percent(rate_percent),  # "unknown" when None
        "rate_source": drop.rate_source,
        "confidence": drop.confidence,
        "observed": observed_for(db, drop.monster_id, drop.item_id),
    }


def ingredient_info(ingredient):
    """One recipe ingredient. item_id is None when the name didn't match an item."""
    return {"item_id": ingredient.item_id, "name": ingredient.item_name, "count": ingredient.count}


def recipe_info(recipe):
    """The parts of a recipe every page shows."""
    return {
        "discipline": recipe.discipline,
        "discipline_level": recipe.discipline_level,
        "req_level": recipe.req_level,
        "meso_cost": recipe.meso_cost,
        "result_count": recipe.result_count,
        "ingredients": [ingredient_info(i) for i in recipe.ingredients],
    }


def quest_info(reward):
    return {
        "quest_name": reward.quest_name,
        "npc_name": reward.npc_name,
        "level_min": reward.level_min,
        "count": reward.count,
        "region": reward.region,
        "reward_type": reward.reward_type,
        "job": reward.job,
    }


# ---------- search ----------

def search(db, q, limit=50):
    """Find items, monsters and NPCs whose name contains q (any case)."""
    q = (q or "").strip()
    results = {"items": [], "monsters": [], "npcs": []}
    if not q:
        return results

    pattern = f"%{q}%"
    items = db.scalars(select(Item).where(Item.name.ilike(pattern)).order_by(Item.name).limit(limit))
    monsters = db.scalars(visible_monsters(select(Monster).where(Monster.name.ilike(pattern)))
                          .order_by(Monster.name).limit(limit))
    npcs = db.scalars(select(Npc).where(Npc.name.ilike(pattern)).order_by(Npc.name).limit(limit))

    results["items"] = [item_ref(i) for i in items]
    results["monsters"] = [monster_ref(m) for m in monsters]
    results["npcs"] = [npc_ref(n) for n in npcs]
    return results


# ---------- prices ----------

def ok_prices_since(db, item_id, since):
    """All non-flagged price reports for an item since a given time."""
    return db.scalars(
        select(PriceReport)
        .where(PriceReport.item_id == item_id,
               PriceReport.status == "ok",
               PriceReport.reported_at >= since)
        .order_by(PriceReport.reported_at.desc())
    ).all()


def item_price_stats(db, item_id):
    """Median/low/high/count for the last 30 days (outliers filtered)."""
    reports = ok_prices_since(db, item_id, utc_now() - timedelta(days=HISTORY_DAYS))
    return price_stats([r.price for r in reports])


def price_history(db, item_id):
    """One entry per day with reports in the last 30 days, oldest first.

    A single day often has only 1-5 reports, too few to spot outliers, so we
    judge each day's prices against the normal range of the whole 30 days.
    """
    reports = ok_prices_since(db, item_id, utc_now() - timedelta(days=HISTORY_DAYS))
    bounds = iqr_bounds([r.price for r in reports])

    by_day = defaultdict(list)
    for r in reports:
        by_day[r.reported_at.strftime("%Y-%m-%d")].append(r.price)

    history = []
    for day in sorted(by_day):
        s = price_stats(by_day[day], bounds)
        if s["count"] == 0:
            continue  # every report that day was an outlier
        history.append({"date": day, "median": s["median"], "low": s["low"],
                        "high": s["high"], "count": s["count"]})
    return history


# ---------- detail pages ----------

def item_detail(db, item_id):
    """Everything the item page needs, or None if the item doesn't exist."""
    item = db.get(Item, item_id)
    if item is None:
        return None

    shops = sorted(
        ({"npc": npc_ref(s.npc), "buy_price": s.buy_price} for s in item.shop_items),
        key=lambda s: s["buy_price"],
    )
    # Test/unreleased monsters are left out of "Dropped by".
    drops = sorted(
        ({"monster": monster_ref(d.monster), **drop_info(db, d)}
         for d in item.drops if not is_hidden(d.monster)),
        key=lambda d: (d["monster"]["level"] or 0, d["monster"]["name"]),
    )
    recent = ok_prices_since(db, item_id, utc_now() - timedelta(days=HISTORY_DAYS))[:RECENT_REPORTS]

    # Crafting recipes that make this item (easiest crafting level first).
    recipes = sorted((recipe_info(r) for r in item.recipes),
                     key=lambda r: (r["discipline_level"] or 0, r["discipline"]))
    # Quests that give this item (lowest level first; unknown level last).
    quests = sorted((quest_info(q) for q in item.quest_rewards),
                    key=lambda q: (q["level_min"] is None, q["level_min"] or 0, q["quest_name"]))

    # Recipes that use this item as an ingredient, with what they make.
    used_in = []
    for ingredient in item.used_in:
        recipe = ingredient.recipe
        used_in.append({
            "result": item_ref(recipe.output_item),
            "count": ingredient.count,  # how many of THIS item the recipe needs
            **recipe_info(recipe),
        })
    used_in.sort(key=lambda u: u["result"]["name"])

    return {
        "item": {
            "id": item.id,
            "name": item.name,
            "category": item.category,
            "sub_type": item.sub_type,
            "level_req": item.level_req,
            "job": item.job,
            "equip_slot": item.equip_slot,
            "weapon_type": item.weapon_type,
            "jobs": list(item.jobs or []),
            "stats": item.stats or {},
            "description": item.description,
            "npc_sell_price": item.npc_sell_price,
            "icon_url": item.icon_url,
        },
        # True = we know the NPC price. None = unknown (NULL in the DB means
        # "no source had a price", NOT "can't be sold").
        "sellable": True if item.npc_sell_price is not None else None,
        "how_to_get": {"shops": shops, "drops": drops, "recipes": recipes, "quests": quests},
        "used_in": used_in,
        "shops": shops,
        "drops": drops,
        "price_stats": item_price_stats(db, item_id),
        "recent_reports": [
            {"price": r.price, "quantity": r.quantity, "world": r.world,
             "reported_at": r.reported_at.strftime("%Y-%m-%d %H:%M")}
            for r in recent
        ],
        "sources": source_list(item, *item.shop_items, *item.drops, *item.recipes, *item.quest_rewards),
    }


def monster_detail(db, monster_id):
    """Everything the monster page needs, or None if not found."""
    monster = db.get(Monster, monster_id)
    if monster is None:
        return None

    drops = sorted(
        ({"item": item_ref(d.item), **drop_info(db, d)} for d in monster.drops),
        key=lambda d: d["item"]["name"],
    )
    return {
        "monster": {
            "id": monster.id,
            "name": monster.name,
            "level": monster.level,
            "hp": monster.hp,
            "exp": monster.exp,
            "maps": monster.maps or [],
            "hidden": is_hidden(monster),  # True -> page shows "Test/unreleased monster"
            "note": getattr(monster, "note", None),
        },
        "drops": drops,
        "sources": source_list(monster, *monster.drops),
    }


def npc_detail(db, npc_id):
    """Everything the NPC shop page needs, or None if not found."""
    npc = db.get(Npc, npc_id)
    if npc is None:
        return None

    shop = sorted(
        ({"item": item_ref(s.item), "buy_price": s.buy_price} for s in npc.shop_items),
        key=lambda s: s["item"]["name"],
    )
    return {
        "npc": npc_ref(npc),
        "shop": shop,
        "sources": source_list(npc, *npc.shop_items),
    }
