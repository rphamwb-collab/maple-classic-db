# API Contract v2 (backend-dev <-> frontend-dev)

Owner: backend-dev. Frontend-dev: ask for changes by message; don't edit this file.

**What's new in v2** (details in the sections below):
- New pages: `GET /items` (item browser, HTMX partial), `GET /monsters`, `GET /shops` (`/npcs` redirects there).
- Home page now gets `counts` and `class_tabs`.
- Item page gets `how_to_get`, `used_in`, `sellable`, and `item.equip_slot / weapon_type / jobs`.
- New shared shape `Option` used by every tab / filter button.

- Templates live in `app/templates/` (frontend-dev). Static files are served at `/static` from `app/static/`.
- **Every variable is a plain Python dict / list / number / string** (not a database object), so templates never depend on table column names.
- Every full-page template also receives `request` (needed by Jinja2Templates) and `page_title` (str).
- Missing values are `None` -> show "—" or "unknown".

## Shared shapes

```
ItemRef     = {id, name, category}                # category: str or None
MonsterRef  = {id, name, level}                   # level: int or None
NpcRef      = {id, name, town, map_name, location, note} # location: "Henesys Market, Henesys" style str or None; v2.4 note: str or None
Source      = {name, url, last_scraped}           # last_scraped: str "YYYY-MM-DD" or None
Observed    = {kills, drops_seen, rate_percent, low_confidence, label}
              # rate_percent: float (e.g. 1.25 means 1.25%) or None if kills == 0
              # low_confidence: bool (True when kills < 100)
              # label: ready-to-print string, e.g. "1.25% (5 / 400 kills)" or "no reports yet"
PriceStats  = {median, low, high, count, outliers_removed}
              # all ints; median/low/high are None when count == 0
Option      = {label, value, count, icon_item_id, active, url}      # v2: one tab / filter button
              # label: "Warrior", "1H Sword", "Lv. 11-20" ...  value: the URL param value ("" = "All")
              # count: how many items you'd see after clicking it (int)
              # icon_item_id: item id to show as its picture -> m.sprite("items", o.icon_item_id, o.label)
              #               (None only if nothing matches, which can't happen because 0-count options are hidden)
              # active: bool, True for the currently selected option
              # url: ready-made link with this option applied, e.g. "/items?class=warrior&type=equip"
              #      (other filters kept, lower filters reset, page reset to 1). Use it for href AND hx-get.
ItemCard    = {id, name, category, sub_type, equip_slot, weapon_type, level_req, jobs}   # v2: one browser result
              # jobs: list of capitalized class names like ["Warrior", "Thief"]; [] = any class
              # equip_slot ("Hat", "Weapon", ...) / weapon_type ("1H Sword", ...): str or None
              # (URL params are lowercase, e.g. slot=hat; display values come from the database as-is)
```

`worlds` (list of str) is passed to every page that has a price form. Current list:
`["Scania", "Bera", "Broa", "Windia", "Khaini", "Bellocan", "Mardia", "Kradia", "Yellonde", "Demethos", "Galicia", "El Nido", "Zenith", "Arcania", "Chaos", "Nova", "Renegades"]`
(sample list; easy to change in `app/services/reports.py`).

## Routes

### GET `/` -> `home.html`
| var | type |
|---|---|
| `q` | str (always `""`) |
| `counts` | v2: `{items, monsters, shops}` ints (shops = NPCs that sell at least 1 item) |
| `class_tabs` | v2: [Option] — same list as on `/items` (All, Beginner, Warrior, Magician, Bowman, Thief); `url` goes to `/items?class=...` |

