"""
Shipment risk assessment (Phase A, Step 5).

This module combines two clearly separated kinds of output:

  MODEL OUTPUT (from ml_inference.py)
    * XGBoost spoilage-risk score          -> "model_risk_score"
    * LSTM forecast (+ predicted breach)
    * autoencoder anomaly score
    * SHAP top contributing factors

  RULE-BASED OUTPUT (transparent, documented formulas)
    * cumulative exposure severity from the Step 3 exposure engine
    * percent of readings outside the allowed range
    * remaining shelf-life fraction
    -> "rule_based_score"

The two are blended into `risk_score` / `risk_level`. Thresholds are
APPLICATION/DEMO thresholds, configurable through environment variables
(RISK_LOW_MAX, RISK_MEDIUM_MAX, RISK_HIGH_MAX, RISK_MODEL_WEIGHT,
RISK_RULE_WEIGHT). They are NOT medical or regulatory limits, and the score is
NOT a calibrated real-world probability - it is reported as a *risk score*
(`risk_percent` is only that score scaled to 0-100 for display).
"""

from __future__ import annotations

import threading
import time
from datetime import datetime, timezone
from typing import Any, Sequence

from ..config import get_settings
from . import ml_inference
from .exposure import compute_exposure
from .recommendations import build_recommendations

settings = get_settings()

RISK_LEVELS = ("LOW", "MEDIUM", "HIGH", "CRITICAL")

DISCLAIMER = (
    "Risk levels and scores are application/demo outputs from a model trained on "
    "SYNTHETIC/DEMO data plus rule-based formulas; they are not calibrated "
    "probabilities and not medical, regulatory or legal limits. Use them as "
    "decision support only."
)

# Assessment cache: polling the dashboard/risk endpoint must not re-run
# inference for every request, but it must also never serve data that predates
# the newest telemetry (the cache key includes the last reading id).
_CACHE: dict[tuple, tuple[float, dict]] = {}
_CACHE_LOCK = threading.Lock()


def clear_cache() -> None:
    """Drop every cached assessment (used by tests)."""
    with _CACHE_LOCK:
        _CACHE.clear()
# ---------------------------------------------------------------------------
# RULE-BASED OUTPUT: classification thresholds and exposure severity
# ---------------------------------------------------------------------------
def risk_thresholds() -> dict[str, float]:
    """Configurable 0..1 score bands (application/demo thresholds)."""
    return {
        "low_max": float(settings.risk_low_max),
        "medium_max": float(settings.risk_medium_max),
        "high_max": float(settings.risk_high_max),
        "model_weight": float(settings.risk_model_weight),
        "rule_weight": float(settings.risk_rule_weight),
        "model_decision_threshold": float(settings.risk_model_decision_threshold),
    }


def classify_score(score: float | None, thresholds: dict[str, float] | None = None) -> str:
    """
    Map a 0..1 score to LOW / MEDIUM / HIGH / CRITICAL.

    Bands (defaults, configurable):
      LOW      score <  0.25
      MEDIUM   score <  0.50
      HIGH     score <  0.75
      CRITICAL score >= 0.75
    A missing score returns "UNKNOWN" (never a made-up level).
    """
    if score is None:
        return "UNKNOWN"
    th = thresholds or risk_thresholds()
    value = float(score)
    if value < th["low_max"]:
        return "LOW"
    if value < th["medium_max"]:
        return "MEDIUM"
    if value < th["high_max"]:
        return "HIGH"
    return "CRITICAL"


