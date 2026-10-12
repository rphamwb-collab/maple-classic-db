# Design Plan: "Maple World UI" (Phase 3)

Owner: frontend-dev. Status: **approved by the user, built in Phase 3**. (The browser URL param is `class`, not `job`; level filter uses backend range chips instead of min/max inputs.)

## Subject, audience, job
- Subject: a fan database for MapleStory Classic (pre-Big-Bang Maple World: Henesys, Ellinia, Perion, Kerning City).
- Audience: players mid-grind, often on a phone next to the game, who want one answer fast ("who drops this?", "what does it sell for?").
- Primary job: find an item and see how to get it and what it's worth.

## Concept
The site looks like the game's own UI, not a website wearing a theme.
- Pages are made of **game windows**: a light panel with a thick rounded wood-brown border and a small title strip, like the in-game Inventory, Shop and Quest windows.
- The **item page centrepiece is the in-game item tooltip**: a dark navy rounded box with the item name in gold, centred, then REQ LEV / REQ STR lines, job names (yours lit, others dim), a dashed divider, and stat lines. This is the one bold, memorable element; everything else stays quiet.
- The art you already liked (item icons, monster and NPC sprites) is the colour. Sprites sit on small "inventory slot" squares so mismatched art sizes look tidy.
- No Nexon logos, fonts or artwork beyond the game-data images we already credit. The leaf mark is a plain CSS/emoji maple leaf, not the MapleStory logo.

## Palette
Light mode: sky over Maple Island.

| name | hex | use |
|---|---|---|
| Lith Sky | `#D7ECF8` | page background |
| Window Paper | `#FFFDF6` | window/panel body |
| Maple Wood | `#8A5A2B` | window borders, title strips, headings |
| Leaf Orange | `#E8771B` | primary action (buttons, active tab, links on hover) |
| Henesys Green | `#4E9A2E` | success, "you can wear this", observed rates |
| Tooltip Navy | `#1D2846` | item tooltip box (also chart line) |
| Tooltip Gold | `#FFCF3F` | item name inside tooltip |
| Ink | `#2E2418` | body text (warm, not grey) |
| Bark Muted | `#7D6A55` | secondary text |

Dark mode: Maple World at night (Ellinia after dark).

| name | hex | use |
|---|---|---|
| Night Sky | `#121B2E` | page background |
| Night Window | `#1C2840` | window body |
| Moon Rim | `#6F86B3` | window borders, title strips |
| Lantern Orange | `#FF9A3C` | primary action |
| Moss Green | `#7CC45A` | success |
| Tooltip Navy | `#0C1326` | tooltip (darker than windows so it still pops) |
| Tooltip Gold | `#FFD34F` | item name |
| Star Text | `#E9EEF8` | body text |
| Dusk Muted | `#9FAAC2` | secondary text |

Rule: orange is only for things you can click or the current selection. Green only for "good/success". Never decorative gradients; the only gradient is the soft sky fade behind the header.

## Typography (Google Fonts)
- **Fredoka** (600) for headings, tabs and buttons: round, chunky, playful, close to the game's friendly lettering without copying it.
- **Nunito** (400/700) for body text and tables: rounded and very readable on phones.
- **DotGothic16** only inside the item tooltip and the in-game-style price tags: a bitmap-style face that evokes the old Korean client's pixel UI font. Used nowhere else.
- Scale (1.25 ratio): 0.8 / 1 / 1.25 / 1.56 / 1.95 / 2.44 rem. Body 16px, line-height 1.55. Numbers use tabular figures. Sentence case everywhere; no all-caps labels except the game's own tooltip lines (REQ LEV), which are part of the reference.

## Components
- **Window**: `.win` = rounded 14px, 3px Maple Wood border, title strip (Fredoka, small sprite on the left). Inner content padded. Replaces Pico `<article>` cards.
- **Slot**: 44px rounded square with an inset shadow, holds an icon centred and pixel-crisp (`image-rendering: pixelated`).
- **Tabs (class tabs)**: look like inventory tabs: rounded top corners, attached to the window below; active tab is raised, orange underline, picture + label.
- **Filter chips**: pill buttons with a 20px icon; selected = orange fill. Hidden sub-filters (slot, weapon type) slide open only when their parent is chosen.
- **Meso price**: number + a small gold coin dot, DotGothic16, e.g. `● 12,500`.
- **Rate pill**: known rate (navy), observed (green), unknown (dashed outline, muted "Unknown").
- **Empty states**: a dashed window with a sprite (Snail for "no drops", a meso bag for "no prices"), one sentence, and the action button.

## Wireframes (desktop; phone = same blocks stacked, tabs scroll sideways)

### Home
```
+--------------------------------------------------------------+
| (leaf) Maple Classic DB      Items  Monsters  NPCs   [search] |
+--------------------------------------------------------------+
|   Find any item, monster or NPC in Maple World               |
|   [ Search "Red Potion", "Snail", "Ellinia"...        (Go) ] |
|   2,220 items · 88 monsters · 226 NPCs                        |
+--------------------------------------------------------------+
| Browse by class  (window)                                    |
|  [img All] [img Beginner] [img Warrior] [img Magician] ...    |
+--------------------------------------------------------------+
| Shortcuts (window)          | Recently priced (window)        |
| [slot] Equips  [slot] Use   | [slot] Ilbi ....... 12.5m       |
| [slot] Scrolls [slot] Etc   | [slot] Red Potion .... 45       |
| [sprite] Monsters by level  |  (only if backend can supply)   |
| [sprite] Shops by town      |                                 |
+--------------------------------------------------------------+
```
Left-aligned. Counts are a single quiet line, not big stat tiles.

