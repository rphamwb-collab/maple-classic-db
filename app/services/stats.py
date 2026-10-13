"""Pure math helpers: price medians (with an outlier filter) and drop rates.

Nothing in this file touches the database, so it is easy to test.
"""

import statistics

# Below this many kills, an observed drop rate is flagged as "low confidence".
LOW_CONFIDENCE_KILLS = 100

# We only run the outlier filter when there are at least this many prices.
# With fewer, there is not enough data to say what an "outlier" is.
MIN_PRICES_FOR_FILTER = 4


def iqr_bounds(prices):
    """Work out the "normal" price range using the IQR rule.

    Q1 = the price 25% of the way up the sorted list, Q3 = 75% of the way.
    IQR = Q3 - Q1. The normal range is Q1 - 1.5*IQR up to Q3 + 1.5*IQR.
    Returns (low_cut, high_cut), or None if there are too few prices to judge.
    """
    if len(prices) < MIN_PRICES_FOR_FILTER:
        return None
    # "inclusive" treats the list as the whole population (the usual textbook method).
    q1, _q2, q3 = statistics.quantiles(sorted(prices), n=4, method="inclusive")
    iqr = q3 - q1
    return (q1 - 1.5 * iqr, q3 + 1.5 * iqr)


def iqr_filter(prices, bounds=None):
    """Remove extreme prices. Returns a new sorted list without the outliers.

    By default the bounds come from `prices` itself. You can pass `bounds`
    (from iqr_bounds) to judge a small group, like one day's prices,
    against a bigger window, like the last 30 days.
    """
    prices = sorted(prices)
    if bounds is None:
        bounds = iqr_bounds(prices)
    if bounds is None:
        return prices
    low_cut, high_cut = bounds
    return [p for p in prices if low_cut <= p <= high_cut]


def price_stats(prices, bounds=None):
    """Summarize a list of prices: median, low, high, count after filtering.

    Returns a dict:
      {"median", "low", "high", "count", "outliers_removed"}
    median/low/high are None when there are no prices.
    `bounds` is optional; see iqr_filter.
    """
    kept = iqr_filter(prices, bounds)
    if not kept:
        return {"median": None, "low": None, "high": None, "count": 0, "outliers_removed": 0}

    return {
        # Prices are whole mesos, so round the median to a whole number.
        "median": round(statistics.median(kept)),
        "low": kept[0],
        "high": kept[-1],
        "count": len(kept),
        "outliers_removed": len(prices) - len(kept),
    }


def observed_rate(kills, drops_seen):
    """Turn total kills and total drops into an observed drop rate.

    Returns a dict:
      {"kills", "drops_seen", "rate_percent", "low_confidence", "label"}
    rate_percent is a percentage (1.25 means 1.25%), or None if there are no kills.
    """
    kills = kills or 0
    drops_seen = drops_seen or 0

    if kills <= 0:
        return {
            "kills": 0,
            "drops_seen": drops_seen,
            "rate_percent": None,
            "low_confidence": True,
            "label": "no reports yet",
        }

    rate_percent = drops_seen / kills * 100
    low_confidence = kills < LOW_CONFIDENCE_KILLS
    label = f"{format_percent(rate_percent)} ({drops_seen} / {kills} kills)"
    if low_confidence:
        label += ", low confidence"

    return {
        "kills": kills,
        "drops_seen": drops_seen,
        "rate_percent": rate_percent,
        "low_confidence": low_confidence,
        "label": label,
    }


def format_percent(percent):
    """Format a percentage nicely: 12.5 -> '12.5%', 0.0123 -> '0.0123%'."""
    if percent is None:
        return "unknown"
    if percent == 0:
        return "0%"
    if percent >= 1:
        text = f"{percent:.2f}"
    else:
        # Small rates need more digits so they don't show as 0.00%.
        text = f"{percent:.4f}"
    # Trim trailing zeros: "5.00" -> "5", "0.5000" -> "0.5"
    text = text.rstrip("0").rstrip(".")
    return f"{text}%"


def is_player_confirmed(confidence, drops_seen):
    """True when an older-version ("estimated") drop has been seen by players.

    It means a player actually saw this item drop in Classic, so the
    "may not drop in Classic" warning is no longer a worry.
    """
    return confidence == "estimated" and (drops_seen or 0) > 0
