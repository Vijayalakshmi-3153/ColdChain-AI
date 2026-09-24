"""
Shipment API routes: CRUD for shipments (+ related telemetry/alerts reads).
"""

from datetime import datetime, timezone
from pathlib import Path

from fastapi import APIRouter, Depends, File, HTTPException, UploadFile, status
from sqlalchemy.orm import Session

from .. import crud, schemas
from ..database import get_db
from ..services.exposure import compute_exposure
from ..services.ml_inference import classify_packaging

router = APIRouter(prefix="/shipments", tags=["shipments"])

PROJECT_ROOT = Path(__file__).resolve().parents[3]
PACKAGING_ROOT = PROJECT_ROOT / "data" / "packaging"
ALLOWED_IMAGE_TYPES = {"image/png", "image/jpeg", "image/jpg", "image/webp"}
ALLOWED_SUFFIXES = {".png", ".jpg", ".jpeg", ".webp"}
MAX_PACKAGING_BYTES = 5 * 1024 * 1024


@router.get("", response_model=list[schemas.ShipmentRead])
def list_shipments(
    skip: int = 0,
    limit: int = 100,
    status_filter: str | None = None,
    db: Session = Depends(get_db),
):
    """List shipments, optionally filtered by status (?status_filter=in_transit)."""
    return crud.get_shipments(db, skip=skip, limit=limit, status=status_filter)


@router.get("/{shipment_id}", response_model=schemas.ShipmentRead)
def get_shipment(shipment_id: int, db: Session = Depends(get_db)):
    """Get a single shipment by id."""
    shipment = crud.get_shipment(db, shipment_id)
    if shipment is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Shipment not found")
    return shipment


@router.post("", response_model=schemas.ShipmentRead, status_code=status.HTTP_201_CREATED)
def create_shipment(shipment: schemas.ShipmentCreate, db: Session = Depends(get_db)):
    """Create a new shipment (product_id must exist)."""
    if crud.get_product(db, shipment.product_id) is None:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"product_id {shipment.product_id} does not exist",
        )
    return crud.create_shipment(db, shipment)


@router.patch("/{shipment_id}", response_model=schemas.ShipmentRead)
def update_shipment(
    shipment_id: int, shipment: schemas.ShipmentUpdate, db: Session = Depends(get_db)
):
    """Partially update a shipment (e.g. status or last known position)."""
    db_shipment = crud.get_shipment(db, shipment_id)
    if db_shipment is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Shipment not found")
    return crud.update_shipment(db, db_shipment, shipment)


@router.delete("/{shipment_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_shipment(shipment_id: int, db: Session = Depends(get_db)):
    """Delete a shipment (cascades to telemetry and alerts)."""
    db_shipment = crud.get_shipment(db, shipment_id)
    if db_shipment is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Shipment not found")
    crud.delete_shipment(db, db_shipment)


# ---------------------------------------------------------------------------
# Related reads
# ---------------------------------------------------------------------------
@router.get("/{shipment_id}/telemetry", response_model=list[schemas.TelemetryRead])
def list_shipment_telemetry(
    shipment_id: int, skip: int = 0, limit: int = 100, db: Session = Depends(get_db)
):
    """Latest telemetry readings for a shipment."""
    if crud.get_shipment(db, shipment_id) is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Shipment not found")
    return crud.get_telemetry_for_shipment(db, shipment_id, skip=skip, limit=limit)


@router.get("/{shipment_id}/alerts", response_model=list[schemas.AlertRead])
def list_shipment_alerts(
    shipment_id: int, skip: int = 0, limit: int = 100, db: Session = Depends(get_db)
):
    """Alerts raised for a shipment."""
    if crud.get_shipment(db, shipment_id) is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Shipment not found")
    return crud.get_alerts_for_shipment(db, shipment_id, skip=skip, limit=limit)


@router.get("/{shipment_id}/exposure", response_model=schemas.ExposureRead)
def get_exposure(shipment_id: int, db: Session = Depends(get_db)):
    """
    Cumulative temperature-exposure summary for a shipment.

    Combines the telemetry history with the product's temperature limits
    (min/max, shelf_life_hours, q10, maximum_allowed_excursion_minutes).
    """
    shipment = crud.get_shipment(db, shipment_id)
    if shipment is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Shipment not found")

    product = crud.get_product(db, shipment.product_id)
    readings = crud.get_telemetry_for_shipment(db, shipment_id, skip=0, limit=100_000)

    metrics = compute_exposure(product, readings)
    return {
        "shipment_id": shipment.id,
        "shipment_status": shipment.status,
        "product": product,
        "metrics": metrics,
    }


@router.post(
    "/{shipment_id}/packaging",
    response_model=schemas.PackagingRead,
    status_code=status.HTTP_200_OK,
    summary="Upload a packaging image and classify it with the CNN",
)
async def upload_packaging_image(
    shipment_id: int,
    file: UploadFile = File(..., description="Packaging photo (PNG, JPEG, or WebP)"),
    db: Session = Depends(get_db),
):
    """
    Store one packaging image on local disk and cache the CNN result.

    GET /shipments/{id}/risk reads the stored result and does not re-run CNN.
    """
    shipment = crud.get_shipment(db, shipment_id)
    if shipment is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Shipment not found")

    suffix = Path(file.filename or "").suffix.lower()
    content_type = (file.content_type or "").lower()
    if suffix not in ALLOWED_SUFFIXES and content_type not in ALLOWED_IMAGE_TYPES:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Upload a PNG, JPEG, or WebP packaging image",
        )

    raw = await file.read()
    if not raw:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Uploaded file is empty")
    if len(raw) > MAX_PACKAGING_BYTES:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Packaging image must be 5 MB or smaller",
        )

    try:
        from PIL import Image
        import io

        with Image.open(io.BytesIO(raw)) as image:
            image.verify()
    except Exception:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="File is not a readable image",
        )

    dest_dir = PACKAGING_ROOT / str(shipment.id)
    dest_dir.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S%f")
    dest_name = f"{stamp}{suffix or '.png'}"
    dest_path = dest_dir / dest_name
    dest_path.write_bytes(raw)

    result = classify_packaging(raw)
    relative = str(dest_path.relative_to(PROJECT_ROOT)).replace("\\", "/")
    crud.update_shipment_packaging(db, shipment, image_path=relative, result=result)
    return result
