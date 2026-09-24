"""
Unit tests for the cumulative temperature-exposure engine.

Covers: normal readings, above-maximum, below-minimum, consecutive
excursions, and the cumulative (Q10 / degree-minutes) calculations.
"""

from datetime import datetime, timedelta, timezone
from types import SimpleNamespace

from app.services.exposure import compute_exposure

BASE_TIME = datetime(2026, 1, 1, 12, 0, 0, tzinfo=timezone.utc)


def make_product(**overrides):
    """A dairy-like product: allowed range 2-6 degC, 48 h shelf life."""
    data = {
        "minimum_temperature": 2.0,
        "maximum_temperature": 6.0,
        "shelf_life_hours": 48.0,
        "q10": 2.0,
        "maximum_allowed_excursion_minutes": 30,
    }
    data.update(overrides)
    return SimpleNamespace(**data)


def reading(minute_offset: float, temperature: float) -> SimpleNamespace:
    return SimpleNamespace(
        timestamp=BASE_TIME + timedelta(minutes=minute_offset),
        temperature=temperature,
    )


# ---------------------------------------------------------------------------
# 1. Normal (in-range) temperature readings
# ---------------------------------------------------------------------------
def test_normal_readings_produce_no_excursion():
    product = make_product()
    readings = [reading(0, 4.0), reading(10, 4.5), reading(20, 5.0)]

    metrics = compute_exposure(product, readings)

    assert metrics["total_readings"] == 3
    assert metrics["excursion_readings"] == 0
    assert metrics["total_excursion_minutes"] == 0.0
    assert metrics["degree_minutes_outside_range"] == 0.0
    assert metrics["percent_readings_outside_range"] == 0.0
    assert metrics["status"] == "normal"
    assert metrics["max_temperature"] == 5.0
    assert metrics["min_temperature"] == 4.0
    # 20 monitored minutes at Q10 rate ~1 -> ~0.33 h of ageing
    assert 0 < metrics["equivalent_age_hours"] < 1
    assert metrics["remaining_shelf_life_hours"] < 48.0


# ---------------------------------------------------------------------------
# 2. Temperatures above the maximum
# ---------------------------------------------------------------------------
def test_above_maximum_accumulates_degree_minutes():
    product = make_product()
    # t=10 -> 8 degC (2 above max, 10 min), t=20 -> 9 degC (3 above max, 10 min)
    readings = [reading(0, 4.0), reading(10, 8.0), reading(20, 9.0)]

    metrics = compute_exposure(product, readings)

    assert metrics["excursion_readings"] == 2
    assert metrics["total_excursion_minutes"] == 20.0
    assert metrics["degree_minutes_outside_range"] == 2 * 10 + 3 * 10  # 50
    assert metrics["max_temperature"] == 9.0
    # 20 min <= 30 min allowed, so not critical yet
    assert metrics["status"] == "warning"


# ---------------------------------------------------------------------------
# 3. Temperatures below the minimum
# ---------------------------------------------------------------------------
def test_below_minimum_accumulates_degree_minutes():
    product = make_product()
    # t=10 -> 0 degC (2 below min, 10 min), t=20 -> 1 degC (1 below min, 10 min)
    readings = [reading(0, 4.0), reading(10, 0.0), reading(20, 1.0)]

    metrics = compute_exposure(product, readings)

    assert metrics["excursion_readings"] == 2
    assert metrics["total_excursion_minutes"] == 20.0
    assert metrics["degree_minutes_outside_range"] == 2 * 10 + 1 * 10  # 30
    assert metrics["min_temperature"] == 0.0
    assert metrics["status"] == "warning"


# ---------------------------------------------------------------------------
# 4. Multiple consecutive excursion readings (cumulative over time)
# ---------------------------------------------------------------------------
def test_consecutive_excursions_accumulate_minutes():
    product = make_product(maximum_allowed_excursion_minutes=15)
    # Three consecutive out-of-range readings, 10 minutes apart.
    readings = [reading(0, 4.0), reading(10, 7.0), reading(20, 7.0), reading(30, 7.0)]

    metrics = compute_exposure(product, readings)

    # The first out-of-range interval starts at reading #2: 10+10+10 = 30 min.
    assert metrics["total_excursion_minutes"] == 30.0
    assert metrics["degree_minutes_outside_range"] == (7 - 6) * 30
    assert metrics["percent_readings_outside_range"] == 75.0  # 3 of 4 readings
    # 30 min > 15 min allowed -> critical
    assert metrics["status"] == "critical"


def test_excursion_limit_boundary_is_not_critical():
    product = make_product(maximum_allowed_excursion_minutes=30)
    readings = [reading(0, 4.0), reading(10, 7.0), reading(20, 7.0), reading(30, 7.0)]

    metrics = compute_exposure(product, readings)

    # Exactly at the limit (30 > 30 is False) -> warning, not critical.
    assert metrics["total_excursion_minutes"] == 30.0
    assert metrics["status"] == "warning"


# ---------------------------------------------------------------------------
# 5. Cumulative exposure / equivalent age / remaining shelf life
# ---------------------------------------------------------------------------
def test_cool_history_ages_slower_than_hot_history():
    product = make_product(q10=2.0)
    # Same duration (60 monitored minutes) at the centre of the range (4 degC):
    cold = [reading(0, 4.0), reading(20, 4.0), reading(40, 4.0), reading(60, 4.0)]
    cold_metrics = compute_exposure(product, cold)

    # ... versus a much hotter history (10 degC):
    hot = [reading(0, 10.0), reading(20, 10.0), reading(40, 10.0), reading(60, 10.0)]
    hot_metrics = compute_exposure(product, hot)

    # At Tref (4 degC) the Q10 factor is 1.0 -> exactly 1 hour of ageing.
    assert cold_metrics["equivalent_age_hours"] == 1.0
    # Hot history ages faster (Q10=2, +6 degC -> factor ~1.52).
    assert hot_metrics["equivalent_age_hours"] > cold_metrics["equivalent_age_hours"]
    # Remaining shelf life shrinks accordingly.
    assert (
        hot_metrics["remaining_shelf_life_hours"]
        < cold_metrics["remaining_shelf_life_hours"]
    )
    # Cumulative, never negative.
    assert hot_metrics["remaining_shelf_life_hours"] >= 0


def test_remaining_shelf_life_never_negative():
    product = make_product(shelf_life_hours=1.0, q10=4.0)
    readings = [reading(0, 20.0), reading(60, 20.0), reading(120, 20.0)]

    metrics = compute_exposure(product, readings)

    # Aged far beyond shelf life -> clamped to 0.
    assert metrics["equivalent_age_hours"] > 1.0
    assert metrics["remaining_shelf_life_hours"] == 0.0
    assert metrics["status"] == "critical"


def test_empty_history_reports_no_data():
    metrics = compute_exposure(make_product(), [])

    assert metrics["total_readings"] == 0
    assert metrics["status"] == "no_data"
    assert metrics["remaining_shelf_life_hours"] == 48.0
    assert metrics["max_temperature"] is None