### Item browser (/items)
```
+--------------------------------------------------------------+
| Items                                                         |
| _[All]_[Beginner]_[Warrior]_[Magician]_[Bowman]_[Thief]_  <- tabs
|+------------------------------------------------------------+|
|| Type:   (o)Equip (o)Use (o)Etc (o)Setup (o)Scroll           ||
|| Slot:   (o)Weapon (o)Hat (o)Top ...       <- only if Equip   ||
|| Weapon: (o)1H Sword (o)2H Axe ...         <- only if Weapon  ||
|| Level:  [ 0 ] to [ 200 ]                     [Clear filters] ||
|+------------------------------------------------------------+|
|| 142 items                                                   ||
|| +------+ +------+ +------+ +------+ +------+ +------+       ||
|| |[slot]| |[slot]| |[slot]| |[slot]| |[slot]| |[slot]|       ||
|| |Name  | |Name  | |Name  | |Name  | |Name  | |Name  |       ||
|| |Lv 30 | |Lv 35 | |...   | |      | |      | |      |       ||
|| |Warrior| ...                                              ||
|| +------+ +------+ ...            [ Load more / pages ]      ||
|+------------------------------------------------------------+|
```
Tabs and chips are plain links (`<a href="/items?job=warrior&type=equip">`) with `hx-get` + `hx-push-url`, so the URL is always shareable and it works without JS. Only the results+filters panel swaps.

### Item page
```
+--------------------------------------------------------------+
| Items > Warrior > Weapon > Two-Handed Sword        (breadcrumb)
|                                                               |
| +---------------------+   +--------------------------------+ |
| |   TOOLTIP (navy)    |   | How to get it (window)          | |
| |     Zard (gold)     |   |  Buy  [sprite] Mr. Smith ... 5k | |
| | [slot]  REQ LEV: 43 |   |  Drop [sprite] Fire Boar  0.5%  | |
| |  big    REQ STR:135 |   |       [sprite] Wild Boar  ?     | |
| |  icon   REQ DEX: 0  |   |  Craft [i][i][i] + 10,000 mesos | |
| | Beginner WARRIOR ...|   |  Quest  "Quest name" reward     | |
| | ------------------- |   +--------------------------------+ |
| | Weapon type: 2H Swd |   | Used in (window)               | |
| | Attack Speed: Normal|   |  [slot][slot] recipes...       | |
| | STR +2  W.ATT +55   |   +--------------------------------+ |
| | Upgrades: 7         |                                      |
| | Sells for: 21,000   |                                      |
| |  "flavour text..."  |                                      |
| +---------------------+                                      |
|                                                               |
| Market (window)                                               |
|  Median 30d  ● 1.2m   Range 900k - 1.5m   14 reports          |
|  [ chart, or empty state: meso bag + "No prices reported yet. |
|    Be the first." (Report a price) ]                          |
|  Report a price: [price] [qty] [world v] (Submit)             |
|  > Recent reports                                             |
+--------------------------------------------------------------+
```
On phones the tooltip goes first, full width, then "How to get it", then Market.

### Monster page
```
+--------------------------------------------------------------+
| +------------------+  Snail                                   |
| |  sprite on sky   |  Lv 1   HP 8   EXP 3                     |
| |  card (big)      |  Found in: [Maple Island map] [...]       |
| +------------------+                                          |
| Drops (window: inventory grid, like looting)                  |
|  [slot]Snail Shell   [slot]Red Potion   [slot]Meso ...        |
|   known 60%           Unknown            observed 2.1% (n=400)|
| Report a drop (window, form)                                  |
+--------------------------------------------------------------+
```

### NPC page
```
+--------------------------------------------------------------+
| +-----------+  Mr. Smith                                      |
| |  sprite   |  Henesys Market, Henesys                         |
| +-----------+                                                 |
| Shop (window styled like the in-game shop list)               |
|  [slot] Red Potion ........................ ● 50              |
|  [slot] Orange Potion ..................... ● 160             |
+--------------------------------------------------------------+
```

### /monsters and /npcs browse
- Monsters: level-band chips (1-10, 11-20, ...) + sprite card grid (sprite on slot, name, Lv).
- NPCs: grouped by town, each town a window with its NPC sprites in a grid; shopkeepers get a coin badge.

## Principles
1. **One bold thing per page**: the tooltip on items, the big sprite card on monsters/NPCs. Everything else is quiet windows.
2. **Pictures do the work**: every tab, filter and row has an icon. Text is short.
3. **Honest data**: unknown rates look clearly unknown (dashed, muted); player data is always labelled "player-reported" with sample size.
4. **Empty is an invitation**: every empty state says what to do next and has the button for it.
5. **Phone first**: tabs and chips scroll sideways, grids reflow to 3 columns, no table wider than the screen.
6. **Quality floor**: visible orange focus ring, `alt` text on meaningful images (decorative sprites next to a name get `alt=""`), reduced-motion respected, AA contrast in both modes.

## Review against the brief (what I changed)
- First draft used a cream background + serif headings: that is the generic "warm" default. Replaced with sky blue + rounded Fredoka, which comes from the game's own Maple Island setting.
- First draft used big number stat tiles on Home: generic dashboard look. Replaced with one quiet count line under search.
- Considered a pixel font everywhere: hard to read on phones. Kept it only inside the tooltip, where it carries the reference.

## Data I'll need from backend-dev (api-contract v2)
- `/items` browser: tab + filter options each with `icon_item_id`, counts, results, paging.
- Item page: crafting (ingredients + meso cost), quest rewards, "used in", job requirement stats (req_str etc.), attack speed if available.
- Home: counts; optional "recently priced" list.
- `/monsters`, `/npcs` browse data.
