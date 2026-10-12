"""The item browser (GET /items): reading the filters from the URL, finding
the matching items, and building every tab / filter button.

How it works, in plain English:
  1. Load a small summary of EVERY item (only ~2,000, so this is fast).
  2. Clean up the URL filters (ignore anything we don't recognise).
  3. Keep the items that match, sort them, and cut out one page.
  4. For every tab / button, count how many items you'd see if you clicked it,
     and pick a picture for it (the lowest-level item in that group).

Filter order is: class > type > gear > slot > weapon. Changing one resets the
ones below it (weapon types differ per class, slots only exist for equips...).
Gear groups equips: Weapons (then weapon type) | Clothes | Accessories (then slot).
Use items split into HP potions | MP potions | HP + MP | Scrolls | Other (`use`).
`level` and `q` (name search) are independent and are always kept.

Every button is a dict called an "Option" (see docs/api-contract.md):
  {label, value, count, icon_item_id, active, url}
"""

import re
from urllib.parse import urlencode

from sqlalchemy import select

from app.models import Item

PAGE_SIZE = 60
LEVEL_STEP = 10  # level ranges are 0-10, 11-20, 21-30, ...

# (URL value, label). These are the ONLY class tabs.
CLASSES = [
    ("all", "All"),
    ("beginner", "Beginner"),
    ("warrior", "Warrior"),
    ("magician", "Magician"),
    ("bowman", "Bowman"),
    ("thief", "Thief"),
]

TYPES = [
    ("equip", "Equip"),
    ("use", "Use"),
    ("etc", "Etc"),
    ("setup", "Setup"),
]

# Sections shown after picking "Use" (scrolls live here, like the in-game Use tab).
USE_KINDS = [
    ("hp", "HP potions"),
    ("mp", "MP potions"),
    ("hpmp", "HP + MP"),
    ("scroll", "Scrolls"),
    ("other", "Other"),
]

# "Restores 35% of your HP and MP" style descriptions, for potions with no heal numbers.
RESTORES = re.compile(r"Restores [\d,]+%? (?:of your )?(HP and MP|HP|MP)\b")


def use_kind(category, sub_type, stats, description):
    """Which Use section an item belongs in ("" for non-Use items).

    Healing comes from the heal_hp / heal_mp stats, or from the description
    when the game file only describes it (Elixir, Mana Elixir, W Ramen).
    """
    if category != "use":
        return ""
    if sub_type == "Scroll":
        return "scroll"
    stats = stats or {}
    hp, mp = bool(stats.get("heal_hp")), bool(stats.get("heal_mp"))
    found = RESTORES.search(description or "")
    if found and not (hp or mp):
        hp, mp = "HP" in found.group(1), "MP" in found.group(1)
    if hp and mp:
        return "hpmp"
    return "hp" if hp else "mp" if mp else "other"

# URL values are lowercase; the database stores them capitalized ("Hat").
SLOTS = [
    ("weapon", "Weapon"),
    ("hat", "Hat"),
    ("top", "Top"),
    ("bottom", "Bottom"),
    ("overall", "Overall"),
    ("shoes", "Shoes"),
    ("glove", "Glove"),
    ("shield", "Shield"),
    ("cape", "Cape"),
    ("earring", "Earring"),
]

# Equip groups shown after picking "Equip": (URL value, label, slots inside it).
GEARS = [
    ("weapons", "Weapons", ["weapon"]),
    ("clothes", "Clothes", ["hat", "top", "bottom", "overall", "shoes", "glove", "cape"]),
    ("accessories", "Accessories", ["earring", "shield"]),
]
GEAR_SLOTS = {value: slots for value, _, slots in GEARS}


def gear_for_slot(slot):
    """Which group a slot belongs to ("hat" -> "clothes")."""
    return next((value for value, slots in GEAR_SLOTS.items() if slot in slots), "")


# Weapon types each class can use. Values are exactly what the database stores.
WEAPONS_BY_CLASS = {
    "warrior": ["1H Sword", "2H Sword", "1H Axe", "2H Axe",
                "1H Blunt Weapon", "2H Blunt Weapon", "Spear", "Polearm"],
    "magician": ["Wand", "Staff"],
    "bowman": ["Bow", "Crossbow"],
    "thief": ["Claw", "Dagger"],
}
ALL_WEAPONS = [w for weapons in WEAPONS_BY_CLASS.values() for w in weapons]


def weapon_label(weapon_type):
    """Shorter button text: "1H Blunt Weapon" -> "1H Blunt"."""
    return weapon_type.replace(" Weapon", "")


def weapons_for_class(cls):
    """Weapon types to offer for a class tab ("all"/"beginner" get every type)."""
    return WEAPONS_BY_CLASS.get(cls, ALL_WEAPONS)


