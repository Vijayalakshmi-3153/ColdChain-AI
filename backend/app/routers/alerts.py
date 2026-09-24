"""
Alert acknowledgement API (Phase A, Step 5).

PATCH /alerts/{alert_id}/acknowledge marks one alert as acknowledged so the
deduplication window allows a fresh alert of the same type later.
"""

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from .. import crud, schemas
from ..database import get_db

router = APIRouter(prefix="/alerts", tags=["alerts"])


@router.patch("/{alert_id}/acknowledge", response_model=schemas.AlertRead)
def acknowledge_alert(alert_id: int, db: Session = Depends(get_db)):
    """Acknowledge one alert by id (404 when unknown)."""
    alert = crud.get_alert(db, alert_id)
    if alert is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Alert not found")
    if alert.acknowledged:
        return alert
    return crud.acknowledge_alert(db, alert)
