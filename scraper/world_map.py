"""World map pictures and "spots" (where each map sits on the world map).

    .venv\\Scripts\\python -m scraper.world_map

What it does:
1. Downloads (once) from maplestory.io, which serves the GMS v83 game files:
   - each world map picture (Maple Island, Victoria Island, whole-world overview)
   - each picture's list of spots: a pixel position + the v83 map IDs at that spot
   - the names of every v83 map (one request)
   Everything is cached in data/raw/worldmap/, so running again makes no new requests.
2. Saves the pictures to app/static/img/worldmap/{world}.png plus worlds.json (sizes).
3. Matches each Classic map (data/raw/osms/maps.json) to a spot and prints the match rate.

Why matching is needed: Classic map IDs differ from v83 ones (Henesys is 10001000 in
Classic, 100000000 in v83). So we match by (map name, street name) instead.
Maps without their own spot use the spot of the nearest map you can walk to (through
portals), or else the town they return to; both are marked spot_exact=False.

scraper.run calls `map_rows(cache_only=True)`, which never goes online.
Game art (c) Nexon. Credit: "World map from the v83 game files via maplestory.io".
"""
import json
import time
from pathlib import Path

import httpx

ROOT = Path(__file__).resolve().parents[1]
CACHE = ROOT / "data" / "raw" / "worldmap"
OUT_DIR = ROOT / "app" / "static" / "img" / "worldmap"
OSMS_MAPS = ROOT / "data" / "raw" / "osms" / "maps.json"

API = "https://maplestory.io/api"

# our world key -> (title, v83 world map file)
WORLDS = {
    "maple-island": ("Maple Island", "WorldMap000.img"),
    "victoria-island": ("Victoria Island", "WorldMap010.img"),
    "world": ("Maple World", "WorldMap.img"),   # overview picture only; no spots used
}
# Worlds whose spots we match maps to (the overview's spots point at whole islands).
SPOT_WORLDS = ("maple-island", "victoria-island")

# OSMS region -> our world key (used when a map has no spot at all)
REGION_WORLD = {"Maple Island": "maple-island", "Victoria Island": "victoria-island"}

_client = None


class NotCached(Exception):
    """Raised in cache-only mode when a file was never downloaded."""


def fetch(path: str, binary: bool = False, cache_only: bool = False):
    """GET {API}/{path}, saved to disk so each URL is only ever downloaded once.
    (Same pattern as scraper/town_backgrounds.py.) A 404 is cached as None / b""."""
    global _client
    name = path.replace("/", "_") + (".png" if binary else ".json")
    cached = CACHE / name
    if cached.exists():
        return cached.read_bytes() if binary else json.loads(cached.read_text(encoding="utf-8"))
    if cache_only:
        raise NotCached(path)
    if _client is None:
        _client = httpx.Client(timeout=60, headers={"User-Agent": "maple-classic-db (fan site)"})
    time.sleep(0.2)   # be polite to maplestory.io
    # Retry server hiccups (502/503...), waiting longer each time.
    for wait in (5, 20, 60, None):
        resp = _client.get(f"{API}/{path}")
        if resp.status_code < 500 or wait is None:
            break
        print(f"  server busy ({resp.status_code}), retrying in {wait}s...", flush=True)
        time.sleep(wait)
    if resp.status_code == 404:
        data = b"" if binary else None
    else:
        resp.raise_for_status()
        data = resp.content if binary else resp.json()
    CACHE.mkdir(parents=True, exist_ok=True)
    if binary:
        cached.write_bytes(data)
    else:
        cached.write_text(json.dumps(data), encoding="utf-8")
    return data


def wz(path: str, cache_only: bool = False) -> dict:
    """One node of the game files: {"children": [...], "value": ...}."""
    return fetch(f"wz/GMS/83/Map/WorldMap/{path}", cache_only=cache_only) or {}


