# Data Contract (v2, Phase 3)
Owner: data-engineer. If a field name changes, data-engineer will message everyone first.

## What changed in v2 (summary)
- `items` gets 3 new columns: `equip_slot`, `weapon_type`, `jobs`. Old `job` and `sub_type` stay as-is.
- Scrolls stay `category = "use"`, `sub_type = "Scroll"` (no new category).
- New tables: `recipes`, `recipe_ingredients` (crafting), `quest_rewards`.
- `npc_sell_price` NULL = unknown / can't sell. Scrolls: we check MapleStory Quest item pages, but the game client gives scrolls no NPC price, so they stay NULL (the scroll shops, e.g. Tulcus, are now in `shop_items`).
- New imports: `from app.models import Recipe, RecipeIngredient, QuestReward`.

## Basics
- Database: SQLite at `data/maple.db` (SQLAlchemy 2.x).
- Import from code:
  - `from app.db import get_db, init_db, SessionLocal, engine`
  - `from app.models import Base, Source, Item, Monster, Drop, Npc, ShopItem, PriceReport, DropReport, Recipe, RecipeIngredient, QuestReward`
- `get_db()` is a FastAPI dependency: `db: Session = Depends(get_db)`
- `init_db()` creates any missing tables. It is safe to call on startup.
- Fill with sample data: `.venv\Scripts\python -m scraper.seed_sample` (wipes and refills everything).
- Money is whole **mesos** (int). Times are **UTC** `datetime`s without a timezone attached.
- `drop_rate` is a **fraction from 0 to 1** (0.05 = 5%). `NULL` means the rate is unknown.
- Every game-data row links to a `sources` row. In Phase 2 that is always the source named `"sample"`.

## Tables

### `sources` (class `Source`)
| field | type | notes |
|---|---|---|
| id | int PK | |
| name | str, unique | e.g. `"sample"` |
| url | str, nullable | credit link |
| last_scraped | datetime, nullable | |
| notes | str, nullable | |

### `items` (class `Item`)
| field | type | notes |
|---|---|---|
| id | int PK | game item ID (e.g. 2000000 = Red Potion), not auto-generated |
| name | str, indexed | |
| category | str | one of `equip`, `use`, `etc`, `setup` |
| sub_type | str, nullable | e.g. `One-Handed Sword`, `Potion`, `Scroll`, `Hat`, `Monster Drop` |
| level_req | int, nullable | |
| job | str, nullable | `Beginner`, `Warrior`, `Magician`, `Bowman`, `Thief`, or `Any` |
| stats | JSON dict, nullable | keys always lowercase snake_case, values always int. e.g. `{"str": 3, "weapon_attack": 17, "slots": 7}`; scroll: `{"success_rate": 60, "weapon_attack": 2}`. See full key list below |
| description | str, nullable | |
| npc_sell_price | int, nullable | mesos you get when selling to an NPC |
| icon_url | str, nullable | e.g. `/static/img/items/1302000.png`; NULL in sample data |
| equip_slot | str, nullable | **v2.** Exactly one of `Hat`, `Top`, `Bottom`, `Overall`, `Shoes`, `Glove`, `Shield`, `Cape`, `Earring`, `Weapon`. NULL for non-equips |
| weapon_type | str, nullable | **v2.** Only set when `equip_slot = "Weapon"`. Exact OSMS values: `1H Sword`, `2H Sword`, `1H Axe`, `2H Axe`, `1H Blunt Weapon`, `2H Blunt Weapon`, `Spear`, `Polearm`, `Wand`, `Staff`, `Bow`, `Crossbow`, `Claw`, `Dagger` |
| jobs | JSON list[str], never NULL | **v2.** Classes that can use it, from `Warrior`, `Magician`, `Bowman`, `Thief` (capitalized, sorted in that order). `[]` = no class requirement (every class / beginner can use it, and also non-equips) |
| source_id | int FK -> sources.id | |

**Allowed `stats` keys** (all ints; missing key = not applicable):
- Base stats: `str`, `dex`, `int`, `luk`, `hp`, `mp` (show as STR/DEX/INT/LUK/HP/MP)
- Combat: `weapon_attack`, `magic_attack`, `weapon_def`, `magic_def`, `accuracy`, `avoid`, `speed`, `jump`
- Equip: `slots` (upgrade slots)
- Scrolls: `success_rate` (percent, 10/60/100)
- Potions: `heal_hp`, `heal_mp` (flat amount restored)

Relationships: `item.source`, `item.drops` (list[Drop]), `item.shop_items` (list[ShopItem]), `item.price_reports` (list[PriceReport]), `item.drop_reports` (list[DropReport]).
v2: `item.recipes` (list[Recipe] that CRAFT this item), `item.used_in` (list[RecipeIngredient] where this item is an ingredient; use `.recipe` to get the recipe), `item.quest_rewards` (list[QuestReward]).

Filtering tip for `jobs` (SQLite JSON): "usable by Thief" = `jobs = '[]'` OR `jobs LIKE '%"Thief"%'`.

### `monsters` (class `Monster`)
| field | type | notes |
|---|---|---|
| id | int PK | game mob ID (e.g. 100100 = Snail) |
| name | str, indexed | |
| level | int, nullable | |
| hp | int, nullable | |
| exp | int, nullable | |
| maps | JSON list[str], nullable | e.g. `["Henesys Hunting Ground I"]` |
| hidden | bool, default False, indexed | True = test/unreleased mob (Test(Basic), Crimson Balrog...). Hide from normal lists (added 2026-10-12) |
| note | str, nullable | short label, e.g. `"Invincible obstacle (can't be killed)"` (added 2026-10-12) |
| source_id | int FK -> sources.id | |

