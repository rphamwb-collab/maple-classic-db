"""Polite web fetcher.

Rules it follows:
- Checks robots.txt before every new site, and refuses pages robots.txt blocks.
- Waits at least 2 seconds between requests (1 request / 2s).
- Saves every page to data/cache/ so we never download the same page twice.
- Sends a clear User-Agent saying who we are.

Allowed sources: MapleStory Quest (robots-allowed pages only) and the OSMS
GitHub data. NEVER point this at Henesys.gg (bans scraping) or MeowDB (terms
ban scrapers without permission). See output/source-audit.md.
"""
import hashlib
import time
from pathlib import Path
from urllib.parse import urlparse
from urllib.robotparser import RobotFileParser

import httpx

PROJECT_ROOT = Path(__file__).resolve().parent.parent
CACHE_DIR = PROJECT_ROOT / "data" / "cache"

USER_AGENT = "MapleClassicDB-bot/0.1 (fan project; contact: see site footer)"
MIN_SECONDS_BETWEEN_REQUESTS = 2.0


class BlockedByRobots(Exception):
    """Raised when robots.txt says we are not allowed to fetch a URL."""


class PoliteFetcher:
    def __init__(self, user_agent: str = USER_AGENT, delay: float = MIN_SECONDS_BETWEEN_REQUESTS):
        self.user_agent = user_agent
        self.delay = delay
        self._last_request_time = 0.0
        self._robots: dict[str, RobotFileParser] = {}  # one parser per site
        self.client = httpx.Client(headers={"User-Agent": user_agent}, timeout=30, follow_redirects=True)
        CACHE_DIR.mkdir(parents=True, exist_ok=True)

    # --- helpers ----------------------------------------------------------
    def _wait_turn(self) -> None:
        """Sleep if the last request was less than `delay` seconds ago."""
        elapsed = time.monotonic() - self._last_request_time
        if elapsed < self.delay:
            time.sleep(self.delay - elapsed)
        self._last_request_time = time.monotonic()

    def _cache_path(self, url: str) -> Path:
        """Each URL gets its own file, named by a hash of the URL."""
        return CACHE_DIR / (hashlib.sha256(url.encode()).hexdigest() + ".html")

    def allowed(self, url: str) -> bool:
        """Ask the site's robots.txt whether we may fetch this URL."""
        parts = urlparse(url)
        site = f"{parts.scheme}://{parts.netloc}"
        if site not in self._robots:
            parser = RobotFileParser()
            self._wait_turn()
            resp = self.client.get(site + "/robots.txt")
            if resp.status_code == 200:
                parser.parse(resp.text.splitlines())
            elif resp.status_code in (401, 403):
                parser.disallow_all = True  # site blocks us entirely
            else:
                parser.allow_all = True  # no robots.txt = no rules
            self._robots[site] = parser
        return self._robots[site].can_fetch(self.user_agent, url)

    # --- main entry point -------------------------------------------------
    def get(self, url: str, use_cache: bool = True) -> str:
        """Return the page's HTML, from cache if we have it."""
        cache_file = self._cache_path(url)
        if use_cache and cache_file.exists():
            return cache_file.read_text(encoding="utf-8")

        if not self.allowed(url):
            raise BlockedByRobots(url)

        self._wait_turn()
        resp = self.client.get(url)
        resp.raise_for_status()
        cache_file.write_text(resp.text, encoding="utf-8")
        return resp.text

    def close(self) -> None:
        self.client.close()
