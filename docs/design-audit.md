# Design note: /audit "Data quality" page (Phase 4)

Owner: frontend-dev. Status: **waiting for approval**. Builds on `docs/design-plan.md` (Maple World UI): same palette, fonts, `.win` windows, pills, chips and empty states. No new colours or fonts.

## Subject, audience, job
- Subject: an honest "what we're not sure about" list for the database.
- Audience: curious players and the site owner checking the data after a refresh.
- Job: show at a glance how many problems each check found, then let you jump to the item or monster that needs a look.

## Concept: the Quest Log
The in-game Quest Log is where Maple players already look for "things left to do". The audit page borrows it:
- The checks are **quest entries**, each with a count. Zero means the check is "completed" (green tick, "All clear").
- The `?check=` tabs look like the Quest Log tabs, reusing the existing inventory-tab style.
- This is the one memorable idea on the page; the tables below stay plain.

## Layout (desktop; phone = same blocks stacked)
```
+--------------------------------------------------------------+
| Data quality                                                  |
| Automatic checks on our game data plus what players report.   |
| Last checked: 2026-10-12 (from the latest data refresh)       |
+--------------------------------------------------------------+
| [scroll] No way to get it   [Snail] Mobs with no drops       |
|          214 items                   6 monsters               |
| [?] Unknown or old rates    [!] Source disagreements          |
|          1,203 drops                 31 rows                  |
| [check] Player-confirmed    [!] Rate mismatch   [+] Reported  |
|          12 drops               2 drops         but missing 4 |
+--------------------------------------------------------------+   <- summary cards = links to ?check=
| _[All]_[No source]_[No drops]_[Rates]_[Sources]_[Players]_     |   <- tabs, scroll sideways on phone
|+------------------------------------------------------------+|
|| No way to get it (214)                                      ||
|| These items have no drop, shop, recipe or quest that gives  ||
|| them. Some are event or cash items; some are missing data.  ||
||  [slot] Zard ............ Equip · Lv 43                     ||
||  [slot] Blue Snail Shell  Etc                               ||
||  ... first 50, then "Show all 214" link (?check=no-source)  ||
|+------------------------------------------------------------+|
| (next check's window, when tab = All)                         |
+--------------------------------------------------------------+
```
- Left aligned throughout. Intro is one sentence, not a banner.
- **Summary cards**: a 2-column grid on phones, 3-4 on desktop. Each is a small `.win`-style link: icon slot, label (Nunito 700), count (Fredoka 1.56rem, tabular figures). A count of 0 shows a green tick and "All clear" instead of a number. Card with the current `?check=` gets the orange "selected" border, same rule as chips (orange only for clickable/selected).
- **Tabs**: plain `<a href="/audit?check=...">` links (no HTMX, as planned). "All" shows every check's window, limited to the first rows each; a single tab shows that check's full table.
- **One window per check**: title strip = check name + count, then one sentence saying what the check means in player words, then the table.

## Table columns per check (all names link to /items/{id} or /monsters/{id})
| check | columns |
|---|---|
| No way to get it | item (slot icon + name), type |
| Mobs with no drops | monster (sprite + name), level |
| Unknown or old rates | item, monster, rate pill (reuses `rate_pill`) |
| Source disagreements | ID, what differs (e.g. "Name: OSMS 'X' vs MapleStory Quest 'Y'"), kind |
| Player-confirmed | item, monster, kills reported, times seen |
| Rate mismatch | item, monster, listed rate pill, observed pill (with n kills) |
| Reported but not in our table | item, monster, times seen, kills reported |

Tables sit in `.table-wrap` (scroll sideways on phones). On phones the less important columns (type, level) are hidden so no table is wider than the screen.

## Empty states (from the design plan: "empty is an invitation")
- Check with 0 rows: dashed `.empty-state` box, tick icon, "All clear. Nothing to look at here."
- Player checks with 0 rows: "No player reports to compare yet." plus a button "Find a monster to report drops" linking to /monsters.
- Source disagreements before any scrape: "Run a data refresh to compare sources."

## Player-confirmed pill (item and monster drop lists)
- Shown when an older-version (`estimated`) drop has been seen by players at least once.
- Look: `.pill-confirmed` = green-ink text, 2px solid green border, paper background, a small ✓ before "Player-confirmed". Outlined, not filled, so it stays different from the filled green "observed rate" pill.
- Title text (hover / long-press): "Players reported seeing this drop, so it does exist in Classic."
- Placed right after the "Older-version estimate" pill it answers.

## Footer
- Add one line: "Data quality: see what we're unsure about" linking to `/audit`, next to the "player-reported" note.

## Review against the brief (what I changed)
- First draft used big number stat tiles across the top: the generic dashboard look the design plan already rejected. Kept the counts (the brief asks for them) but made them small quest-entry cards with an icon slot, and a 0 count says "All clear" instead of a big "0".
- Considered red/amber severity colours for each check: that adds a new colour system. Dropped it; the existing warn pill outline is enough, and green stays only for "good".

## Data I need from backend-dev
- Per check: key (for `?check=`), title, count, rows; current `check`; last-run date.
- Row fields: item id/name/icon, monster id/name, rate data in the shape `rate_pill` / `observed_pill` already accept.
- On drop dicts for item and monster pages: a `player_confirmed` boolean.