# ---------- level ranges ----------

def level_range_value(low, high):
    return f"{low}-{high}"


def parse_level(value):
    """"11-20" -> (11, 20). Anything else -> None."""
    try:
        low, high = (int(part) for part in value.split("-"))
    except (ValueError, AttributeError):
        return None
    if low < 0 or high < low:
        return None
    return low, high


def level_ranges(max_level):
    """All ranges up to max_level: [(0, 10), (11, 20), ...]."""
    ranges = [(0, LEVEL_STEP)]
    while ranges[-1][1] < (max_level or 0):
        start = ranges[-1][1] + 1
        ranges.append((start, start + LEVEL_STEP - 1))
    return ranges


def in_level_range(level, level_value):
    """True if `level` (None counts as 0) is inside the "11-20" style range."""
    bounds = parse_level(level_value)
    if bounds is None:
        return True  # no level filter
    return bounds[0] <= (level or 0) <= bounds[1]


# ---------- loading items + matching ----------

def load_items(db):
    """A small dict for every item (just the fields the browser needs)."""
    rows = db.execute(
        select(Item.id, Item.name, Item.category, Item.sub_type, Item.equip_slot,
               Item.weapon_type, Item.level_req, Item.jobs, Item.icon_url,
               Item.stats, Item.description)
    ).all()
    return [
        {
            "id": r.id,
            "name": r.name,
            "category": r.category,
            "sub_type": r.sub_type,
            "equip_slot": r.equip_slot,
            "weapon_type": r.weapon_type,
            "level_req": r.level_req,
            "jobs": list(r.jobs or []),  # treat a missing list as "any class"
            "icon_url": r.icon_url,
            "use_kind": use_kind(r.category, r.sub_type, r.stats, r.description),
        }
        for r in rows
    ]


def matches(item, f):
    """Does one item pass every filter in f? Blank filters match everything."""
    cls = f.get("class", "all")
    if cls == "beginner" and item["jobs"]:
        return False  # beginner = no class requirement at all
    if cls not in ("all", "beginner") and cls.capitalize() not in item["jobs"]:
        return False
    if f.get("type") and item["category"] != f["type"]:
        return False
    if f.get("use") and item.get("use_kind") != f["use"]:
        return False
    if f.get("gear") and (item["equip_slot"] or "").lower() not in GEAR_SLOTS[f["gear"]]:
        return False
    if f.get("slot") and (item["equip_slot"] or "").lower() != f["slot"]:
        return False
    if f.get("weapon") and item["weapon_type"] != f["weapon"]:
        return False
    if f.get("level") and not in_level_range(item["level_req"], f["level"]):
        return False
    if f.get("q") and f["q"].lower() not in item["name"].lower():
        return False
    return True


def apply_filters(items, f):
    return [item for item in items if matches(item, f)]


def representative_icon(items):
    """The picture for a group: its lowest-level item that has an icon.

    If no item has an icon (e.g. sample data), use the lowest-level item anyway;
    the template shows a placeholder when the picture file is missing.
    """
    if not items:
        return None
    with_icon = [i for i in items if i["icon_url"]] or items
    best = min(with_icon, key=lambda i: (i["level_req"] or 0, i["id"]))
    return best["id"]


# ---------- reading the URL ----------

def clean_filters(params):
    """Turn raw URL params into safe filter values. Unknown values become blank."""
    get = lambda key: (params.get(key) or "").strip()

    cls = get("class").lower()
    if cls not in dict(CLASSES):
        cls = "all"

    # Class tabs are about gear, so any class other than "all" means equips only
    # (no Type step: Warrior -> Weapons -> 2H Sword). Type only exists on "All".
    type_ = get("type").lower()
    use = get("use").lower()
    if type_ == "scroll":  # old links: Scrolls used to be its own type
        type_, use = "use", "scroll"
    if cls != "all":
        type_ = "equip"
    elif type_ not in dict(TYPES):
        type_ = ""
    if type_ != "use" or use not in dict(USE_KINDS):
        use = ""

    # gear + slot only make sense for equips, weapon only for the weapon slot.
    slot = get("slot").lower()
    if type_ != "equip" or slot not in dict(SLOTS):
        slot = ""
    gear = get("gear").lower()
    if type_ != "equip" or gear not in GEAR_SLOTS:
        gear = gear_for_slot(slot)  # old links like ?slot=hat still work
    if slot and slot not in GEAR_SLOTS.get(gear, []):
        slot = ""
    if gear == "weapons":
        slot = "weapon"  # the Weapons group has just one slot

    weapon = get("weapon")
    if slot != "weapon" or weapon not in weapons_for_class(cls):
        weapon = ""

    level = get("level")
    if parse_level(level) is None:
        level = ""

    try:
        page = max(1, int(get("page") or 1))
    except ValueError:
        page = 1

    return {"class": cls, "type": type_, "use": use, "gear": gear, "slot": slot, "weapon": weapon,
            "level": level, "q": get("q")[:100], "page": page}