### GET `/items` -> `items.html` (full page) or `partials/item_results.html` (HTMX) — v2
Query params (all optional; unknown values are ignored as if blank):
| param | values |
|---|---|
| `class` | `all` (default) / `beginner` / `warrior` / `magician` / `bowman` / `thief`. beginner = items with no class requirement (`jobs == []`); a class = items whose jobs include it (multi-class items show under each) |
| `type` | `equip` / `use` / `etc` / `setup` / `scroll` (scrolls are NOT in `use`) |
| `slot` | only when type=equip: `weapon` / `hat` / `top` / `bottom` / `overall` / `shoes` / `glove` / `shield` / `cape` / `earring` |
| `weapon` | only when slot=weapon. Value = exact database weapon_type: `1H Sword` `2H Sword` `1H Axe` `2H Axe` `1H Blunt Weapon` `2H Blunt Weapon` `Spear` `Polearm` (warrior), `Wand` `Staff` (magician), `Bow` `Crossbow` (bowman), `Claw` `Dagger` (thief). The Option `label` is shorter for blunts (`1H Blunt`). |
| `level` | `0-10`, `11-20`, `21-30`, ... (by level_req; missing level counts as 0) |
| `q` | name contains (any case) |
| `page` | 1-based, 60 per page |

Filter order is type > slot > weapon. Clicking an option resets the filters below it (changing type clears slot + weapon; changing slot clears weapon; changing class clears only weapon) — the `url` in each Option already does this.

When the request has the `HX-Request: true` header, ONLY `partials/item_results.html` is rendered, and it gets **all the same variables** (so the partial can redraw the filter bars too). Suggested: put the filter bars + results inside one `<div id="item-browser">` in the partial, and have links use `hx-get="{{ o.url }}" hx-target="#item-browser" hx-push-url="true"`.

| var | type |
|---|---|
| `filters` | `{class, type, slot, weapon, level, q, page}` — current cleaned values (`class` is `"all"` by default, others `""`; `page` int) |
| `class_tabs` | [Option] — All, Beginner, Warrior, Magician, Bowman, Thief. Switching class KEEPS type + slot + level + q but clears weapon (weapon types differ per class); count matches that. Never hidden, even at 0 |
| `type_options` | [Option] — first one is "All types" (value `""`), then equip/use/etc/setup/scroll with count > 0 |
| `slot_options` | [Option] — empty list unless type=equip; first is "All slots" |
| `weapon_options` | [Option] — empty list unless slot=weapon; first is "All weapons"; only weapon types valid for the selected class |
| `level_options` | [Option] — first is "All levels"; ranges with count > 0 |
| `items` | [ItemCard] for this page, sorted by level_req then name |
| `total` | int — matching items over all pages |
| `page`, `pages` | ints (pages >= 1) |
| `prev_url`, `next_url` | str or None |
| `clear_url` | str — `/items` (resets everything) |
| `page_title` | str (full page only, but harmless in partial) |

### GET `/monsters` -> `monsters.html` — v2
Param `level` (same ranges as above, by monster level; optional).
| var | type |
|---|---|
| `monsters` | `[{id, name, level, hp, exp, maps, drop_count}]` sorted by level then name |
| `level_options` | [Option] — "All levels" first, then ranges with count > 0; `url` like `/monsters?level=11-20`; `icon_item_id` is **None** here, use `icon_monster_id` instead (each Option on this page also has `icon_monster_id`) |
| `filters` | `{level}` |
| `total` | int |

### GET `/shops` -> `shops.html` — v2  (`GET /npcs` redirects 307 to `/shops`)
Only NPCs that sell at least 1 item.
| var | type |
|---|---|
| `towns` | `[{town, shop_count, shops: [{npc: NpcRef, item_count}]}]` — towns A-Z (NPCs without a town go last under `"Other"`), shops A-Z |
| `total_shops` | int |

### GET `/search?q=` -> `search.html`
| var | type |
|---|---|
| `q` | str (trimmed) |
| `results` | `{items: [ItemRef], monsters: [MonsterRef], npcs: [NpcRef]}` (max 50 each; empty lists when q is blank) |
| `total` | int (sum of all three lists) |

### GET `/api/search?q=` -> `partials/search_suggestions.html` (HTMX autocomplete)
| var | type |
|---|---|
| `q` | str |
| `results` | same shape as above, but max 8 each |

Add `?format=json` to get the same `results` as JSON instead (handy for testing).

