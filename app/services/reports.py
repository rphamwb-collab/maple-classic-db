"""User-submitted reports: price reports and drop (kill) reports.

Includes simple anti-spam:
  - a per-IP rate limit (kept in memory, so it resets when the server restarts)
  - checks that reject silly values (price <= 0, absurd quantities, etc.)
"""

import time
from collections import defaultdict, deque

from sqlalchemy import select

from app.models import Drop, DropReport, PriceReport

# Worlds shown in the "Report a price" dropdown. Sample list; edit freely.
WORLDS = [
    "Scania", "Bera", "Broa", "Windia", "Khaini", "Bellocan", "Mardia",
    "Kradia", "Yellonde", "Demethos", "Galicia", "El Nido", "Zenith",
    "Arcania", "Chaos", "Nova", "Renegades",
]

# Sanity limits for submitted numbers.
MAX_PRICE = 10_000_000_000   # 10 billion mesos per unit is already absurd
MAX_QUANTITY = 10_000
MAX_KILLS = 100_000


class ReportError(Exception):
    """Raised when a report is rejected. The message is shown to the user."""


class RateLimiter:
    """Allow at most `max_hits` reports per IP in any `window_seconds` window."""

    def __init__(self, max_hits=5, window_seconds=60):
        self.max_hits = max_hits
        self.window_seconds = window_seconds
        # ip -> times of recent hits (oldest first)
        self.hits = defaultdict(deque)

    def allow(self, ip):
        """Return True (and record the hit) if this IP may submit now."""
        now = time.monotonic()
        recent = self.hits[ip]
        # Forget hits that are older than the window.
        while recent and now - recent[0] > self.window_seconds:
            recent.popleft()
        if len(recent) >= self.max_hits:
            return False
        recent.append(now)
        return True

    def reset(self):
        """Clear everything (used by tests)."""
        self.hits.clear()


# One shared limiter for the whole app.
rate_limiter = RateLimiter()


def _to_int(value, field_name):
    """Turn form text like '1200' into an int, or raise a friendly error."""
    try:
        return int(str(value).replace(",", "").strip())
    except (TypeError, ValueError):
        raise ReportError(f"{field_name} must be a whole number.")


def save_price_report(db, item_id, price, quantity, world, ip):
    """Check and save one price report. Returns the new PriceReport."""
    if not rate_limiter.allow(ip):
        raise ReportError("Too many reports from you. Please wait a minute and try again.")

    price = _to_int(price, "Price")
    quantity = _to_int(quantity if quantity not in (None, "") else 1, "Quantity")
    world = (world or "").strip()

    if price <= 0:
        raise ReportError("Price must be more than 0 mesos.")
    if price > MAX_PRICE:
        raise ReportError("That price is too high to be real.")
    if quantity < 1 or quantity > MAX_QUANTITY:
        raise ReportError(f"Quantity must be between 1 and {MAX_QUANTITY:,}.")
    if world not in WORLDS:
        raise ReportError("Please pick a world from the list.")

    report = PriceReport(item_id=item_id, price=price, quantity=quantity,
                         world=world, reporter_ip=ip, status="ok")
    db.add(report)
    db.commit()
    return report


def save_drop_report(db, monster_id, item_id, kills, drops, world, ip):
    """Check and save one drop report. Returns the new DropReport."""
    if not rate_limiter.allow(ip):
        raise ReportError("Too many reports from you. Please wait a minute and try again.")

    item_id = _to_int(item_id, "Item")
    kills = _to_int(kills, "Kills")
    drops = _to_int(drops if drops not in (None, "") else 0, "Drops")
    world = (world or "").strip()

    if kills < 1 or kills > MAX_KILLS:
        raise ReportError(f"Kills must be between 1 and {MAX_KILLS:,}.")
    if drops < 0 or drops > kills:
        raise ReportError("Drops must be between 0 and the number of kills.")
    if world and world not in WORLDS:
        raise ReportError("Please pick a world from the list.")

    # The item must be a known drop of this monster.
    known = db.scalar(select(Drop).where(Drop.monster_id == monster_id, Drop.item_id == item_id))
    if known is None:
        raise ReportError("That item isn't a known drop of this monster.")

    report = DropReport(monster_id=monster_id, item_id=item_id, kills=kills,
                        drops_seen=drops, world=world or "Unknown", reporter_ip=ip)
    db.add(report)
    db.commit()
    return report