def normalise(text: str | None) -> str:
    """Compare names loosely: lowercase, trimmed, single spaces."""
    return " ".join((text or "").lower().split())


# ---------- reading the game files ----------

def world_info(key: str, cache_only: bool = False) -> dict:
    """Picture origin + list of spots for one world map.
    Each spot: {"x", "y"} in pixels from the picture's TOP-LEFT, "type", "v83_ids"."""
    img = WORLDS[key][1]
    origin = wz(f"{img}/BaseImg/0/origin", cache_only).get("value") or {"x": 0, "y": 0}
    spots = []
    if key in SPOT_WORLDS:
        for n in sorted(wz(f"{img}/MapList", cache_only).get("children", []), key=int):
            base = f"{img}/MapList/{n}"
            pos = wz(f"{base}/spot", cache_only).get("value")
            if not pos:
                continue
            ids = [wz(f"{base}/mapNo/{k}", cache_only).get("value")
                   for k in wz(f"{base}/mapNo", cache_only).get("children", [])]
            spots.append({
                # The game stores spots relative to the picture's origin; convert to top-left pixels.
                "x": pos["x"] + origin["x"],
                "y": pos["y"] + origin["y"],
                "type": wz(f"{base}/type", cache_only).get("value"),
                "v83_ids": [i for i in ids if isinstance(i, int)],
            })
    return {"origin": origin, "spots": spots}


def world_picture(key: str, cache_only: bool = False) -> bytes:
    return fetch(f"wz/img/GMS/83/Map/WorldMap/{WORLDS[key][1]}/BaseImg/0", binary=True, cache_only=cache_only)


def v83_names(cache_only: bool = False) -> list[dict]:
    """[{name, streetName, id}, ...] for every v83 map (one request)."""
    return fetch("GMS/83/map", cache_only=cache_only) or []


def classic_maps() -> list[dict]:
    data = json.loads(OSMS_MAPS.read_text(encoding="utf-8"))
    return [m for region in data["regions"] for m in region["maps"]]


# ---------- matching ----------

def map_rows(cache_only: bool = True, spots: bool = True) -> list[dict]:
    """One dict per Classic map, shaped like the `maps` table (without source_id).
    Raises NotCached in cache-only mode if `python -m scraper.world_map` was never run.
    spots=False skips the game files completely: every map gets no spot."""
    # v83 map id -> (world, x, y). If a map is on several spots, the first one wins.
    spot_of: dict[int, tuple[str, int, int]] = {}
    # (name, street) -> v83 ids with that name (a few names repeat)
    by_name: dict[tuple[str, str], list[int]] = {}
    if spots:
        for key in SPOT_WORLDS:
            for s in world_info(key, cache_only)["spots"]:
                for v83_id in s["v83_ids"]:
                    spot_of.setdefault(v83_id, (key, s["x"], s["y"]))
        for m in v83_names(cache_only):
            by_name.setdefault((normalise(m.get("name")), normalise(m.get("streetName"))), []).append(m["id"])

    rows = {}
    for m in classic_maps():
        candidates = by_name.get((normalise(m["name"]), normalise(m.get("street_name"))), [])
        # prefer a v83 match that actually has a spot
        with_spot = [i for i in candidates if i in spot_of]
        v83_id = (with_spot or candidates or [None])[0]
        row = {
            "id": m["id"], "name": m["name"], "street_name": m.get("street_name"),
            "region": m.get("region"), "map_mark": m.get("map_mark"),
            "is_town": bool(m.get("is_town")), "return_map_id": m.get("return_map_id"),
            "world": REGION_WORLD.get(m.get("region")), "spot_x": None, "spot_y": None,
            "spot_exact": None, "v83_map_id": v83_id,
        }
        if v83_id in spot_of:
            row["world"], row["spot_x"], row["spot_y"] = spot_of[v83_id]
            row["spot_exact"] = True
        rows[m["id"]] = row

    # Fallback 1: no own spot -> the nearest map you can walk to (through portals)
    # that does have a spot, on the same island. Most of these are small "Hidden Street"
    # side maps, so the neighbour is right next to them.
    neighbours: dict[int, set[int]] = {}
    for m in classic_maps():
        for exit_id in m.get("exits") or []:
            if exit_id in rows and exit_id != m["id"]:
                neighbours.setdefault(m["id"], set()).add(exit_id)
                neighbours.setdefault(exit_id, set()).add(m["id"])  # portals go both ways
    for row in rows.values():
        if row["spot_x"] is None and row["region"] in REGION_WORLD:
            near = nearest_spotted(row["id"], rows, neighbours)
            if near:
                row["world"], row["spot_x"], row["spot_y"] = near["world"], near["spot_x"], near["spot_y"]
                row["spot_exact"] = False

    # Fallback 2: still nothing -> use the spot of the town it returns to.
    for row in rows.values():
        town = rows.get(row["return_map_id"])
        if row["spot_x"] is None and town and town["spot_exact"]:
            row["world"], row["spot_x"], row["spot_y"] = town["world"], town["spot_x"], town["spot_y"]
            row["spot_exact"] = False
    return list(rows.values())