Alternate mobs carry a suffix in `name`: `"Ligator (KPQ)"`, `"Lupin (2nd Job Test)"`.
Hidden flags, notes and suffixes come from `scraper/corrections.py`.

Relationships: `monster.source`, `monster.drops`, `monster.drop_reports`.

### `drops` (class `Drop`): monster <-> item
| field | type | notes |
|---|---|---|
| id | int PK | |
| monster_id | int FK -> monsters.id | |
| item_id | int FK -> items.id | |
| drop_rate | float, nullable | 0..1; NULL = unknown |
| rate_source | str, nullable | where the rate came from, e.g. `"sample"`; NULL when rate is NULL |
| confidence | str | `unverified`, `estimated`, or `verified` |
| source_id | int FK -> sources.id | |

Unique on (monster_id, item_id). Relationships: `drop.monster`, `drop.item`, `drop.source`.

### `npcs` (class `Npc`)
| field | type | notes |
|---|---|---|
| id | int PK | game NPC ID |
| name | str, indexed | |
| town | str, nullable | `Henesys`, `Ellinia`, `Perion`, `Kerning City`, `Lith Harbor` |
| map_name | str, nullable | e.g. `Henesys Market` |
| note | str, nullable | short label, e.g. `"Not open in this release"` (Luma). Added 2026-10-12 |
| source_id | int FK -> sources.id | |

Relationships: `npc.source`, `npc.shop_items`.

### `shop_items` (class `ShopItem`): npc <-> item
| field | type | notes |
|---|---|---|
| id | int PK | |
| npc_id | int FK -> npcs.id | |
| item_id | int FK -> items.id | |
| buy_price | int | mesos the player pays |
| source_id | int FK -> sources.id | |

Unique on (npc_id, item_id). Relationships: `shop_item.npc`, `shop_item.item`.

### `price_reports` (class `PriceReport`): user-submitted market prices
| field | type | notes |
|---|---|---|
| id | int PK | |
| item_id | int FK -> items.id, indexed | |
| price | int | mesos **per unit** |
| quantity | int, default 1 | |
| world | str | sample values: `Scania`, `Bera`, `Broa` |
| reported_at | datetime, indexed | default now (UTC) |
| reporter_ip | str, nullable | used for rate limiting |
| status | str, default `ok` | `ok` or `flagged` (flagged = hidden from charts/median) |

Relationship: `price_report.item`.

### `drop_reports` (class `DropReport`): user-submitted kill/drop logs
| field | type | notes |
|---|---|---|
| id | int PK | |
| monster_id | int FK -> monsters.id, indexed | |
| item_id | int FK -> items.id, nullable | NULL = "killed N, logged no specific item" |
| kills | int | |
| drops_seen | int, default 0 | how many of item_id dropped in those kills |
| world | str | |
| reported_at | datetime | default now (UTC) |
| reporter_ip | str, nullable | |

Observed rate = sum(drops_seen) / sum(kills) for a (monster, item) pair; show sample size = sum(kills).
Relationships: `drop_report.monster`, `drop_report.item`.

### `recipes` (class `Recipe`): crafting (v2)
| field | type | notes |
|---|---|---|
| id | int PK | OSMS recipe id (not auto-generated) |
| output_item_id | int FK -> items.id, indexed | the item you craft |
| result_count | int | how many you get, usually 1 |
| discipline | str | `Smithing`, `Weaponcrafting`, `Tailoring`, `Woodcrafting`, `Leatherworking`, `Arcforge` |
| discipline_level | int | crafting-skill level needed |
| req_level | int, nullable | character level needed |
| craft_exp | int, nullable | crafting exp gained |
| meso_cost | int, nullable | mesos the craft costs |
| source_id | int FK -> sources.id | |

Relationships: `recipe.output_item` (Item), `recipe.ingredients` (list[RecipeIngredient]), `recipe.source`.

### `recipe_ingredients` (class `RecipeIngredient`) (v2)
| field | type | notes |
|---|---|---|
| id | int PK | |
| recipe_id | int FK -> recipes.id, indexed | |
| item_id | int FK -> items.id, nullable, indexed | NULL when we couldn't match the name to an item: show `item_name` as plain text |
| item_name | str | always set (OSMS only gives names) |
| count | int | |

Relationships: `ingredient.recipe`, `ingredient.item` (Optional[Item]).

### `quest_rewards` (class `QuestReward`) (v2)
One row per (quest, reward item). Only item rewards (not exp/mesos).
| field | type | notes |
|---|---|---|
| id | int PK | |
| quest_id | int, indexed | game quest ID |
| quest_name | str | |
| npc_name | str, nullable | quest giver |
| region | str, nullable | e.g. `Victoria Island`, `Maple Island` |
| level_min | int, nullable | |
| item_id | int FK -> items.id, indexed | |
| count | int | |
| reward_type | str | `guaranteed` (always given), `random` (one of a weighted random pool), `choice` (player picks one) |
| job | str, nullable | if the reward is class-specific: `Beginner`/`Warrior`/`Magician`/`Bowman`/`Thief`; NULL = any class |
| source_id | int FK -> sources.id | |

Relationships: `quest_reward.item`, `quest_reward.source`.

## Sample data (what the seed creates)
- ~30 items (equips, potions, scrolls, etc drops), ~10 monsters with drops, 5 NPC shops.
- ~60 days of price reports for ~6 items, including a few absurd outliers (status `ok`, so backend's IQR filter must handle them) and a couple already `flagged`.
- Some drop reports. Some drops have `drop_rate = NULL` on purpose to test the "unknown" display.
