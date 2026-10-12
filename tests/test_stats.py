"""Tests for the pure math in app/services/stats.py (no database needed)."""

from app.services.stats import format_percent, iqr_bounds, iqr_filter, observed_rate, price_stats


# ---------- IQR outlier filter + median ----------

def test_iqr_removes_absurd_high_and_low():
    prices = [100, 102, 98, 101, 99, 100, 999_999, 1]
    kept = iqr_filter(prices)
    assert 999_999 not in kept
    assert 1 not in kept
    assert kept == [98, 99, 100, 100, 101, 102]


def test_iqr_keeps_everything_when_no_outliers():
    prices = [10, 20, 30, 40, 50]
    assert iqr_filter(prices) == [10, 20, 30, 40, 50]


def test_iqr_skipped_for_tiny_lists():
    # Fewer than 4 prices: not enough data to call anything an outlier.
    assert iqr_bounds([1, 1_000_000]) is None
    assert iqr_filter([1, 1_000_000]) == [1, 1_000_000]


def test_iqr_bounds_textbook_example():
    # Q1 = 2.75, Q3 = 6.25 (inclusive method), IQR = 3.5 -> range -2.5 .. 11.5
    assert iqr_bounds([1, 2, 3, 4, 5, 6, 7, 8]) == (-2.5, 11.5)


def test_filter_with_outside_bounds():
    # A single day's prices judged against a 30-day range.
    assert iqr_filter([90, 500], bounds=(80, 120)) == [90]


def test_price_stats_ignores_outlier():
    stats = price_stats([1000, 1100, 1200, 1300, 50_000_000])
    assert stats == {"median": 1150, "low": 1000, "high": 1300, "count": 4, "outliers_removed": 1}


def test_price_stats_odd_count_median():
    assert price_stats([5, 1, 3])["median"] == 3


def test_price_stats_empty():
    assert price_stats([]) == {"median": None, "low": None, "high": None,
                               "count": 0, "outliers_removed": 0}


# ---------- drop rates ----------

def test_observed_rate_basic():
    r = observed_rate(kills=400, drops_seen=5)
    assert r["rate_percent"] == 1.25
    assert r["low_confidence"] is False
    assert r["label"] == "1.25% (5 / 400 kills)"


def test_observed_rate_low_confidence_under_100_kills():
    r = observed_rate(kills=99, drops_seen=1)
    assert r["low_confidence"] is True
    assert "low confidence" in r["label"]


def test_observed_rate_exactly_100_kills_is_ok():
    assert observed_rate(kills=100, drops_seen=0)["low_confidence"] is False


def test_observed_rate_no_kills():
    r = observed_rate(kills=0, drops_seen=0)
    assert r["rate_percent"] is None
    assert r["label"] == "no reports yet"


def test_format_percent():
    assert format_percent(None) == "unknown"
    assert format_percent(5.0) == "5%"
    assert format_percent(0.5) == "0.5%"
    assert format_percent(0.0123) == "0.0123%"
    assert format_percent(0) == "0%"
