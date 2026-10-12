"""Copy item icons, NPC portraits, and monster sprites from an OSMS clone into the website.

    .venv\\Scripts\\python -m scraper.icons <path to osms_datamine_dashboard clone>

Get the clone with:
    git clone --depth 1 https://github.com/ohmi69/osms_datamine_dashboard.git <somewhere>

Only images for things in our database are copied, named by game ID so the
templates can find them without any database lookup:
    app/static/img/items/{item_id}.png
    app/static/img/npcs/{npc_id}.png
    app/static/img/monsters/{monster_id}.webp   (animated "standing" sprite)

Game art (c) Nexon. Afterwards, run `python -m scraper.run` so items get their icon_url.
"""
import json
import shutil
import sys
from pathlib import Path

from sqlalchemy import select

from app.db import SessionLocal
from app.models import Item, Monster, Npc

STATIC_IMG = Path(__file__).resolve().parents[1] / "app" / "static" / "img"


def copy_images(clone: Path) -> None:
    images = clone / "data" / "current" / "images"
    monster_sprites = clone / "data" / "images" / "monsters"
    if not images.is_dir():
        sys.exit(f"Can't find {images}. Is {clone} an OSMS clone?")

    db = SessionLocal()
    try:
        item_ids = db.scalars(select(Item.id)).all()
        npc_ids = db.scalars(select(Npc.id)).all()
        monster_ids = set(db.scalars(select(Monster.id)).all())
    finally:
        db.close()

    counts = {}
    # OSMS names files with zero padding: items 8 digits, NPCs 7 digits
    for kind, ids, width in (("items", item_ids, 8), ("npcs", npc_ids, 7)):
        out = STATIC_IMG / kind
        out.mkdir(parents=True, exist_ok=True)
        copied = 0
        for obj_id in ids:
            src = images / kind / f"{obj_id:0{width}d}.png"
            if src.exists():
                shutil.copyfile(src, out / f"{obj_id}.png")
                copied += 1
        counts[kind] = (copied, len(ids))

    # monsters: monsters.json says which sprite file is each monster's "stand" animation
    out = STATIC_IMG / "monsters"
    out.mkdir(parents=True, exist_ok=True)
    data = json.loads((clone / "data" / "current" / "monsters.json").read_text(encoding="utf-8"))
    copied = 0
    for mob in data["monsters"]:
        sprite = (mob.get("gifs") or {}).get("stand") or (mob.get("gifs") or {}).get("move")
        if mob["id"] in monster_ids and sprite:
            matches = list(monster_sprites.rglob(f"{sprite}.*"))
            if matches:
                shutil.copyfile(matches[0], out / f"{mob['id']}{matches[0].suffix}")
                copied += 1
    counts["monsters"] = (copied, len(monster_ids))

    for kind, (copied, total) in counts.items():
        print(f"  {kind:9} {copied} / {total} images copied")


if __name__ == "__main__":
    if len(sys.argv) != 2:
        sys.exit(__doc__)
    copy_images(Path(sys.argv[1]))
