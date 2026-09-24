"""
Risk assessment API (Phase A, Step 5).

GET /shipments/{shipment_id}/risk

Combines REAL PostgreSQL telemetry, the Step 3 exposure engine, the Step 4
MODEL OUTPUTs (XGBoost / LSTM / autoencoder / CNN / SHAP) and the RULE-BASED
risk layer into one response. The endpoint is read-only: it never writes
alerts and never trains anything.
"""

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.orm import Session

from .. import crud, schemas
from ..database import get_db
from ..services import risk as risk_service

router = APIRouter(prefix="/shipments", tags=["risk"])


@router.get(
    "/{shipment_id}/risk",
    response_model=schemas.RiskAssessmentRead,
    summary="Spoilage risk assessment for one shipment",
)
def get_shipment_risk(
    shipment_id: int,
    include_shap: bool = Query(True, description="Compute SHAP top contributing factors"),
    refresh: bool = Query(False, description="Bypass the short-lived assessment cache"),
    db: Session = Depends(get_db),
):
    """
    Full risk assessment for a shipment.

    Every part of the response states where its numbers come from:

    * `exposure`, `latest_reading`, `position` - REAL telemetry from PostgreSQL
    * `model_risk_score`, `lstm_forecast`, `anomaly`, `packaging`,
      `shap_top_factors` - MODEL OUTPUT (Step 4 artifacts)
    * `risk_level`, `risk_score`, `recommendations` - MODEL OUTPUT blended with
      RULE-BASED formulas; `risk_reasons`/`notes` show exactly how

    Unavailable models or insufficient data are reported as
    `unavailable` / `insufficient_data` - values are never invented.
    """
    shipment = crud.get_shipment(db, shipment_id)
    if shipment is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Shipment not found")
    product = crud.get_product(db, shipment.product_id)

    assessment = risk_service.assess_shipment(
        db,
        shipment,
        product=product,
        include_shap=include_shap,
        use_cache=not refresh,
    )
    return risk_service.to_api_payload(assessment)
