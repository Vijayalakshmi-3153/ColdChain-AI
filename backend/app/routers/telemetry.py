"""
Telemetry API routes: ingestion of IoT sensor readings.
"""

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.orm import Session

from .. import crud, schemas
from ..database import get_db

router = APIRouter(prefix="/telemetry", tags=["telemetry"])


@router.post("", response_model=schemas.TelemetryRead, status_code=status.HTTP_201_CREATED)
def ingest_telemetry(telemetry: schemas.TelemetryCreate, db: Session = Depends(get_db)):
    """
    Ingest a single sensor reading.

    This is the entry point the IoT simulator / MQTT bridge will call.
    """
    if crud.get_shipment(db, telemetry.shipment_id) is None:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"shipment_id {telemetry.shipment_id} does not exist",
        )
    reading = crud.create_telemetry(db, telemetry)
    try:
        from ..services.alerts import evaluate_after_telemetry

        evaluate_after_telemetry(db, telemetry.shipment_id)
    except Exception as exc:  # noqa: BLE001 - ingest must still succeed
        print(f"[telemetry] Reading stored; alert evaluation failed: {exc}")
    return reading


@router.get("", response_model=list[schemas.TelemetryRead])
def list_telemetry(
    shipment_id: int = Query(..., description="Shipment to fetch readings for"),
    skip: int = 0,
    limit: int = 100,
    db: Session = Depends(get_db),
):
    """Read latest telemetry for a shipment: /telemetry?shipment_id=1"""
    if crud.get_shipment(db, shipment_id) is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Shipment not found")
    return crud.get_telemetry_for_shipment(db, shipment_id, skip=skip, limit=limit)