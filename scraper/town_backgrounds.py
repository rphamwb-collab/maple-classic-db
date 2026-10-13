"""Make the class hometown backgrounds (home page class cards + /items banner).

    .venv\\Scripts\\python -m scraper.town_backgrounds

Each town picture is drawn the way the game draws the map:
  1. background layers (sky, hills, skyline...), with parallax
  2. the 8 map layers, each with its objects (houses, trees, signs...) then
     its floor tiles
  3. "front" background layers (mist, leaves in front)
The camera is centred on the town's NPCs, so you see the street with the shops.
Everything comes from GMS v83 game files served by maplestory.io. Game art (c) Nexon.

Every download is saved under data/raw/towns/wz/, so running the script again
makes no new requests. To re-frame a town, change VIEW_X / CAM_UP and re-run.
"""
import io
import json
import statistics
import time
from pathlib import Path

import httpx
from PIL import Image, ImageOps

ROOT = Path(__file__).resolve().parents[1]
WZ_CACHE = ROOT / "data" / "raw" / "towns" / "wz"
OUT_DIR = ROOT / "app" / "static" / "img" / "towns"

API = "https://maplestory.io/api"

# class value -> (town name, v83 map id). "all" is the /items banner for the All tab.
TOWNS = {
    "beginner": ("Amherst", 1010000),
    "warrior": ("Perion", 102000000),
    "magician": ("Ellinia", 101000000),
    "bowman": ("Henesys", 100000000),
    "thief": ("Kerning City", 103000000),
    "all": ("Lith Harbor", 104000000),
}

# Optional framing tweaks. VIEW_X: map x of the picture's centre (default:
# where the NPCs stand). CAM_UP: move the camera up by this many pixels.
VIEW_X: dict[str, int] = {}
CAM_UP: dict[str, int] = {}

WIDTH, HEIGHT = 800, 600    # the "game screen" we draw (v83 was 800x600)
OUT_HEIGHT = 320            # final picture keeps the bottom part of the screen
FLOOR_ROW = 50              # the street sits this many pixels above the picture's bottom

# Background layer types (from the game): which repeat sideways / up-down,
# and which drift with time (drawn as if time = 0).
H_TILE = {1, 3, 4, 6}
V_TILE = {2, 3, 5, 7}
MOVING_X = {4, 6}
MOVING_Y = {5, 7}

_client = None


def fetch(path: str, binary: bool = False):
    """GET {API}/{path}, saved to disk so each URL is only ever downloaded once."""
    global _client
    name = path.replace("/", "_") + (".png" if binary else ".json")
    cached = WZ_CACHE / name
    if cached.exists():
        return cached.read_bytes() if binary else json.loads(cached.read_text())
    if _client is None:
        _client = httpx.Client(timeout=60, headers={"User-Agent": "maple-classic-db (fan site)"})
    time.sleep(0.05)   # be polite to maplestory.io (each request already takes ~0.2s)
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
    WZ_CACHE.mkdir(parents=True, exist_ok=True)
    if binary:
        cached.write_bytes(data)
    else:
        cached.write_text(json.dumps(data))
    return data


def wz_value(path: str, default=None):
    """One value from the game files, e.g. an object's x position."""
    node = fetch(f"wz/GMS/83/{path}")
    return default if node is None else node.get("value", default)


def wz_children(path: str) -> list[str]:
    node = fetch(f"wz/GMS/83/{path}")
    return (node or {}).get("children", [])


def map_path(map_id: int) -> str:
    padded = f"{map_id:09d}"
    return f"Map/Map/Map{padded[0]}/{padded}.img"