def rule_based_score(metrics: dict[str, Any]) -> tuple[float | None, dict[str, Any]]:
    """
    RULE-BASED OUTPUT: 0..1 severity derived from the exposure engine.

        excursion_term = min(excursion_minutes / excursion_limit, 2) / 2
        outside_term   = percent_readings_outside_range / 100
        shelf_term     = 1 - remaining_shelf_life / shelf_life_hours
        score          = 0.40*excursion_term + 0.30*outside_term + 0.30*shelf_term

    Returns (score, components). `None` when the shipment has no telemetry
    (there is nothing to score - the API reports that as UNKNOWN rather than
    inventing a value).
    """
    if not metrics or metrics.get("status") == "no_data" or not metrics.get("total_readings"):
        return None, {"available": False, "detail": "no telemetry readings for this shipment"}

    limit = max(float(metrics.get("excursion_limit_minutes") or 0.0), 1.0)
    excursion_minutes = float(metrics.get("total_excursion_minutes") or 0.0)
    percent_outside = float(metrics.get("percent_readings_outside_range") or 0.0)
    remaining = float(metrics.get("remaining_shelf_life_hours") or 0.0)

    excursion_term = min(excursion_minutes / limit, 2.0) / 2.0
    outside_term = min(max(percent_outside / 100.0, 0.0), 1.0)
    shelf_total = max(remaining + float(metrics.get("equivalent_age_hours") or 0.0), 1e-9)
    shelf_term = min(max(1.0 - remaining / shelf_total, 0.0), 1.0)

    score = 0.40 * excursion_term + 0.30 * outside_term + 0.30 * shelf_term
    return round(score, 6), {
        "available": True,
        "weights": {"excursion": 0.40, "outside_range": 0.30, "shelf_life": 0.30},
        "excursion_minutes": round(excursion_minutes, 2),
        "excursion_limit_minutes": round(limit, 2),
        "excursion_term": round(excursion_term, 4),
        "percent_readings_outside_range": round(percent_outside, 2),
        "outside_term": round(outside_term, 4),
        "shelf_life_used_fraction": round(shelf_term, 4),
    }


def combine_scores(
    model_risk_score: float | None, rule_score: float | None, thresholds: dict[str, float] | None = None
) -> tuple[float | None, str, dict[str, Any]]:
    """
    Blend MODEL OUTPUT with RULE-BASED OUTPUT.

    `score = w_model*model + w_rule*rule`, re-normalized over whichever
    component is available. If neither is available the result is (None,
    "unknown", ...) so callers can report UNKNOWN instead of a fake number.
    """
    th = thresholds or risk_thresholds()
    components: dict[str, Any] = {
        "model_risk_score": model_risk_score,
        "rule_based_score": rule_score,
        "configured_weights": {"model": th["model_weight"], "rule": th["rule_weight"]},
    }
    available = []
    if model_risk_score is not None:
        available.append(("model", float(model_risk_score), th["model_weight"]))
    if rule_score is not None:
        available.append(("rule", float(rule_score), th["rule_weight"]))
    if not available:
        return None, "unknown", components

    total_weight = sum(w for _, _, w in available) or 1.0
    score = sum(value * weight for _, value, weight in available) / total_weight
    basis = "+".join(name for name, _, _ in available)
    components["effective_weights"] = {name: round(weight / total_weight, 4) for name, _, weight in available}
    return round(score, 6), basis, components
# ---------------------------------------------------------------------------
# Assessment assembly (MODEL OUTPUT + RULE-BASED OUTPUT + REAL telemetry)
# ---------------------------------------------------------------------------
def _risk_reasons(
    *,
    metrics: dict[str, Any],
    model_result: dict[str, Any],
    rule_components: dict[str, Any],
    anomaly: dict[str, Any],
    forecast: dict[str, Any],
    level: str,
) -> list[str]:
    """Human-readable explanation of the current risk level (no hidden maths)."""
    reasons: list[str] = []

    if not metrics or metrics.get("status") == "no_data":
        reasons.append("No telemetry is available for this shipment yet, so no risk can be assessed.")
    else:
        if metrics["total_excursion_minutes"] > 0:
            reasons.append(
                f"{metrics['total_excursion_minutes']:.0f} min of cumulative temperature excursion "
                f"(allowed {metrics['excursion_limit_minutes']:.0f} min); "
                f"{metrics['percent_readings_outside_range']:.1f}% of readings were outside "
                f"[{metrics['reference_temperature']:.1f} C reference range]."
            )
        reasons.append(
            f"Remaining shelf life {metrics['remaining_shelf_life_hours']:.1f} h after "
            f"{metrics['equivalent_age_hours']:.1f} h of Q10-equivalent ageing."
        )

    if model_result.get("status") == "ok":
        reasons.append(
            f"XGBoost Model Output: risk score {model_result['risk_score']:.2f} "
            f"(decision threshold {model_result['decision_threshold']:.2f}"
            f"{', above threshold' if model_result.get('flag') else ', below threshold'})."
        )
    else:
        reasons.append(
            "XGBoost Model Output unavailable: "
            f"{model_result.get('detail') or 'artifact not loaded'}."
        )

    if rule_components.get("available"):
        reasons.append(
            "Rule-based exposure severity "
            f"{rule_components['excursion_term']:.2f} (excursion), "
            f"{rule_components['outside_term']:.2f} (outside-range share), "
            f"{rule_components['shelf_life_used_fraction']:.2f} (shelf life used)."
        )

    if anomaly.get("status") in ("anomalous", "elevated"):
        reasons.append(
            f"Autoencoder anomaly status '{anomaly['status']}' "
            f"(score {anomaly.get('score')} vs threshold {anomaly.get('threshold')})."
        )
    if forecast.get("status") == "ok" and forecast.get("predicted_breach"):
        breach = forecast["predicted_breach"]
        reasons.append(
            f"LSTM forecast predicts {breach['direction'].replace('_', ' ')} in "
            f"~{breach['minutes_ahead']:.0f} min at {breach['predicted_temperature']:.2f} C."
        )

    reasons.append(f"Final risk level {level} = blend of the available model and rule components.")
    return reasons


