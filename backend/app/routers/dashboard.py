"""
Dashboard API (Phase A, Step 5).
GET /dashboard/summary | /dashboard/shipments | /dashboard/map

All required PostgreSQL data is loaded before ML inference so the
database connection is not held while expensive ML models run.
"""

from datetime import datetime, timezone

from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from .. import crud
from ..config import get_settings
from ..database import get_db
from ..services import ml_inference
from ..services import risk as risk_service

router = APIRouter(prefix="/dashboard", tags=["dashboard"])

settings = get_settings()

ACTIVE_STATUSES = {"pending", "in_transit", "delayed", "late"}


def _get(source, name):
    """Read a field from either a dict or an object."""
    if isinstance(source, dict):
        return source.get(name)
    return getattr(source, name, None)


def _row_from_assessment(
    shipment,
    assessment: dict,
    active_alerts: int = 0,
) -> dict:
    """Build one dashboard row without database queries."""

    metrics = assessment.get("exposure") or {}
    latest = assessment.get("latest_reading") or {}
    position = assessment.get("position") or {}
    product = assessment.get("product")

    readings = int(
        (metrics.get("total_readings") or 0)
        or assessment.get("readings_used")
        or 0
    )

    return {
        "shipment_id": shipment.id,
        "vehicle_id": shipment.vehicle_id,
        "origin": shipment.origin,
        "destination": shipment.destination,
        "status": shipment.status,
        "product_id": shipment.product_id,
        "product_name": getattr(product, "name", None) if product else None,
        "product_category": getattr(product, "category", None) if product else None,
        "temperature": _get(latest, "temperature"),
        "humidity": _get(latest, "humidity"),
        "door_open": _get(latest, "door_open"),
        "battery_level": _get(latest, "battery_level"),
        "last_updated": _get(latest, "timestamp"),
        "readings_count": readings,
        "risk_level": assessment.get("risk_level", "UNKNOWN"),
        "risk_score": assessment.get("risk_score"),
        "model_risk_score": assessment.get("model_risk_score"),
        "exposure_status": metrics.get("status"),
        "cumulative_excursion_minutes": metrics.get(
            "total_excursion_minutes"
        ),
        "remaining_shelf_life_hours": metrics.get(
            "remaining_shelf_life_hours"
        ),
        "anomaly_status": (assessment.get("anomaly") or {}).get("status"),
        "active_alerts": active_alerts,
        "latitude": _get(position, "latitude"),
        "longitude": _get(position, "longitude"),
        "position_source": _get(position, "source"),
        "estimated_arrival_time": shipment.estimated_arrival_time,
    }


def _assess_all(db: Session, limit: int):
    """
    Load PostgreSQL data first, release the DB transaction, then
    perform ML inference.

    The original ORM telemetry rows are intentionally preserved because
    risk_service._cache_key() requires the telemetry row ID.
    """

    # ---------------------------------------------------------
    # STEP 1: Load shipments
    # ---------------------------------------------------------
    shipments = crud.get_shipments(
        db,
        skip=0,
        limit=limit,
    )

    prepared = []

    # ---------------------------------------------------------
    # STEP 2: Load everything needed from PostgreSQL.
    # ---------------------------------------------------------
    for shipment in shipments:

        product = crud.get_product(
            db,
            shipment.product_id,
        )

        try:
            telemetry_rows = crud.get_telemetry_for_shipment(
                db,
                shipment.id,
                skip=0,
                limit=int(settings.ml_max_readings_per_shipment),
            )
        except Exception:
            telemetry_rows = []

        try:
            alerts = crud.get_alerts_for_shipment(
                db,
                shipment.id,
                skip=0,
                limit=1000,
            )

            active_alerts = sum(
                1
                for alert in alerts
                if not getattr(alert, "acknowledged", False)
            )

        except Exception:
            active_alerts = 0

        prepared.append(
            {
                "shipment": shipment,
                "product": product,
                "telemetry": telemetry_rows,
                "active_alerts": active_alerts,
            }
        )

    # ---------------------------------------------------------
    # STEP 3: Release the PostgreSQL connection.
    #
    # The ML inference below can be expensive, so we do not want
    # the database connection to remain checked out during it.
    # ---------------------------------------------------------
    try:
        db.rollback()
    except Exception:
        pass

    # ---------------------------------------------------------
    # STEP 4: Run the existing risk/ML pipeline.
    # ---------------------------------------------------------
    rows = []

    for item in prepared:

        shipment = item["shipment"]
        product = item["product"]
        telemetry_rows = item["telemetry"]
        active_alerts = item["active_alerts"]

        try:
            assessment = risk_service.assess_shipment(
                db,
                shipment,
                product=product,
                readings=telemetry_rows,
                include_shap=False,
                use_cache=True,
            )

        except Exception as exc:

            assessment = {
                "risk_level": "UNKNOWN",
                "risk_score": None,
                "model_risk_score": None,
                "exposure": None,
                "anomaly": {
                    "status": "error"
                },
                "latest_reading": None,
                "position": None,
                "readings_used": 0,
                "product": product,
                "notes": [
                    f"assessment failed: {exc}"
                ],
            }

        rows.append(
            _row_from_assessment(
                shipment,
                assessment,
                active_alerts=active_alerts,
            )
        )

    return shipments, rows


