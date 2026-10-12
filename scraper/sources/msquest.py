"""Scrape drop tables and NPC shops from MapleStory Quest (https://maplestory.quest).

Why this site: OSMS has items/monsters/NPCs from the game client, but drop tables
and shop stock are NOT in the client. MapleStory Quest lists both.

What we fetch (all allowed by its robots.txt, which only blocks /api/, /market,
and query-string listing pages):
    /monsters/{id}  -> "Drop table" (older-version rates) + "Confirmed drops" (player-seen)
    /npcs/{id}      -> "What <NPC> sells" (shop stock + price)
    /items/{id}     -> NPC sell value (only fetched for scrolls, which OSMS gives no price)

Pages go through PoliteFetcher: robots.txt check, 2s between requests, disk cache.
"""
import re

import httpx
from bs4 import BeautifulSoup

from scraper.base import BlockedByRobots, PoliteFetcher

BASE_URL = "https://maplestory.quest"
SOURCE_NAME = "MapleStory Quest"
SOURCE_URL = BASE_URL + "/"
RATE_SOURCE = "Older game version (v83), via MapleStory Quest"

ITEM_LINK = re.compile(r"^/items/(\d+)")
ITEM_ICON = re.compile(r"/assets/items/0*(\d+)\.png")


def _sections(html: str):
    """Yield (section heading, item_id, row text) for every item link on the page."""
    soup = BeautifulSoup(html, "html.parser")
    main = soup.find("main") or soup.body
    heading = ""
    for el in main.find_all(["h2", "a"]):
        if el.name == "h2":
            heading = el.get_text(" ", strip=True)
            continue
        match = ITEM_LINK.match(el.get("href", ""))
        if not match:
            continue
        row = el.find_parent(["li", "tr"])
        text = row.get_text(" | ", strip=True) if row else el.get_text(strip=True)
        yield heading, int(match.group(1)), text


def parse_monster_page(html: str) -> list[dict]:
    """Return drops: [{item_id, drop_rate (0..1 or None), confidence}]."""
    drops: dict[int, dict] = {}
    for heading, item_id, text in _sections(html):
        if heading.startswith("Drop table"):
            pct = re.search(r"([\d.]+)\s*%", text)
            rate = round(float(pct.group(1)) / 100, 6) if pct else None
            entry = drops.setdefault(item_id, {"item_id": item_id, "drop_rate": None, "confidence": "estimated"})
            if entry["drop_rate"] is None:
                entry["drop_rate"] = rate
        elif heading.startswith("Confirmed drops"):
            entry = drops.setdefault(item_id, {"item_id": item_id, "drop_rate": None, "confidence": "verified"})
            entry["confidence"] = "verified"  # a player saw it drop in Classic
    return list(drops.values())


def _row_item_id(row) -> int | None:
    """Item ID for one list row: from an /items/{id} link, or else from the
    item icon (/assets/items/02040004.png). Some shop rows (e.g. scrolls) have no link."""
    link = row.find("a", href=ITEM_LINK)
    if link:
        return int(ITEM_LINK.match(link["href"]).group(1))
    icon = row.find("img", src=ITEM_ICON)
    if icon:
        return int(ITEM_ICON.search(icon["src"]).group(1))
    return None


def parse_npc_page(html: str) -> list[dict]:
    """Return shop stock: [{item_id, buy_price}] from the "What <NPC> sells" panel."""
    soup = BeautifulSoup(html, "html.parser")
    stock: dict[int, dict] = {}
    for h2 in soup.find_all("h2"):
        if " sells" not in h2.get_text(" ", strip=True):
            continue
        panel = h2.find_parent("section") or h2.parent
        for row in panel.find_all("li"):
            item_id = _row_item_id(row)
            numbers = re.findall(r"\d[\d,]*", row.get_text(" | ", strip=True))
            if item_id and numbers:
                # the price is the last number in the row
                stock.setdefault(item_id, {"item_id": item_id, "buy_price": int(numbers[-1].replace(",", ""))})
    return list(stock.values())


def parse_npc_identity(html: str) -> tuple[str | None, str | None]:
    """Who this NPC page is about: (name, map name or None).

    The name is the page's <h1>. The map comes from the intro sentence,
    e.g. "Sam is an NPC ..., found in Henesys Weapon Store (Victoria Island)."
    Pages for NPCs the client puts on no map have no "found in", so map is None."""
    soup = BeautifulSoup(html, "html.parser")
    h1 = soup.find("h1")
    name = h1.get_text(" ", strip=True) if h1 else None
    main = soup.find("main") or soup.body
    found = re.search(r"found in (.+?) \(", main.get_text(" ", strip=True))
    return name, (found.group(1).strip() if found else None)