def _data_notes(metrics: dict[str, Any], readings_used: int, feature_quality: dict[str, Any]) -> list[str]:
    """Explicit limitations of the current assessment (documented, not hidden)."""
    notes: list[str] = [
        "TELEMETRY is real data from PostgreSQL; MODEL OUTPUT comes from models trained on "
        "SYNTHETIC/DEMO data (see ml/README.md); RULE-BASED OUTPUT follows the documented formulas.",
    ]
    if feature_quality.get("imputed_features"):
        notes.append(
            "Model input features imputed (not available in PostgreSQL): "
            + ", ".join(feature_quality["imputed_features"])
        )
    notes.extend(feature_quality.get("notes") or [])
    if readings_used:
        notes.append(f"Features were computed from the latest {readings_used} telemetry readings of this shipment.")
    return notes
def _cache_key(shipment, product, readings, include_shap: bool) -> tuple:
    last_id = readings[0].id if readings else None
    return (
        shipment.id,
        len(readings),
        last_id,
        include_shap,
        product.id,
        float(product.minimum_temperature),
        float(product.maximum_temperature),
        float(product.shelf_life_hours),
        float(product.maximum_allowed_excursion_minutes),
        shipment.status,
        getattr(shipment, "packaging_image_path", None),
    )


def _from_cache(key: tuple, ttl: float) -> dict | None:
    with _CACHE_LOCK:
        hit = _CACHE.get(key)
    if hit is None:
        return None
    stored_at, payload = hit
    if ttl > 0 and (time.monotonic() - stored_at) > ttl:
        with _CACHE_LOCK:
            _CACHE.pop(key, None)
        return None
    return payload


def _to_cache(key: tuple, payload: dict) -> None:
    with _CACHE_LOCK:
        _CACHE[key] = (time.monotonic(), payload)


def assess_shipment(
    db,
    shipment,
    product=None,
    readings: Sequence | None = None,
    *,
    include_shap: bool = True,
    use_cache: bool = True,
    raise_alerts: bool = False,
) -> dict[str, Any]:
    """
    Build the complete risk assessment for one shipment.

    Reads REAL telemetry from PostgreSQL, prepares features with the Step 4
    logic, runs the cached ML models, then combines the outputs with the
    rule-based layer. Never mutates the shipment record.

    `raise_alerts=True` additionally persists the alerts justified by this
    assessment (deduplicated by type + cooldown, see services/alerts.py); the
    risk endpoint keeps the read path side-effect free by leaving it False.

    Caching: results are cached for `ML_CACHE_TTL_SECONDS`, keyed by the
    shipment, its newest reading id / reading count, the product limits and the
    shipment status - so new telemetry invalidates the entry.
    """
    from .. import crud  # local import: avoids a circular import at module load

    if product is None:
        product = crud.get_product(db, shipment.product_id)
    if product is None:
        return {
            "shipment_id": shipment.id,
            "shipment": shipment,
            "product": None,
            "assessed_at": datetime.now(timezone.utc),
            "risk_level": "UNKNOWN",
            "risk_score": None,
            "risk_percent": None,
            "risk_level_basis": "unknown",
            "risk_reasons": ["The shipment has no product record, so no limits are known."],
            "model_risk_score": None,
            "model_result": {"status": "unavailable", "detail": "no product record"},
            "rule_based_score": None,
            "rule_components": {"available": False, "detail": "no product record"},
            "score_components": {},
            "thresholds": risk_thresholds(),
            "exposure": None,
            "forecast": {"status": "unavailable", "detail": "no product record"},
            "anomaly": {"status": "unavailable", "detail": "no product record"},
            "packaging": _packaging_payload(shipment),
            "shap": {"status": "unavailable", "top_factors": None, "base_value": None,
                     "detail": "no product record"},
            "shap_top_factors": None,
            "recommendations": [],
            "latest_reading": None,
            "position": None,
            "readings_used": 0,
            "model_statuses": [st.as_dict() for st in ml_inference.registry.status().values()],
            "global_shap_importance": None,
            "data_quality": {"imputed_features": [], "notes": ["product record missing"],
                             "readings_used": 0},
            "notes": ["The shipment has no product record; no assessment was produced."],
            "alerts": {"evaluated": 0, "created": 0, "suppressed": 0},
            "disclaimer": DISCLAIMER,
        }

    if readings is None:
        readings = crud.get_telemetry_for_shipment(
            db, shipment.id, skip=0, limit=int(settings.ml_max_readings_per_shipment)
        )
    readings = list(readings)

    cache_key = _cache_key(shipment, product, readings, include_shap)
    payload = _from_cache(cache_key, float(settings.ml_cache_ttl_seconds)) if use_cache else None
    if payload is None:
        payload = _build_assessment(shipment, product, readings, include_shap)
        if use_cache:
            _to_cache(cache_key, payload)

    if raise_alerts:
        payload["alerts"] = _raise_alerts(db, shipment, product, payload)
    return payload


