# Design note: World map and "Show on map" pings (Phase 5)

Owner: frontend-dev. Status: **waiting for approval**. Builds on `docs/design-plan.md` (Maple World UI): same palette, the same fonts (Maplestory for the section title, Fredoka, Nunito, DotGothic16), `.win` windows, `.tabs`, slots and pills. No new colours or fonts.

## Subject, audience, job
- Subject: where things are in Maple World (Maple Island and Victoria Island).
- Audience: players mid-grind, often on a phone next to the game, asking "where do Pigs spawn?" or "which town is this shop in?"
- Job: show a place on a picture the player already knows, then list what's there.

## Concept: the in-game World Map window (the W key)
Every player has opened the game's World Map: a framed window with the island painted on it, small dots on each map, and a tab for each region. We copy that window instead of inventing a map widget.
- **The map picture is the bold thing.** It's the real v83 world map art (from data-engineer), shown big, pixel-crisp (`image-rendering: pixelated`), inside a normal `.win`. Everything around it stays quiet.
- **Spots** are small round markers drawn on top of the art, like the game's map dots. Towns get a label in the window's own title style (Fredoka on a paper tag); field spots are just dots until you hover or select them.
- **The ping** is the game's "you are here" blink, redrawn in our Leaf Orange: a solid dot with rings that grow and fade.

## 1. Home "World map" window
Placed between "Choose your class" and "Hunt monsters", with the same `showcase-head` header as its neighbours.