def items_url(f, base="/items"):
    """Build a link like /items?class=warrior&type=equip from a filter dict.

    Blank values, class=all and page=1 are left out to keep links short.
    """
    params = {}
    for key in ("class", "type", "use", "gear","slot", "weapon", "level", "q", "page"):
        value = f.get(key)
        if not value or (key == "class" and value == "all") or (key == "page" and value == 1):
            continue
        if key == "type" and f.get("class", "all") != "all":  # class tabs are always equips
            continue
        if key == "slot" and f.get("gear") == "weapons":  # implied by gear=weapons
            continue
        params[key] = value
    return base + ("?" + urlencode(params) if params else "")


# ---------- building the buttons ----------

def make_option(items, label, value, active, link_filters, count_filters=None):
    """One tab / filter button.

    link_filters:  the filters you'd have after clicking (used for url).
    count_filters: the filters used to count + pick the picture
                   (defaults to link_filters).
    """
    matching = apply_filters(items, count_filters or link_filters)
    return {
        "label": label,
        "value": value,
        "count": len(matching),
        "icon_item_id": representative_icon(matching),
        "active": active,
        "url": items_url({**link_filters, "page": 1}),
    }


def class_tabs(items, f):
    """The 6 class tabs. Switching class keeps gear + slot but drops weapon
    (weapon types differ per class). Class tabs (not "All") are equips only.
    Tabs are always shown, even with 0 items."""
    tabs = []
    for value, label in CLASSES:
        link = {**f, "class": value, "weapon": "", "use": "" if value != "all" else f.get("use", "")}
        if value != "all":
            link["type"] = "equip"
            if f["type"] != "equip":
                link.update(gear="", slot="")
        tabs.append(make_option(items, label, value, f["class"] == value, link))
    return tabs


def with_all_option(items, all_label, key, f, choices, reset):
    """Build an "All ..." button followed by one button per choice.

    key:   the filter these buttons set ("type", "slot", ...)
    reset: filters below this one, cleared when you click
    Choices with 0 matching items are hidden.
    """
    cleared = {**f, key: "", **{r: "" for r in reset}}
    options = [make_option(items, all_label, "", f[key] == "", cleared)]
    for value, label in choices:
        option = make_option(items, label, value, f[key] == value, {**cleared, key: value})
        if option["count"] > 0:
            options.append(option)
    return options


def type_options(items, f):
    if f["class"] != "all":
        return []  # class tabs are equips only, so there's no Type row
    return with_all_option(items, "All types", "type", f, TYPES, reset=["use", "gear", "slot", "weapon"])


def use_options(items, f):
    """HP potions | MP potions | HP + MP | Scrolls | Other, shown once "Use" is picked."""
    if f["type"] != "use":
        return []
    return with_all_option(items, "All use items", "use", f, USE_KINDS, reset=[])


def gear_options(items, f):
    """Weapons | Clothes | Accessories, shown once "Equip" is picked."""
    if f["type"] != "equip":
        return []
    cleared = {**f, "gear": "", "slot": "", "weapon": ""}
    options = [make_option(items, "All equips", "", f["gear"] == "", cleared)]
    # Picture slot per group, so each looks different (a shirt for Clothes, not a hat).
    picture_slot = {"weapons": "weapon", "clothes": "top", "accessories": "earring"}
    for value, label, _ in GEARS:
        link = {**cleared, "gear": value, "slot": "weapon" if value == "weapons" else ""}
        option = make_option(items, label, value, f["gear"] == value, link)
        pictured = apply_filters(items, {**link, "slot": picture_slot[value]})
        option["icon_item_id"] = representative_icon(pictured) or option["icon_item_id"]
        if option["count"] > 0:
            options.append(option)
    return options


def slot_options(items, f):
    """Slots inside the picked gear group (Weapons has none; it uses weapon types)."""
    if f["gear"] not in ("clothes", "accessories"):
        return []
    choices = [(s, label) for s, label in SLOTS if s in GEAR_SLOTS[f["gear"]]]
    return with_all_option(items, f"All {f['gear']}", "slot", f, choices, reset=["weapon"])


def weapon_options(items, f):
    if f["slot"] != "weapon":
        return []
    choices = [(w, weapon_label(w)) for w in weapons_for_class(f["class"])]
    return with_all_option(items, "All weapons", "weapon", f, choices, reset=[])