@router.get("/summary")
def dashboard_summary(
    db: Session = Depends(get_db),
):
    """Summary cards computed live from PostgreSQL."""

    limit = int(settings.dashboard_max_shipments)

    shipments, rows = _assess_all(
        db,
        limit,
    )

    breakdown = {
        "LOW": 0,
        "MEDIUM": 0,
        "HIGH": 0,
        "CRITICAL": 0,
        "UNKNOWN": 0,
    }

    for row in rows:

        level = row.get(
            "risk_level",
            "UNKNOWN",
        )

        breakdown[level] = (
            breakdown.get(level, 0) + 1
        )

    active = [
        shipment
        for shipment in shipments
        if str(shipment.status).lower()
        in ACTIVE_STATUSES
    ]

    # Alert counts were loaded before ML inference.
    active_alerts = sum(
        int(row.get("active_alerts") or 0)
        for row in rows
    )

    ml = ml_inference.registry.summary()

    assessed = sum(
        1
        for row in rows
        if row.get("risk_level") != "UNKNOWN"
    )

    notes = [
        "Counts are computed live from PostgreSQL on every request.",
        "Risk blends XGBoost MODEL OUTPUT with RULE-BASED exposure severity.",
    ]

    if len(shipments) >= limit:
        notes.append(
            f"Capped at {limit} shipments (DASHBOARD_MAX_SHIPMENTS)."
        )

    return {
        "total_shipments": len(shipments),
        "active_shipments": len(active),
        "high_or_critical_risk": (
            breakdown.get("HIGH", 0)
            + breakdown.get("CRITICAL", 0)
        ),
        "active_alerts": active_alerts,
        "risk_breakdown": breakdown,
        "active_statuses": sorted(
            {
                str(shipment.status)
                for shipment in active
            }
        ),
        "shipments_assessed": assessed,
        "generated_at": datetime.now(timezone.utc),
        "ml_available": ml.get(
            "available",
            [],
        ),
        "ml_unavailable": ml.get(
            "unavailable",
            [],
        ),
        "data_sources": {
            "telemetry": "REAL data from PostgreSQL",
            "risk": "MODEL OUTPUT (SYNTHETIC/DEMO) + RULE-BASED OUTPUT",
        },
        "notes": notes,
    }


@router.get("/shipments")
def dashboard_shipments(
    limit: int = Query(
        50,
        ge=1,
        le=200,
    ),
    db: Session = Depends(get_db),
):
    """One assessed row per shipment for the dashboard table."""

    cap = min(
        int(limit),
        int(settings.dashboard_max_shipments),
    )

    _, rows = _assess_all(
        db,
        cap,
    )

    return rows


@router.get("/map")
def dashboard_map(
    db: Session = Depends(get_db),
):
    """Live map payload with assessed shipments and coordinates."""

    _, rows = _assess_all(
        db,
        int(settings.dashboard_max_shipments),
    )

    with_coords = [
        row
        for row in rows
        if row.get("latitude") is not None
    ]

    latest_ts = None

    for row in rows:

        ts = row.get("last_updated")

        if ts is not None and (
            latest_ts is None
            or ts > latest_ts
        ):
            latest_ts = ts

    notes = [
        "Positions come from latest telemetry GPS, else shipment record.",
        "Origin/destination are place names (no geocoding in Step 5).",
        f"{len(with_coords)} of {len(rows)} shipments have coordinates.",
    ]

    return {
        "generated_at": datetime.now(timezone.utc),
        "shipments": rows,
        "notes": notes,
        "last_reading_at": latest_ts,
    }