def sprite(path: str, flip: bool = False, alpha: int = 255):
    """A game picture plus its origin point, or (None, None) if it doesn't exist."""
    png = fetch(f"wz/img/GMS/83/{path}", binary=True)
    if not png:
        return None, None
    origin = wz_value(f"{path}/origin", None) or {"x": 0, "y": 0}
    img = Image.open(io.BytesIO(png)).convert("RGBA")
    ox = origin["x"]
    if flip:
        img = ImageOps.mirror(img)
        ox = img.width - ox
    if alpha not in (0, 255):
        img.putalpha(img.getchannel("A").point(lambda v: v * alpha // 255))
    return img, (ox, origin["y"])


# ---------- background layers ----------

def background_layers(map_id: int) -> list[dict]:
    base = map_path(map_id) + "/back"
    layers = []
    for idx in sorted(wz_children(base), key=int):
        p = f"{base}/{idx}"
        layer = {k: wz_value(f"{p}/{k}", 0) for k in
                 ("bS", "no", "type", "x", "y", "rx", "ry", "cx", "cy", "a", "ani", "front", "f")}
        if layer["bS"]:
            layers.append(layer)
    return layers


def draw_background(canvas: Image.Image, layer: dict, cam_x: int, cam_y: int) -> None:
    """Place one background layer the way the game does with the camera at (cam_x, cam_y)."""
    folder = "ani" if layer["ani"] else "back"
    path = f"Map/Back/{layer['bS']}.img/{folder}/{layer['no']}" + ("/0" if layer["ani"] else "")
    img, origin = sprite(path, flip=bool(layer["f"]), alpha=layer["a"] or 255)
    if img is None:
        return
    t = layer["type"]
    # rx/ry is parallax: 0 = stays put on screen (far away), -100 = scrolls with the ground.
    sx = layer["x"] - cam_x if t in MOVING_X else layer["x"] + layer["rx"] * cam_x // 100
    sy = layer["y"] - cam_y if t in MOVING_Y else layer["y"] + layer["ry"] * cam_y // 100
    sx += WIDTH // 2 - origin[0]
    sy += HEIGHT // 2 - origin[1]
    step_x = layer["cx"] or img.width
    step_y = layer["cy"] or img.height
    xs = range(sx % step_x - step_x, WIDTH, step_x) if t in H_TILE else [sx]
    ys = range(sy % step_y - step_y, HEIGHT, step_y) if t in V_TILE else [sy]
    for y in ys:
        for x in xs:
            canvas.paste(img, (x, y), img)   # the image's own transparency is the mask


# ---------- map layers: objects + tiles ----------

def on_screen(x: int, y: int, cam_x: int, cam_y: int, margin: int = 700) -> bool:
    """Roughly in view? (Big margin: houses and trees can be large.)"""
    return abs(x - cam_x) < WIDTH // 2 + margin and abs(y - cam_y) < HEIGHT // 2 + margin


def draw_map_layer(canvas: Image.Image, map_id: int, layer: int, cam_x: int, cam_y: int) -> None:
    base = f"{map_path(map_id)}/{layer}"
    # Objects first (houses, trees, signs), back to front by their z value.
    objs = []
    for i in wz_children(f"{base}/obj"):
        p = f"{base}/obj/{i}"
        x, y = wz_value(f"{p}/x", 0), wz_value(f"{p}/y", 0)
        if on_screen(x, y, cam_x, cam_y):
            objs.append((wz_value(f"{p}/z", 0), int(i), p, x, y))
    for _z, _i, p, x, y in sorted(objs):
        parts = [wz_value(f"{p}/{k}", "") for k in ("oS", "l0", "l1", "l2")]
        img, origin = sprite(f"Map/Obj/{parts[0]}.img/{parts[1]}/{parts[2]}/{parts[3]}/0",
                             flip=bool(wz_value(f"{p}/f", 0)))
        if img is not None:
            canvas.paste(img, (x - cam_x + WIDTH // 2 - origin[0], y - cam_y + HEIGHT // 2 - origin[1]), img)
    # Then the floor tiles of this layer.
    tile_set = wz_value(f"{base}/info/tS", "")
    if not tile_set:
        return
    for i in wz_children(f"{base}/tile"):
        p = f"{base}/tile/{i}"
        x, y = wz_value(f"{p}/x", 0), wz_value(f"{p}/y", 0)
        if not on_screen(x, y, cam_x, cam_y, margin=200):
            continue
        img, origin = sprite(f"Map/Tile/{tile_set}.img/{wz_value(f'{p}/u', '')}/{wz_value(f'{p}/no', 0)}")
        if img is not None:
            canvas.paste(img, (x - cam_x + WIDTH // 2 - origin[0], y - cam_y + HEIGHT // 2 - origin[1]), img)


# ---------- putting it together ----------

def camera(cls: str, map_id: int) -> tuple[int, int]:
    """Centre on where the town's NPCs stand, with their street near the picture's bottom."""
    info = fetch(f"GMS/83/map/{map_id}")
    npcs = [n for n in info.get("npcs") or [] if not n.get("hidden")]
    street_x = int(statistics.median(n["x"] for n in npcs))
    street_y = int(statistics.median(n["y"] for n in npcs))
    cam_x = VIEW_X.get(cls, street_x)
    cam_y = street_y - HEIGHT // 2 + FLOOR_ROW - CAM_UP.get(cls, 0)
    return cam_x, cam_y


def make_town(cls: str) -> Path:
    town, map_id = TOWNS[cls]
    cam_x, cam_y = camera(cls, map_id)
    canvas = Image.new("RGBA", (WIDTH, HEIGHT), (135, 190, 235, 255))  # plain sky if a map has none
    backs = background_layers(map_id)
    for layer in backs:
        if not layer["front"]:
            draw_background(canvas, layer, cam_x, cam_y)
    for layer in range(8):
        draw_map_layer(canvas, map_id, layer, cam_x, cam_y)
    for layer in backs:
        if layer["front"]:
            draw_background(canvas, layer, cam_x, cam_y)
    picture = canvas.crop((0, HEIGHT - OUT_HEIGHT, WIDTH, HEIGHT)).convert("RGB")
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    out = OUT_DIR / f"{cls}.webp"
    picture.save(out, "WEBP", quality=80, method=6)
    print(f"{cls:9} {town:13} camera ({cam_x}, {cam_y}) -> {out.name} {out.stat().st_size // 1024} KB", flush=True)
    return out


if __name__ == "__main__":
    for cls in TOWNS:
        make_town(cls)