def _same(a: str | None, b: str | None) -> bool:
    """Compare two names loosely (ignore case and extra spaces)."""
    return " ".join((a or "").lower().split()) == " ".join((b or "").lower().split())


def npc_page_matches(html: str, expected_name: str, expected_map: str | None) -> tuple[bool, str]:
    """Check an MSQ NPC page is really the OSMS NPC we asked for.
    MSQ and OSMS use the same IDs for almost every NPC, but not always, so we
    only trust a shop list when the name (and map, when both sides have one) agree.
    Returns (ok, reason)."""
    name, map_name = parse_npc_identity(html)
    if not _same(name, expected_name):
        return False, f"name differs (MSQ '{name}' vs OSMS '{expected_name}')"
    if map_name and expected_map and not _same(map_name, expected_map):
        return False, f"map differs (MSQ '{map_name}' vs OSMS '{expected_map}')"
    return True, "ok"


def parse_item_npc_price(html: str) -> int | None:
    """What an NPC pays you for this item (mesos), from an /items/{id} page.

    The site says this value comes from the game client and is shown on each item
    page. We look for a label like "NPC buy price" / "NPC pays" followed by a number.
    Returns None when the page has no such value (true for every scroll we checked:
    the client gives scrolls no NPC price)."""
    soup = BeautifulSoup(html, "html.parser")
    main = soup.find("main") or soup.body
    text = main.get_text(" | ", strip=True)
    match = re.search(r"(?i)npc\s*(?:buy\s*price|pays(?:\s*you)?|sell\s*price)\s*[|:]*\s*([\d,]+)", text)
    return int(match.group(1).replace(",", "")) if match else None


def scrape_item_prices(item_ids: list[int], log=print) -> dict[int, int | None]:
    """Fetch /items/{id} for each ID and return {item_id: npc price or None}."""
    fetcher = PoliteFetcher()
    prices: dict[int, int | None] = {}
    try:
        for n, item_id in enumerate(item_ids, 1):
            url = f"{BASE_URL}/items/{item_id}"
            try:
                prices[item_id] = parse_item_npc_price(fetcher.get(url))
            except httpx.HTTPStatusError as e:
                log(f"  [{n}/{len(item_ids)}] skip {url} ({e.response.status_code})")
            except BlockedByRobots:
                log(f"  robots.txt blocks {url}, stopping")
                break
            if n % 50 == 0 or n == len(item_ids):
                log(f"  [{n}/{len(item_ids)}] item pages")
    finally:
        fetcher.close()
    return prices


def scrape(monster_ids: list[int], npc_ids: list[int], log=print,
           npc_info: dict[int, tuple[str, str | None]] | None = None) -> tuple[dict, dict]:
    """Fetch every monster and NPC page. Returns ({monster_id: drops}, {npc_id: stock}).

    npc_info = {npc_id: (OSMS name, OSMS map name)}. When given, an NPC page's shop
    is only kept if the page is about that same NPC (see npc_page_matches)."""
    fetcher = PoliteFetcher()
    drops, shops = {}, {}
    npc_info = npc_info or {}

    def parse_npc_checked(html: str, npc_id: int) -> list[dict]:
        stock = parse_npc_page(html)
        if stock and npc_id in npc_info:
            ok, reason = npc_page_matches(html, *npc_info[npc_id])
            if not ok:
                log(f"  NPC {npc_id}: shop skipped, page is a different NPC ({reason})")
                return []
        return stock

    total = len(monster_ids) + len(npc_ids)
    done = 0
    try:
        for kind, ids, parser, out in (
            ("monsters", monster_ids, lambda html, _id: parse_monster_page(html), drops),
            ("npcs", npc_ids, parse_npc_checked, shops),
        ):
            for obj_id in ids:
                done += 1
                url = f"{BASE_URL}/{kind}/{obj_id}"
                try:
                    out[obj_id] = parser(fetcher.get(url), obj_id)
                except httpx.HTTPStatusError as e:
                    log(f"  [{done}/{total}] skip {url} ({e.response.status_code})")
                    continue
                except BlockedByRobots:
                    log(f"  [{done}/{total}] robots.txt blocks {url}, skipping")
                    continue
                if done % 25 == 0 or done == total:
                    log(f"  [{done}/{total}] fetched")
    finally:
        fetcher.close()
    return drops, shops