```
 World map                                See all shops by town
+--------------------------------------------------------------+
| _[Maple Island]_[Victoria Island]_          <- .tabs (inventory tabs)
|+------------------------------------------------------------+|
||                                                            ||
||            (Ellinia)                                        ||
||        o     o                    (Perion)                  ||
||    o                      o   o     [Perion]                ||
||  [Henesys] O      o                   o                     ||
||       o         [Kerning City]  o                           ||
||   o        o                 (Lith Harbor)                  ||
||                                                             ||
||  map art, full window width, keeps its own aspect ratio     ||
|+------------------------------------------------------------+|
|| Tap a spot to see its maps, monsters and shops.             ||   <- .win-note
|+------------------------------------------------------------+|
```
- **Tabs:** Victoria Island is selected first (it's where most of the game is). The tabs are `<button role="tab">` with `aria-selected`; switching swaps the picture and its spots with no page load. If JavaScript is off, both islands show one under the other (the data is server-rendered from `world_maps`), so nothing is lost.
- **Markers:** positioned in percent (`left: x / width * 100%`), so they stay on the right spot at any size.
  - Field spot: 14px dot, paper fill, 2px wood border.
  - Town spot: 18px dot plus a small label tag under it (paper background, wood border, Fredoka 600, 0.8rem). Towns: Henesys, Ellinia, Perion, Kerning City, Lith Harbor, Sleepywood, Amherst, Southperry.
  - Hover/focus: the dot fills orange (orange = clickable/selected, per the design plan).
  - Selected spot: orange fill plus a still orange ring (no animation; the ring only pulses in the ping dialog).
- **Tap targets:** each marker is a `<button>` whose hit area is at least 32px across (the visible dot is smaller, the padding is invisible). On phones the hit area grows to 40px. Where spots are crowded the buttons can overlap a little; the one nearest the finger wins, which is fine for a map.

## 2. Spot panel
Opens when a spot is clicked. Desktop: a `.win` beside the map (map about 2/3, panel 1/3). Phone: below the map, and the page scrolls to it.

```
+--------------------------------+
| Henesys                    [x] |   <- win-title: spot name, close button
|--------------------------------|
| Maps                            |
|  Henesys · Henesys Market ·     |   <- pill-tag chips (not links: we
|  Henesys Hunting Ground I       |      have no map pages)
| Monsters                        |
|  [sprite] Snail        Lv 1     |   <- .rows, each links to /monsters/{id}
|  [sprite] Orange Mushroom Lv 8  |
| Shops                           |
|  [sprite] Rina                  |   <- .rows, each links to /npcs/{id}
|  [sprite] Mr. Smith             |
+--------------------------------+
```
- Before anything is clicked the panel shows a quiet empty state: "Pick a spot on the map to see what's there." (the "empty is an invitation" rule).
- Monster sprites come from `/static/img/monsters/{id}.webp`, NPC sprites from `/static/img/npcs/`, both through the existing `m.art` / slot styles, with the placeholder fallback.
- Empty groups are left out. A spot with nothing known says "We don't have monsters or shops listed for this spot yet."
- Long lists (a town with 20 maps) show the first 8 maps and a "Show all 20" toggle.
- The panel has `aria-live="polite"` so screen readers hear the new spot name.

## 3. "Show on map" ping buttons
A small text button with the pin emoji: **📍 Show on map**. Pico's `secondary outline` button, shrunk to pill size so it sits next to the pills.
- **Monster page:** each "Found in" pill gets its own pin button inside it (`[Henesys Hunting Ground I 📍]`), plus one "📍 Show all on map" after the list (only when `has_pings`).
- **Item page, "Dropped by":** one "📍 Map" button under each monster's level line. It pings all of that monster's spots.
- **NPC page:** "📍 Show on map" next to the location line.
- **/shops:** a "📍" button in the corner of each shop card (the card itself stays a link to the NPC).
- Buttons are only drawn when there is a place to show (the monster has map ids, the NPC has a `map_id`). Without JavaScript they're links to `/api/locate?...`; with JavaScript they open the dialog.

## 4. Ping dialog
One shared `<dialog>` in `base.html`, filled by `worldmap.js`. It's a `.win`:

```
+---------------------------------------------+
| Snail on the map                        [x] |   <- title: "<thing> on the map"
|---------------------------------------------|
| _[Maple Island 3]_[Victoria Island 5]_      |   <- tabs only if pings span 2 islands;
|  +---------------------------------------+  |      counts = pings on each
|  |                                       |  |
|  |        (( o ))       (( o ))          |  |   <- pulsing pings
|  |                 (( o ))               |  |
|  +---------------------------------------+  |
|  Henesys Hunting Ground I                   |   <- list of the pinged map names,
|  Snail Hunting Ground II (near Henesys)*    |      same order as the pings
|  * Shown at the nearest town: exact spot    |
|    not known.                               |
+---------------------------------------------+
```
- Opens on the island with the most pings. Closing: the X button, Esc, or a click on the dark backdrop. Focus returns to the button that opened it.
- Backdrop: `rgba(18, 27, 46, 0.55)` (Night Sky at 55%), the same in both modes.
- **Inexact spots** (`exact: false`, the fallback to a town): the ping is drawn with a dashed ring and no fill, and the map name in the list gets "(approximate: shown at the town)". Honest data: we don't pretend to know the exact spot.
- Several maps on the same spot get one ping with a small count badge ("3") instead of stacked rings.
- Loading: the dialog opens at once with the map and a "Finding spots…" line, then the pings appear. Error: "Couldn't load the map. Try again." with a "Try again" button.

## 5. Ping animation
- A 12px Leaf Orange dot with a 2px white (light) / Night Sky (dark) outline, so it reads on any part of the art.
- Two rings grow from 12px to 44px and fade from 70% to 0% opacity, 1.6s, staggered by 0.8s, repeating. CSS `@keyframes` only, `transform: scale()` + `opacity`, so it stays smooth on phones.
- **Reduced motion:** with `prefers-reduced-motion: reduce` the rings don't move. Instead each ping shows one still ring at 28px, 2px solid orange. The ping still stands out without movement.
- Only the dialog pings animate. The home map has no looping motion.

## 6. Phone layout (390px)
- The map image is `width: 100%; height: auto`, so it shrinks to fit; markers are positioned in percent and stay on their spots.
- Tap targets stay at least 40px (invisible padding around a 14-18px dot), even when the map is small.
- On phones, field-spot town labels shrink to 0.7rem and only town labels show; field spots show their name in the panel only.
- Spot panel stacks under the map. Dialog uses `width: min(94vw, 760px)` and the map list under the art scrolls if long.
- Tabs scroll sideways, like every other tab row on the site.

## 7. Dark mode
- The map art stays as is (it's a painted picture) but gets `filter: brightness(0.85)` in dark mode so it doesn't glare against the night windows.
- Markers swap with the tokens: paper fill becomes Night Window, wood border becomes Moon Rim, orange becomes Lantern Orange. The ping outline becomes Night Sky so it pops on the dimmed art.
- Town label tags use `--mw-paper` / `--mw-ink`, so they follow the theme automatically.

## 8. Keyboard and screen readers
- Every marker is a real `<button>` with `aria-label="Henesys: 4 maps, 3 monsters, 2 shops"`. Tab moves through them in reading order (top-left to bottom-right); Enter/Space opens the panel. The visible focus ring is the site's existing orange ring.
- Island tabs follow the tabs pattern: Left/Right arrows move between tabs.
- The map image has `alt="Victoria Island world map"`; the marker buttons carry the real information.
- The dialog is a native `<dialog>` opened with `showModal()`, so focus is trapped and Esc closes it. Its title is the dialog's `aria-labelledby`. The list of map names under the art means the pings are never the only way to get the answer.

## Credits
Footer line: "World map from the v83 game files via maplestory.io", next to the existing maplestory.io credit.

## Review against the brief (what I changed)
- First draft was a generic web map (zoom buttons, drop-pin icons, a Google-Maps-style side drawer). That's how any site shows locations, and it fights the game look. Replaced it with the game's own World Map window: tabs, dots and the "you are here" blink, all things players already know.
- Considered a scrollable/zoomable map on phones: complex and fiddly with one thumb. Dropped it; the map scales to fit and the tap areas are padded instead.
- Considered showing every field spot's name on the map: too crowded, especially on Victoria Island. Only towns are labelled; the panel names the rest.

## Data (backend-dev's contract v2.6 in docs/api-contract.md, already posted)
- Home: `world_maps` (Maple Island first), embedded in the page with `tojson`, so the home map needs no fetch.
- Ping dialog: `GET /api/locate?monster=|npc=|map=` for the pings (`exact`, `map_names`, `unplaced`), plus `GET /api/world/{world}` once per island for its image and size (kept in memory after the first load).
- `exact: false` pings get the dashed "approximate" ring and "(approximate: shown at the town)" in the list. `unplaced` names are listed as "Not on the map yet: ...".
- Shop NPCs in the panel: only `npcs` with `has_shop` are listed under "Shops"; others under "NPCs".
- Monster page: `found_in` + `has_pings`. Item "Dropped by": `drops[].monster_id` + `has_pings`. NPC page, /shops, "where to buy": `npc.map_id` / `npc.world` (no button when `world` is None).