def nearest_spotted(start: int, rows: dict, neighbours: dict, max_steps: int = 4) -> dict | None:
    """Walk outward through portals (breadth-first) and return the first map on the same
    island that has its own exact spot, or None if there isn't one within max_steps."""
    region = rows[start]["region"]
    seen, frontier = {start}, [start]
    for _ in range(max_steps):
        next_frontier = []
        for map_id in sorted(frontier):
            for nb in sorted(neighbours.get(map_id, ())):
                if nb in seen:
                    continue
                seen.add(nb)
                if rows[nb]["region"] != region:
                    continue   # don't wander onto another island (e.g. through the ship)
                if rows[nb]["spot_exact"]:
                    return rows[nb]
                next_frontier.append(nb)
        frontier = next_frontier
    return None


def match_report(rows: list[dict]) -> str:
    exact = sum(1 for r in rows if r["spot_exact"] is True)
    fallback = sum(1 for r in rows if r["spot_exact"] is False)
    none = len(rows) - exact - fallback
    pct = lambda n: f"{n * 100 / len(rows):.0f}%" if rows else "0%"
    return (f"{len(rows)} maps: {exact} exact ({pct(exact)}), {fallback} fallback to a nearby map or town ({pct(fallback)}), "
            f"{none} no spot ({pct(none)})")


# ---------- the command ----------

def main() -> None:
    from PIL import Image  # only needed here, to read picture sizes
    import io

    OUT_DIR.mkdir(parents=True, exist_ok=True)
    meta = {}
    for key, (title, _img) in WORLDS.items():
        print(f"{title}: downloading picture + spots (cached in data/raw/worldmap/)...", flush=True)
        info = world_info(key)
        png = world_picture(key)
        (OUT_DIR / f"{key}.png").write_bytes(png)
        width, height = Image.open(io.BytesIO(png)).size
        meta[key] = {"title": title, "image": f"/static/img/worldmap/{key}.png",
                     "width": width, "height": height, "origin": info["origin"]}
        print(f"  {key}.png {width}x{height}, {len(info['spots'])} spots", flush=True)
    (OUT_DIR / "worlds.json").write_text(json.dumps(meta, indent=2), encoding="utf-8")

    print("Matching Classic maps to spots...", flush=True)
    rows = map_rows(cache_only=False)
    print(match_report(rows))
    for region in ("Maple Island", "Victoria Island"):
        print(f"  {region}: " + match_report([r for r in rows if r["region"] == region]))
    missing = [r for r in rows if r["spot_x"] is None and r["region"] in REGION_WORLD]
    if missing:
        print(f"  island maps with no spot: {[(r['id'], r['name']) for r in missing]}")


if __name__ == "__main__":
    main()