### GET `/items/{item_id}` -> `item.html` (404 if not found)
| var | type |
|---|---|
| `item` | `{id, name, category, sub_type, level_req, job, equip_slot, weapon_type, jobs, stats, description, npc_sell_price, icon_url}` — `stats` is a dict like `{"weapon_attack": 17}` (may be `{}`); v2: `jobs` list of capitalized class names like `["Warrior", "Thief"]` (`[]` = any class), `equip_slot` (`Hat`, `Weapon`...) / `weapon_type` (`1H Sword`...) str or None |
| `sellable` | v2.4: `True` when `npc_sell_price` is known; `None` when it is NULL (unknown) -> show "NPC sell price: Unknown". (`False` = can't be sold; not produced yet, template still handles it) |
| `how_to_get` | v2: `{shops, drops, recipes, quests}` (each a list, may be empty):<br>`shops` = same as top-level `shops`<br>`drops` = same as top-level `drops`<br>`recipes` = `[{discipline, discipline_level, req_level, meso_cost, result_count, ingredients: [Ingredient]}]`<br>`quests` = `[{quest_name, npc_name, level_min, count, region, reward_type, job}]` — `reward_type` is `guaranteed`/`random`/`choice`; `job` is a class name (`Beginner`/`Warrior`/`Magician`/`Bowman`/`Thief`) or None (any class); npc_name/level_min/region may be None |
| `used_in` | v2: recipes that use this item as an ingredient: `[{result: ItemRef, result_count, count, discipline, discipline_level, req_level, meso_cost, ingredients: [Ingredient]}]` — `count` = how many of THIS item the recipe needs |

`Ingredient = {item_id, name, count}` — `item_id` may be **None** (name couldn't be matched to an item): show `name` as plain text, no link/icon.
| `shops` | `[{npc: NpcRef, buy_price}]` — where to buy, cheapest first (kept for v1 templates; same list as `how_to_get.shops`) |
| `drops` | `[{monster: MonsterRef, rate_percent, rate_label, rate_source, confidence, observed: Observed}]` — `rate_percent` is the known rate (float %) or None; `rate_label` is e.g. `"0.5%"` or `"unknown"`; `rate_source` str or None; `confidence` is `unverified`/`estimated`/`verified` (kept for v1; same as `how_to_get.drops`) |
| `price_stats` | PriceStats (last 30 days, IQR-filtered) |
| `recent_reports` | `[{price, quantity, world, reported_at}]` — newest 20 ok reports; `reported_at` str `"YYYY-MM-DD HH:MM"` |
| `worlds` | list of str |
| `sources` | [Source] |

### GET `/monsters/{monster_id}` -> `monster.html` (404 if not found)
| var | type |
|---|---|
| `monster` | `{id, name, level, hp, exp, maps, hidden, note}` — `maps` is a list of str; v2.4 `hidden` bool (test/unreleased mob), `note` str or None |
| `drops` | `[{item: ItemRef, rate_percent, rate_label, rate_source, confidence, observed: Observed}]` |
| `worlds` | list of str (for the drop form) |
| `sources` | [Source] |

### GET `/npcs/{npc_id}` -> `npc.html` (404 if not found)
| var | type |
|---|---|
| `npc` | NpcRef |
| `shop` | `[{item: ItemRef, buy_price}]` sorted by item name |
| `sources` | [Source] |

### POST `/items/{item_id}/prices` (form, HTMX `hx-post`)
Form fields: `price` (int, mesos, > 0), `quantity` (int, default 1, 1..10000), `world` (str, must be in `worlds`).
Response: `partials/report_result.html` with
| var | type |
|---|---|
| `ok` | bool |
| `message` | str (e.g. "Thanks! Price saved." or the reason it was rejected) |
| `price_stats` | PriceStats after the save (so the form area can show the new median) |

Always status 200 (agreed with frontend-dev); `ok=False` when rejected (bad input or rate-limited).
Non-HTMX submit (no `HX-Request` header): redirects (303) back to `/items/{item_id}`.

### POST `/monsters/{monster_id}/drops` (form, HTMX `hx-post`)
Form fields: `item_id` (int, must be one of this monster's drops), `kills` (int, 1..100000), `drops` (int, 0..kills), `world` (optional str; if given must be in `worlds`, blank saved as `"Unknown"`).
Response: `partials/report_result.html` with `ok`, `message`, and `observed` (Observed for that item after the save; `None` when `ok` is False). Same status codes / redirect rule as above.

### GET `/api/items/{item_id}/price-history` -> JSON
List of days (oldest first, only days that have reports, last 30 days). Outliers are judged against the whole 30-day range, then each day is summarized:
```json
[{"date": "2026-10-01", "median": 1200, "low": 900, "high": 1500, "count": 4}]
```

## Rules the backend enforces
- Median uses an IQR filter: reports outside Q1 − 1.5·IQR … Q3 + 1.5·IQR are ignored (`low`/`high` are also from the filtered set).
- Observed drop rate = total drops ÷ total kills; low confidence when kills < 100.
- Rate limit: max 5 reports per IP per minute (in memory).

## v2.1 changes (Lead Dev, 2026-10-11)
- **New `gear` filter on `GET /items`** between `type` and `slot`: `weapons` | `clothes` | `accessories` (only when `type=equip`).
  - weapons = slot weapon (then the `weapon` filter); clothes = hat, top, bottom, overall, shoes, glove, cape; accessories = earring, shield.
  - `gear=weapons` implies `slot=weapon` (slot is left out of URLs). Old links with only `?slot=...` still work, because gear is inferred from the slot.
  - New template variable `gear_options` [Option]. `slot_options` now only appears for clothes/accessories, and `weapon_options` only for weapons.
- **Home page:** new `classes` variable = big class cards
  `{value, label, url, count, npc_id, instructor, home, stat, blurb, gear: [{label, url, icon_item_id}]}` (built by `filters.home_classes`; facts in `filters.CLASS_INFO`).
- Class colours: `data-class="<value>"` on home cards and `/items` tabs; CSS vars `--cls` / `--cls-sky` in site.css.
- **v2.2 (Lead Dev):** class tabs other than "All" are **equips only**. `type` is forced to `equip` and left out of URLs, and `type_options` is `[]` on class tabs, so Gear shows first. Beginner = equips with `jobs == []`.
- Home `classes` cards now use `hat_id`/`hat` (each class's iconic hat) instead of an NPC portrait. New home variable `monster_field` = {total, bands: [{label, url, monster: {id, name, level}}]} (`browse.home_monster_field`; tutorial mobs skipped).
- Title font "Luckiest Guy" is self-hosted at /static/fonts/LuckiestGuy-Regular.ttf (OFL). `.title-text` / `.class-name` name it directly, because a `var()` there didn't apply.
- **v2.3 (Lead Dev):** class cards show a class character image at /static/img/classes/{class}.png (rendered once with maplestory.io from GMS v83 items; credited in the footer). The title font is now Nexon's free "Maplestory" font (Bold/Light), trimmed to Latin letters and self-hosted as /static/fonts/Maplestory-{Bold,Light}.woff2. Luckiest Guy has been removed.

## v2.4 changes (backend-dev, 2026-10-12, from the MeowDB cross-check)
- **Sell price:** `sellable` is `True` (price known) or `None` (NULL = unknown). item.html shows "NPC sell price: Unknown" instead of "Can't be sold to NPCs".
- **Drop wording:** drops with `confidence == "estimated"` (older v83 data) get an "Older-version estimate" pill, and the drop list adds the line "Older-version estimate. May not drop in Classic." (macros `rate_pill`, `old_version_note`). Verified/player rates are unchanged.
- **Hidden monsters:** `Monster.hidden = True` mobs are left out of `/monsters`, search + `/api/search`, home `monster_field`, `counts.monsters` and item-page "Dropped by". `/monsters/{id}` still loads and shows a "Test/unreleased monster" notice (`monster.hidden`).
- **Notes:** `monster.note` and `NpcRef.note` (str or None) show as a small notice (`m.notice`) on monster/NPC pages; `/shops` cards show the NPC note as a pill.
- All of this reads the new columns with `getattr`, so pages work before and after data-engineer adds them.
