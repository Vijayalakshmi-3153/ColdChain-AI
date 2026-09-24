"""
Alert generation with deduplication (Phase A, Step 5).

Alerts are RULE-BASED OUTPUT raised from the shipment's real conditions plus
the ML outputs:

  temperature_excursion   any cumulative time outside the allowed range
  cumulative_exposure     excursion time above the tolerated limit
  high_ml_risk            blended risk level HIGH / CRITICAL
  anomaly_detected        autoencoder anomaly score above its threshold
  forecast_breach         LSTM predicts a future temperature breach
  sensor_battery_low      sensor battery below ALERT_LOW_BATTERY_PERCENT

Deduplication: an alert type is not raised again while an UNACKNOWLEDGED alert
of the same type for the same shipment is younger than
`ALERT_DEDUP_COOLDOWN_MINUTES` (default 30). Acknowledge an alert to allow a
new one to be raised later. This keeps one telemetry reading from producing
alerts on every poll.
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import Any

from .. import crud, schemas
from ..config import get_settings

settings = get_settings()

ALERT_TYPES = (
    "temperature_excursion",
    "cumulative_exposure",
    "high_ml_risk",
    "anomaly_detected",
    "forecast_breach",
    "sensor_battery_low",
)
def _candidate(
    alert_type: str,
    severity: str,
    message: str,
    recommended_action: str,
    evidence: dict[str, Any] | None = None,
) -> dict[str, Any]:
    return {
        "alert_type": alert_type,
        "severity": severity,
        "message": message,
        "recommended_action": recommended_action,
        "evidence": evidence or {},
    }


def _value(source, name: str):
    """Read a field from a dict or an object (assessments mix both)."""
    if source is None:
        return None
    if isinstance(source, dict):
        return source.get(name)
    return getattr(source, name, None)


def build_alert_candidates(
    *,
    assessment: dict[str, Any],
    product,
    latest_reading=None,
) -> list[dict[str, Any]]:
    """
    RULE-BASED OUTPUT: the alerts that the current assessment justifies.

    Pure function (no DB): the caller decides which of them to persist.
    """
    metrics = assessment.get("exposure") or {}
    model_result = assessment.get("model_result") or {}
    anomaly = assessment.get("anomaly") or {}
    forecast = assessment.get("forecast") or {}
    risk_level = assessment.get("risk_level")

    candidates: list[dict[str, Any]] = []

    has_telemetry = bool(metrics.get("total_readings"))
    if not has_telemetry:
        return candidates

    excursion_minutes = float(metrics.get("total_excursion_minutes") or 0.0)
    excursion_limit = float(metrics.get("excursion_limit_minutes") or 0.0)
    percent_outside = float(metrics.get("percent_readings_outside_range") or 0.0)

    if excursion_minutes > 0:
        if excursion_limit > 0 and excursion_minutes > excursion_limit:
            candidates.append(_candidate(
                "cumulative_exposure",
                "critical",
                (
                    f"Cumulative exposure of {excursion_minutes:.0f} min outside the allowed "
                    f"{getattr(product, 'minimum_temperature', '?')}-{getattr(product, 'maximum_temperature', '?')} C "
                    f"range exceeds the tolerated {excursion_limit:.0f} min."
                ),
                "Inspect the refrigeration unit and prioritise handling of this shipment.",
                {
                    "total_excursion_minutes": excursion_minutes,
                    "excursion_limit_minutes": excursion_limit,
                    "degree_minutes_outside_range": metrics.get("degree_minutes_outside_range"),
                },
            ))
        candidates.append(_candidate(
            "temperature_excursion",
            "warning",
            (
                f"Temperature excursion detected: {excursion_minutes:.0f} min outside the allowed range "
                f"({percent_outside:.1f}% of readings); peak {metrics.get('max_temperature')} C."
            ),
            "Inspect refrigeration and reduce door-open exposure.",
            {
                "total_excursion_minutes": excursion_minutes,
                "percent_readings_outside_range": percent_outside,
                "max_temperature": metrics.get("max_temperature"),
                "min_temperature": metrics.get("min_temperature"),
            },
        ))

    model_score = model_result.get("risk_score")
    if risk_level in ("HIGH", "CRITICAL"):
        candidates.append(_candidate(
            "high_ml_risk",
            "critical" if risk_level == "CRITICAL" else "warning",
            (
                f"Model risk level {risk_level} for this shipment"
                + (f" (XGBoost risk score {model_score:.2f})." if model_score is not None else ".")
            ),
            "Prioritise shipment handling and verify the load at the next check point.",
            {"risk_level": risk_level, "model_risk_score": model_score},
        ))

    if anomaly.get("status") == "anomalous":
        candidates.append(_candidate(
            "anomaly_detected",
            "warning",
            (
                f"Anomaly detected in the sensor pattern: reconstruction error {anomaly.get('score')} "
                f"above the calibrated threshold {anomaly.get('threshold')}."
            ),
            "Inspect the refrigeration unit and sensor calibration.",
            {"score": anomaly.get("score"), "threshold": anomaly.get("threshold")},
        ))

    breach = forecast.get("predicted_breach")
    if settings.alert_raise_forecast_breach and forecast.get("status") == "ok" and breach:
        candidates.append(_candidate(
            "forecast_breach",
            "warning",
            (
                f"Forecast breach in about {float(breach.get('minutes_ahead') or 0):.0f} min: predicted "
                f"{breach.get('predicted_temperature')} C ({str(breach.get('direction', '')).replace('_', ' ')})."
            ),
            "Check temperature control before the predicted breach.",
            dict(breach),
        ))

    battery = _value(latest_reading, "battery_level")
    if battery is not None and float(battery) < float(settings.alert_low_battery_percent):
        candidates.append(_candidate(
            "sensor_battery_low",
            "warning",
            f"Sensor battery at {float(battery):.1f}% (below {settings.alert_low_battery_percent:.0f}%).",
            "Replace/charge the sensor battery to keep monitoring active.",
            {"battery_level": float(battery)},
        ))

    return candidates
def sync_alerts(
    db,
    shipment_id: int,
    candidates: list[dict[str, Any]],
    *,
    cooldown_minutes: int | None = None,
    now: datetime | None = None,
) -> dict[str, Any]:
    """
    Persist the candidates that are not duplicates of a recent open alert.

    Returns {"evaluated", "created": [Alert], "suppressed": [ {...} ]}.
    """
    cooldown = float(cooldown_minutes if cooldown_minutes is not None else settings.alert_dedup_cooldown_minutes)
    moment = now or datetime.now(timezone.utc)
    since = moment - timedelta(minutes=cooldown)

    created: list = []
    suppressed: list[dict[str, Any]] = []
    seen_types: set[str] = set()

    for candidate in candidates:
        alert_type = candidate["alert_type"]
        if alert_type in seen_types:
            suppressed.append({"alert_type": alert_type, "reason": "duplicate in this evaluation"})
            continue

        existing = crud.get_open_alert_by_type(db, shipment_id, alert_type, since)
        if existing is not None:
            suppressed.append({
                "alert_type": alert_type,
                "reason": f"open alert #{existing.id} of this type raised within the last {cooldown:.0f} min",
            })
            continue

        alert = crud.create_alert(
            db,
            schemas.AlertCreate(
                shipment_id=shipment_id,
                alert_type=alert_type,
                severity=candidate["severity"],
                message=candidate["message"],
                recommended_action=candidate.get("recommended_action"),
            ),
        )
        created.append(alert)
        seen_types.add(alert_type)

    return {"evaluated": len(candidates), "created": created, "suppressed": suppressed}


def evaluate_and_sync(
    db,
    shipment_id: int,
    assessment: dict[str, Any],
    product,
    *,
    cooldown_minutes: int | None = None,
) -> dict[str, Any]:
    """
    Convenience wrapper: build the candidates for an assessment and persist the
    non-duplicates. Used by the API layer (GET /shipments/{id}/alerts,
    POST /shipments/{id}/alerts/generate, dashboard).
    """
    candidates = build_alert_candidates(
        assessment=assessment,
        product=product,
        latest_reading=assessment.get("latest_reading"),
    )
    return sync_alerts(db, shipment_id, candidates, cooldown_minutes=cooldown_minutes)


def evaluate_after_telemetry(db, shipment_id: int) -> dict[str, Any]:
    """
    Live ingest hook: assess the shipment and persist justified alerts.

    Reuses `risk.assess_shipment(..., raise_alerts=True)` which calls
    `evaluate_and_sync` (same types, same dedup). SHAP is skipped because
    alert rules do not use it. GET /shipments/{id}/risk stays read-only.
    """
    shipment = crud.get_shipment(db, shipment_id)
    if shipment is None:
        return {"evaluated": 0, "created": 0, "suppressed": 0, "suppressed_types": []}

    product = crud.get_product(db, shipment.product_id)
    from . import risk as risk_service

    assessment = risk_service.assess_shipment(
        db,
        shipment,
        product=product,
        include_shap=False,
        use_cache=True,
        raise_alerts=True,
    )
    return assessment.get("alerts") or {
        "evaluated": 0,
        "created": 0,
        "suppressed": 0,
        "suppressed_types": [],
    }