def _raise_alerts(db, shipment, product, payload: dict[str, Any]) -> dict[str, Any]:
    """Persist the alerts justified by `payload` (deduplicated)."""
    from . import alerts as alert_service

    result = alert_service.evaluate_and_sync(db, shipment.id, payload, product)
    return {
        "evaluated": result["evaluated"],
        "created": len(result["created"]),
        "suppressed": len(result["suppressed"]),
        "suppressed_types": [s["alert_type"] for s in result["suppressed"]],
    }


def _build_assessment(shipment, product, readings: Sequence, include_shap: bool) -> dict[str, Any]:
    """Compute one assessment (no caching, no DB writes)."""

    # --- REAL telemetry -> features (Step 4 logic) --------------------------
    reading_objects = ml_inference.reading_objects(readings)
    metrics = compute_exposure(product, reading_objects)

    if reading_objects:
        features, feature_quality = ml_inference.latest_feature_row(reading_objects, product)
    else:
        features, feature_quality = {}, {
            "imputed_features": [],
            "notes": ["no telemetry available for this shipment"],
            "readings_used": 0,
            "first_reading_at": None,
            "last_reading_at": None,
        }

    # --- MODEL OUTPUT -------------------------------------------------------
    if features:
        model_result = ml_inference.predict_spoilage_risk(features)
        shap_result = ml_inference.explain_prediction(features) if include_shap else {
            "status": "disabled", "top_factors": None, "base_value": None,
            "detail": "SHAP skipped for this request (include_shap=false)",
        }
    else:
        model_result = {"status": "no_data", "model": "xgboost_spoilage", "risk_score": None,
                        "detail": "no telemetry features available"}
        shap_result = {"status": "no_data", "top_factors": None, "base_value": None,
                       "detail": "no telemetry features available"}

    forecast = ml_inference.forecast_series(reading_objects, product)
    anomaly = ml_inference.detect_anomaly(reading_objects, product)

    # --- RULE-BASED risk ----------------------------------------------------
    thresholds = risk_thresholds()
    rule_score, rule_components = rule_based_score(metrics)
    model_score = model_result.get("risk_score")
    overall_score, basis, score_components = combine_scores(model_score, rule_score, thresholds)
    level = classify_score(overall_score, thresholds)

    latest = reading_objects[-1] if reading_objects else None
    position = _position(reading_objects, shipment)

    recommendations = build_recommendations(
        shipment=shipment,
        product=product,
        metrics=metrics,
        risk_level=level,
        model_result=model_result,
        anomaly=anomaly,
        forecast=forecast,
        latest_reading=latest,
        readings=reading_objects,
    )

    payload = {
        "shipment_id": shipment.id,
        "shipment": shipment,
        "product": product,
        "assessed_at": datetime.now(timezone.utc),
        "risk_level": level,
        "risk_score": overall_score,
        "risk_percent": round(overall_score * 100.0, 2) if overall_score is not None else None,
        "risk_level_basis": basis,
        "risk_reasons": _risk_reasons(
            metrics=metrics,
            model_result=model_result,
            rule_components=rule_components,
            anomaly=anomaly,
            forecast=forecast,
            level=level,
        ),
        "model_risk_score": model_score,
        "model_result": model_result,
        "rule_based_score": rule_score,
        "rule_components": rule_components,
        "score_components": score_components,
        "thresholds": thresholds,
        "exposure": metrics,
        "forecast": forecast,
        "anomaly": anomaly,
        "packaging": _packaging_payload(shipment),
        "shap": shap_result,
        "shap_top_factors": shap_result.get("top_factors"),
        "recommendations": recommendations,
        "latest_reading": _latest_reading_dict(latest),
        "position": position,
        "readings_used": len(reading_objects),
        "model_statuses": [st.as_dict() for st in ml_inference.registry.status().values()],
        "global_shap_importance": ml_inference.global_importance(10),
        "data_quality": feature_quality,
        "notes": _data_notes(metrics, len(reading_objects), feature_quality),
        "alerts": {"evaluated": 0, "created": 0, "suppressed": 0},
        "disclaimer": DISCLAIMER,
    }
    return payload


