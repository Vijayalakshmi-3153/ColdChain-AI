"""
Cumulative temperature-exposure engine.

Concept: spoilage risk builds up OVER TIME, not from a single reading.
Every telemetry interval contributes "degree-minutes outside the allowed
range" and ages the product thermally via the Q10 model.

Inputs (product limits):
  - minimum_temperature / maximum_temperature   allowed range (deg C)
  - shelf_life_hours                           initial shelf life
  - q10                                        reaction-rate multiplier per +10 deg C
  - maximum_allowed_excursion_minutes           tolerated time outside the range

Algorithm:
  1. Sort readings by timestamp.
  2. For each pair of consecutive readings, the gap (minutes, capped at
     MAX_GAP_MINUTES) is attributed to the LATER reading.
  3. If that reading is outside [min, max]:
        total_excursion_minutes      += gap
        degree_minutes_outside_range += |deviation from nearest bound| * gap
  4. Thermal ageing (Q10): with Tref = centre of the allowed range,
        equivalent_age += gap_hours * q10 ** ((T - Tref) / 10)
     At Tref the factor is 1.0 (normal ageing); above Tref the product
     ages faster, below slower.
  5. remaining_shelf_life = max(shelf_life_hours - equivalent_age, 0)
  6. status: critical > excursion limit, warning > any excursion, else normal.

The functions are pure (no DB access) so they are easy to unit-test.
"""

from datetime import datetime, timezone

# A single gap longer than this is capped so sparse data cannot
# inflate the exposure numbers unrealistically.
MAX_GAP_MINUTES = 60.0


def _as_naive_utc(dt: datetime) -> datetime:
    """Normalize tz-aware datetimes to naive UTC so they can be compared."""
    if dt.tzinfo is not None:
        return dt.astimezone(timezone.utc).replace(tzinfo=None)
    return dt


def compute_exposure(product, readings) -> dict:
    """
    Compute cumulative exposure metrics.

    Args:
        product: object with minimum_temperature, maximum_temperature,
                 shelf_life_hours, q10, maximum_allowed_excursion_minutes
        readings: iterable of objects with `.timestamp` (datetime) and
                  `.temperature` (float), in any order

    Returns:
        dict of exposure metrics (matches schemas.ExposureMetrics)
    """
    min_t = float(product.minimum_temperature)
    max_t = float(product.maximum_temperature)
    shelf_life = float(product.shelf_life_hours)
    q10 = float(product.q10)
    excursion_limit = float(product.maximum_allowed_excursion_minutes)
    t_ref = (min_t + max_t) / 2.0  # reference (centre of allowed range)

    ordered = sorted(readings, key=lambda r: _as_naive_utc(r.timestamp))

    total_readings = len(ordered)
    if total_readings == 0:
        return {
            "total_readings": 0,
            "excursion_readings": 0,
            "percent_readings_outside_range": 0.0,
            "monitored_minutes": 0.0,
            "total_excursion_minutes": 0.0,
            "degree_minutes_outside_range": 0.0,
            "max_temperature": None,
            "min_temperature": None,
            "reference_temperature": t_ref,
            "q10": q10,
            "equivalent_age_hours": 0.0,
            "remaining_shelf_life_hours": shelf_life,
            "excursion_limit_minutes": excursion_limit,
            "status": "no_data",
        }

    temperatures = [float(r.temperature) for r in ordered]
    excursion_readings = sum(1 for t in temperatures if t < min_t or t > max_t)

    monitored_minutes = 0.0
    excursion_minutes = 0.0
    degree_minutes = 0.0
    equivalent_age_hours = 0.0

    for prev, curr in zip(ordered, ordered[1:]):
        gap_minutes = (_as_naive_utc(curr.timestamp) - _as_naive_utc(prev.timestamp)).total_seconds() / 60.0
        gap_minutes = max(0.0, min(gap_minutes, MAX_GAP_MINUTES))
        temp = float(curr.temperature)

        monitored_minutes += gap_minutes

        # --- cumulative excursion (the core concept) ---
        if temp > max_t:
            excursion_minutes += gap_minutes
            degree_minutes += (temp - max_t) * gap_minutes
        elif temp < min_t:
            excursion_minutes += gap_minutes
            degree_minutes += (min_t - temp) * gap_minutes

        # --- Q10 thermal ageing over this interval ---
        rate = q10 ** ((temp - t_ref) / 10.0)
        equivalent_age_hours += (gap_minutes / 60.0) * rate

    # Include the first reading itself in the percentage stats only.
    remaining_shelf_life = max(shelf_life - equivalent_age_hours, 0.0)

    if excursion_minutes > excursion_limit:
        status = "critical"
    elif excursion_minutes > 0 or excursion_readings > 0:
        status = "warning"
    else:
        status = "normal"

    return {
        "total_readings": total_readings,
        "excursion_readings": excursion_readings,
        "percent_readings_outside_range": round(
            100.0 * excursion_readings / total_readings, 2
        ),
        "monitored_minutes": round(monitored_minutes, 2),
        "total_excursion_minutes": round(excursion_minutes, 2),
        "degree_minutes_outside_range": round(degree_minutes, 2),
        "max_temperature": max(temperatures),
        "min_temperature": min(temperatures),
        "reference_temperature": t_ref,
        "q10": q10,
        "equivalent_age_hours": round(equivalent_age_hours, 4),
        "remaining_shelf_life_hours": round(remaining_shelf_life, 4),
        "excursion_limit_minutes": excursion_limit,
        "status": status,
    }