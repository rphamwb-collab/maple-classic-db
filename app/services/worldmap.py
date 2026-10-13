"""World map: spots on the island pictures, and "show on map" pings.

Where the data comes from:
- `maps`, `monster_maps`, `npc_maps` tables (filled by data-engineer's scraper from
  OSMS maps.json/monsters.json, matched to the v83 world map spots).
- World pictures: /static/img/worldmap/{world}.png, from the v83 game files via maplestory.io.

Coordinates (x, y) are pixels from the TOP-LEFT corner of the world picture.
Every function returns plain dicts/lists (shapes in docs/api-contract.md, v2.6).
"""

import json
from collections import Counter, defaultdict
from pathlib import Path

from sqlalchemy import select

from app.models import Map, Monster, MonsterMap, Npc, NpcMap, ShopItem

# The two worlds we draw, in the order the site shows them.
WORLDS = {
    "maple-island": "Maple Island",
    "victoria-island": "Victoria Island",
}

IMAGE_DIR = Path(__file__).resolve().parents[1] / "static" / "img" / "worldmap"


# ---------- the world pictures ----------

def world_images():
    """Picture info for each world, from app/static/img/worldmap/worlds.json
    (written by data-engineer's scraper/world_map.py). {} if the file is missing."""
    try:
        return json.loads((IMAGE_DIR / "worlds.json").read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {}


def image_info(world):
    """(image_url, width, height) for one world. Width/height are None if unknown."""
    info = world_images().get(world, {})
    url = info.get("image") or f"/static/img/worldmap/{world}.png"
    return url, info.get("width"), info.get("height")


def has_spot(m):
    """True when a map row has a world and a position on it."""
    return m.world in WORLDS and m.spot_x is not None and m.spot_y is not None


# ---------- spots for one world ----------

def spot_label(maps):
    """Name shown on a spot: the town if one is there, else the most common
    street name, else the first map name."""
    for m in maps:
        if m.is_town:
            return m.name
    streets = Counter(m.street_name for m in maps if m.street_name)
    if streets:
        return streets.most_common(1)[0][0]
    return maps[0].name


def world_map(db, world):
    """Everything to draw one world: picture + clickable spots. None if the world is unknown."""
    if world not in WORLDS:
        return None

    maps = db.scalars(select(Map).where(Map.world == world)).all()
    maps = [m for m in maps if has_spot(m)]

    # Group maps that share the same (x, y) into one spot.
    by_spot = defaultdict(list)
    for m in maps:
        by_spot[(m.spot_x, m.spot_y)].append(m)

    map_ids = [m.id for m in maps]
    spot_of_map = {m.id: (m.spot_x, m.spot_y) for m in maps}

    # Monsters per spot (visible ones only; test mobs stay hidden).
    monsters_at = defaultdict(dict)
    rows = db.execute(
        select(MonsterMap.map_id, Monster)
        .join(Monster, Monster.id == MonsterMap.monster_id)
        .where(MonsterMap.map_id.in_(map_ids))
    ).all()
    for map_id, mob in rows:
        if not getattr(mob, "hidden", False):
            monsters_at[spot_of_map[map_id]][mob.id] = {"id": mob.id, "name": mob.name, "level": mob.level}

    # NPCs per spot, with whether they run a shop.
    shop_npc_ids = set(db.scalars(select(ShopItem.npc_id).distinct()))
    npcs_at = defaultdict(dict)
    rows = db.execute(
        select(NpcMap.map_id, Npc)
        .join(Npc, Npc.id == NpcMap.npc_id)
        .where(NpcMap.map_id.in_(map_ids))
    ).all()
    for map_id, npc in rows:
        npcs_at[spot_of_map[map_id]][npc.id] = {"id": npc.id, "name": npc.name,
                                                "has_shop": npc.id in shop_npc_ids}

    spots = []
    for (x, y), spot_maps in by_spot.items():
        spot_maps.sort(key=lambda m: m.name)
        spots.append({
            "x": x,
            "y": y,
            "label": spot_label(spot_maps),
            "is_town": any(m.is_town for m in spot_maps),
            "exact": any(m.spot_exact for m in spot_maps),
            "maps": [{"id": m.id, "name": m.name, "exact": bool(m.spot_exact)} for m in spot_maps],
            "monsters": sorted(monsters_at[(x, y)].values(), key=lambda r: (r["level"] or 0, r["name"])),
            "npcs": sorted(npcs_at[(x, y)].values(), key=lambda r: r["name"]),
        })
    # Left-to-right, top-to-bottom, so the order is stable.
    spots.sort(key=lambda s: (s["x"], s["y"]))

    image_url, width, height = image_info(world)
    return {
        "world": world,
        "name": WORLDS[world],
        "image_url": image_url,
        "width": width,
        "height": height,
        "spots": spots,
    }


def all_world_maps(db):
    """Both worlds, for the home page."""
    return [world_map(db, w) for w in WORLDS]


# ---------- pings ("show on map") ----------

def pings_for_maps(maps):
    """Turn map rows into pings: one per spot, in world order.
    Returns (worlds, pings, unplaced map names)."""
    by_spot = {}
    unplaced = []
    for m in sorted(maps, key=lambda m: m.name):
        if not has_spot(m):
            unplaced.append(m.name)
            continue
        key = (m.world, m.spot_x, m.spot_y)
        if key not in by_spot:
            by_spot[key] = {"world": m.world, "x": m.spot_x, "y": m.spot_y,
                            "map_id": m.id, "map_name": m.name, "map_names": [], "exact": False}
        ping = by_spot[key]
        ping["map_names"].append(m.name)
        ping["exact"] = ping["exact"] or bool(m.spot_exact)

    world_order = list(WORLDS)
    pings = sorted(by_spot.values(), key=lambda p: (world_order.index(p["world"]), p["x"], p["y"]))
    worlds = [w for w in world_order if any(p["world"] == w for p in pings)]
    return worlds, pings, unplaced


def maps_of_monster(db, monster_id):
    return db.scalars(select(Map).join(MonsterMap, MonsterMap.map_id == Map.id)
                      .where(MonsterMap.monster_id == monster_id)).all()


def maps_of_npc(db, npc_id):
    return db.scalars(select(Map).join(NpcMap, NpcMap.map_id == Map.id)
                      .where(NpcMap.npc_id == npc_id)).all()


def locate(db, kind, thing_id):
    """Pings for one monster, NPC or map. None if that id doesn't exist."""
    if kind == "monster":
        thing = db.get(Monster, thing_id)
        maps = maps_of_monster(db, thing_id) if thing else []
    elif kind == "npc":
        thing = db.get(Npc, thing_id)
        maps = maps_of_npc(db, thing_id) if thing else []
    elif kind == "map":
        thing = db.get(Map, thing_id)
        maps = [thing] if thing else []
    else:
        raise ValueError(f"unknown kind: {kind}")
    if thing is None:
        return None

    worlds, pings, unplaced = pings_for_maps(maps)
    return {"kind": kind, "id": thing_id, "name": thing.name,
            "worlds": worlds, "pings": pings, "unplaced": unplaced}


# ---------- extra data for existing pages ----------

def found_in(db, monster_id):
    """Monster page "Found in": [{map_id, name, world, x, y, exact}], A-Z.
    world/x/y are None for maps that have no spot on our world maps."""
    rows = []
    for m in sorted(maps_of_monster(db, monster_id), key=lambda m: m.name):
        placed = has_spot(m)
        rows.append({
            "map_id": m.id,
            "name": m.name,
            "world": m.world if placed else None,
            "x": m.spot_x if placed else None,
            "y": m.spot_y if placed else None,
            "exact": bool(m.spot_exact) if placed else False,
        })
    return rows


def monsters_with_pings(db, monster_ids):
    """Which of these monsters have at least one map on a world map (one query)."""
    if not monster_ids:
        return set()
    rows = db.execute(
        select(MonsterMap.monster_id, Map)
        .join(Map, Map.id == MonsterMap.map_id)
        .where(MonsterMap.monster_id.in_(list(monster_ids)))
    ).all()
    return {mob_id for mob_id, m in rows if has_spot(m)}