def to_api_payload(assessment: dict[str, Any]) -> dict[str, Any]:
    """
    Map an internal assessment dict to the `RiskAssessmentRead` API shape.

    The internal dict also carries helper objects (e.g. the ORM shipment and
    the raw model result) which are not part of the public response; keeping
    this mapping explicit means the API contract never leaks internals.
    """
    metrics = assessment.get("exposure") or {}
    model_result = assessment.get("model_result") or {}
    shap = assessment.get("shap") or {}
    return {
        "shipment_id": assessment["shipment_id"],
        "shipment": assessment.get("shipment"),
        "product": assessment.get("product"),
        "assessed_at": assessment["assessed_at"],
        "risk_level": assessment.get("risk_level", "UNKNOWN"),
        "risk_score": assessment.get("risk_score"),
        "risk_percent": assessment.get("risk_percent"),
        "risk_level_basis": assessment.get("risk_level_basis", "unknown"),
        "risk_reasons": assessment.get("risk_reasons") or [],
        "model_risk_score": assessment.get("model_risk_score"),
        "model_decision_threshold": model_result.get("decision_threshold"),
        "model_flag": model_result.get("flag"),
        "rule_based_score": assessment.get("rule_based_score"),
        "score_components": assessment.get("score_components") or {},
        "thresholds": assessment.get("thresholds") or {},
        "exposure": metrics or None,
        "remaining_shelf_life_hours": metrics.get("remaining_shelf_life_hours") if metrics else None,
        "lstm_forecast": assessment.get("forecast"),
        "anomaly": assessment.get("anomaly"),
        "packaging": assessment.get("packaging"),
        "shap_top_factors": shap.get("top_factors"),
        "shap_status": shap.get("status"),
        "global_shap_importance": assessment.get("global_shap_importance"),
        "recommendations": assessment.get("recommendations") or [],
        "latest_reading": assessment.get("latest_reading"),
        "position": assessment.get("position"),
        "readings_used": assessment.get("readings_used") or 0,
        "model_status": assessment.get("model_statuses") or [],
        "data_quality": assessment.get("data_quality"),
        "notes": assessment.get("notes") or [],
        "disclaimer": assessment.get("disclaimer", DISCLAIMER),
    }


def _packaging_payload(shipment) -> dict[str, Any]:
    """Use the cached CNN result when an image was uploaded; otherwise no_data."""
    stored = getattr(shipment, "packaging_result", None)
    if isinstance(stored, dict) and stored.get("status"):
        return stored
    return ml_inference.packaging_no_data()


def _latest_reading_dict(reading) -> dict[str, Any] | None:
    if reading is None:
        return None
    return {
        "timestamp": reading.timestamp,
        "temperature": reading.temperature,
        "humidity": None if not _finite(reading.humidity) else reading.humidity,
        "latitude": reading.latitude,
        "longitude": reading.longitude,
        "battery_level": reading.battery_level,
        "door_open": reading.door_open,
    }


def _finite(value) -> bool:
    try:
        return value is not None and value == value and abs(float(value)) != float("inf")
    except (TypeError, ValueError):
        return False


def _position(readings: Sequence, shipment) -> dict[str, Any] | None:
    """Most recent GPS position: latest reading with coordinates, else shipment."""
    for reading in reversed(readings):
        if reading.latitude is not None and reading.longitude is not None:
            return {
                "latitude": float(reading.latitude),
                "longitude": float(reading.longitude),
                "timestamp": reading.timestamp,
                "source": "telemetry",
            }
    if shipment.latitude is not None and shipment.longitude is not None:
        return {
            "latitude": float(shipment.latitude),
            "longitude": float(shipment.longitude),
            "timestamp": None,
            "source": "shipment_record",
        }
    return None