def level_options(items, f):
    max_level = max((i["level_req"] or 0 for i in items), default=0)
    choices = [(level_range_value(lo, hi), f"Lv. {lo}-{hi}") for lo, hi in level_ranges(max_level)]
    return with_all_option(items, "All levels", "level", f, choices, reset=[])


# ---------- the whole page ----------

def item_card(item):
    """What one result in the grid needs (see ItemCard in the API contract)."""
    return {key: item[key] for key in
            ("id", "name", "category", "sub_type", "equip_slot", "weapon_type", "level_req", "jobs")}


def browse_items(db, params):
    """Every template variable for GET /items (full page and HTMX partial)."""
    f = clean_filters(params)
    items = load_items(db)

    results = sorted(apply_filters(items, f), key=lambda i: (i["level_req"] or 0, i["name"]))
    total = len(results)
    pages = max(1, -(-total // PAGE_SIZE))  # round up
    page = min(f["page"], pages)
    f["page"] = page
    shown = results[(page - 1) * PAGE_SIZE: page * PAGE_SIZE]

    return {
        "filters": f,
        "class_tabs": class_tabs(items, f),
        "type_options": type_options(items, f),
        "use_options": use_options(items, f),
        "gear_options": gear_options(items, f),
        "slot_options": slot_options(items, f),
        "weapon_options": weapon_options(items, f),
        "level_options": level_options(items, f),
        "items": [item_card(i) for i in shown],
        "total": total,
        "page": page,
        "pages": pages,
        "prev_url": items_url({**f, "page": page - 1}) if page > 1 else None,
        "next_url": items_url({**f, "page": page + 1}) if page < pages else None,
        "clear_url": "/items",
    }


def home_class_tabs(db):
    """Class tabs for the home page (each links to /items?class=...)."""
    blank = clean_filters({})
    return class_tabs(load_items(db), blank)


# Fixed facts for the home page class cards. hat_id = the class's iconic hat
# (the card picture); class colours live in site.css under [data-class].
CLASS_INFO = {
    "beginner": {"hat_id": 1002003, "hat": "Red Headband", "home": "Maple Island", "stat": "Any",
                 "blurb": "Everyone starts here. Gear any class can wear."},
    "warrior": {"hat_id": 1002057, "hat": "Bronze Viking Helm", "home": "Perion", "stat": "STR",
                "blurb": "Tough melee fighters with swords, axes, blunts and spears."},
    "magician": {"hat_id": 1002060, "hat": "Blue Wizardry Hat", "home": "Ellinia", "stat": "INT",
                 "blurb": "Spellcasters who fight from range with wands and staves."},
    "bowman": {"hat_id": 1002063, "hat": "Green Robin Hat", "home": "Henesys", "stat": "DEX",
               "blurb": "Sharp-eyed archers with bows and crossbows."},
    "thief": {"hat_id": 1002048, "hat": "Red Thief Hood", "home": "Kerning City", "stat": "LUK",
              "blurb": "Quick and sneaky, with throwing claws or daggers."},
}


def home_classes(db):
    """The big class cards on the home page: one per class (no "All").

    Each card: {value, label, url, count, npc_id, instructor, home, stat, blurb,
                gear: [{label, url, icon_item_id}]}
    `gear` = little picture links: the class's weapon types, or for Beginner a few
    slots of no-class gear.
    """
    items = load_items(db)
    cards = []
    for value, label in CLASSES:
        if value == "all":
            continue
        f = clean_filters({"class": value})  # class -> equips only
        mine = apply_filters(items, f)
        if value == "beginner":
            picks = [("clothes", "hat", "Hats"), ("clothes", "top", "Tops"), ("clothes", "shoes", "Shoes"),
                     ("weapons", "", "Weapons")]
            links = [{**f, "type": "equip", "gear": gear, "slot": slot or ("weapon" if gear == "weapons" else "")}
                     for gear, slot, _ in picks]
            labels = [p[2] for p in picks]
        else:
            weapons = WEAPONS_BY_CLASS[value]
            links = [{**f, "type": "equip", "gear": "weapons", "slot": "weapon", "weapon": w} for w in weapons]
            labels = [weapon_label(w) for w in weapons]
        gear = []
        for link, gear_label in zip(links, labels):
            matching = apply_filters(items, link)
            if matching:
                gear.append({"label": gear_label, "url": items_url(link),
                             "icon_item_id": representative_icon(matching)})
        cards.append({"value": value, "label": label, "url": items_url(f), "count": len(mine),
                      "gear": gear, **CLASS_INFO[value]})
    return cards
