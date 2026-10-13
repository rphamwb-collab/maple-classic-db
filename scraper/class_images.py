"""Trim the empty space around the class character pictures (home page class cards).

    .venv\\Scripts\\python -m scraper.class_images

The character PNGs (made once with maplestory.io) had different amounts of
transparent padding, so the same CSS height drew them at different sizes.
This cuts each picture down to just the visible character, so the CSS height
(.class-stage img in site.css) means "character height" for every class.

The untouched originals are kept in data/raw/classes/ the first time it runs,
and trimming always starts from those, so running it twice is safe.
"""
import shutil
from pathlib import Path

from PIL import Image

ROOT = Path(__file__).resolve().parents[1]
CLASSES_DIR = ROOT / "app" / "static" / "img" / "classes"
ORIGINALS = ROOT / "data" / "raw" / "classes"


def trim_all() -> None:
    ORIGINALS.mkdir(parents=True, exist_ok=True)
    for png in sorted(CLASSES_DIR.glob("*.png")):
        original = ORIGINALS / png.name
        if not original.exists():
            shutil.copy2(png, original)   # keep the untrimmed picture once
        img = Image.open(original).convert("RGBA")
        box = img.getchannel("A").getbbox()   # smallest box around visible pixels
        img.crop(box).save(png)
        print(f"{png.stem:9} {img.size} -> {box[2] - box[0]}x{box[3] - box[1]}")


if __name__ == "__main__":
    trim_all()
