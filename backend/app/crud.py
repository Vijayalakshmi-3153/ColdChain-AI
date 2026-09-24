"""
CRUD (Create, Read, Update, Delete) helper functions.

Routers stay thin: they parse/validate input and call these functions.
"""

from datetime import datetime

from sqlalchemy.orm import Session

from . import models, schemas


# ---------------------------------------------------------------------------
# Products
# ---------------------------------------------------------------------------
def get_product(db: Session, product_id: int) -> models.Product | None:
    return db.query(models.Product).filter(models.Product.id == product_id).first()


def get_products(db: Session, skip: int = 0, limit: int = 100) -> list[models.Product]:
    return db.query(models.Product).offset(skip).limit(limit).all()


def create_product(db: Session, product: schemas.ProductCreate) -> models.Product:
    db_product = models.Product(**product.model_dump())
    db.add(db_product)
    db.commit()
    db.refresh(db_product)
    return db_product


def update_product(
    db: Session, db_product: models.Product, product: schemas.ProductUpdate
) -> models.Product:
    update_data = product.model_dump(exclude_unset=True)
    for field, value in update_data.items():
        setattr(db_product, field, value)
    db.commit()
    db.refresh(db_product)
    return db_product


def delete_product(db: Session, db_product: models.Product) -> None:
    db.delete(db_product)
    db.commit()


# ---------------------------------------------------------------------------
# Shipments
# ---------------------------------------------------------------------------
def get_shipment(db: Session, shipment_id: int) -> models.Shipment | None:
    return db.query(models.Shipment).filter(models.Shipment.id == shipment_id).first()


def get_shipments(
    db: Session,
    skip: int = 0,
    limit: int = 100,
    status: str | None = None,
) -> list[models.Shipment]:
    query = db.query(models.Shipment)
    if status:
        query = query.filter(models.Shipment.status == status)
    return query.offset(skip).limit(limit).all()


def create_shipment(db: Session, shipment: schemas.ShipmentCreate) -> models.Shipment:
    db_shipment = models.Shipment(**shipment.model_dump())
    db.add(db_shipment)
    db.commit()
    db.refresh(db_shipment)
    return db_shipment


def update_shipment(
    db: Session, db_shipment: models.Shipment, shipment: schemas.ShipmentUpdate
) -> models.Shipment:
    update_data = shipment.model_dump(exclude_unset=True)
    for field, value in update_data.items():
        setattr(db_shipment, field, value)
    db.commit()
    db.refresh(db_shipment)
    return db_shipment


def delete_shipment(db: Session, db_shipment: models.Shipment) -> None:
    db.delete(db_shipment)
    db.commit()


def update_shipment_packaging(
    db: Session,
    db_shipment: models.Shipment,
    *,
    image_path: str,
    result: dict,
) -> models.Shipment:
    """Persist the latest packaging image path and cached CNN result."""
    db_shipment.packaging_image_path = image_path
    db_shipment.packaging_result = result
    db.commit()
    db.refresh(db_shipment)
    return db_shipment


# ---------------------------------------------------------------------------
# Telemetry
# ---------------------------------------------------------------------------
def create_telemetry(
    db: Session, telemetry: schemas.TelemetryCreate
) -> models.Telemetry:
    data = telemetry.model_dump(exclude={"timestamp"})
    db_telemetry = models.Telemetry(
        **data,
        timestamp=telemetry.timestamp,  # None -> server default (func.now)
    )
    db.add(db_telemetry)
    db.commit()
    db.refresh(db_telemetry)
    return db_telemetry


def get_telemetry_for_shipment(
    db: Session, shipment_id: int, skip: int = 0, limit: int = 100
) -> list[models.Telemetry]:
    """Latest readings first."""
    return (
        db.query(models.Telemetry)
        .filter(models.Telemetry.shipment_id == shipment_id)
        .order_by(models.Telemetry.timestamp.desc())
        .offset(skip)
        .limit(limit)
        .all()
    )


# ---------------------------------------------------------------------------
# Alerts
# ---------------------------------------------------------------------------
def get_alerts_for_shipment(
    db: Session, shipment_id: int, skip: int = 0, limit: int = 100
) -> list[models.Alert]:
    return (
        db.query(models.Alert)
        .filter(models.Alert.shipment_id == shipment_id)
        .order_by(models.Alert.created_at.desc())
        .offset(skip)
        .limit(limit)
        .all()
    )


def get_alerts(
    db: Session,
    acknowledged: bool | None = None,
    skip: int = 0,
    limit: int = 100,
) -> list[models.Alert]:
    """All alerts, optionally filtered by acknowledgement state (newest first)."""
    query = db.query(models.Alert)
    if acknowledged is not None:
        query = query.filter(models.Alert.acknowledged == acknowledged)
    return query.order_by(models.Alert.created_at.desc()).offset(skip).limit(limit).all()


def get_alert(db: Session, alert_id: int) -> models.Alert | None:
    return db.query(models.Alert).filter(models.Alert.id == alert_id).first()


def create_alert(db: Session, alert: schemas.AlertCreate) -> models.Alert:
    """Persist one alert (used by the Step 5 alert engine)."""
    db_alert = models.Alert(**alert.model_dump())
    db.add(db_alert)
    db.commit()
    db.refresh(db_alert)
    return db_alert


def get_open_alert_by_type(
    db: Session, shipment_id: int, alert_type: str, created_after: datetime
) -> models.Alert | None:
    """
    Existing UNACKNOWLEDGED alert of the same type, created after
    `created_after` - used for alert deduplication (Step 5).
    """
    return (
        db.query(models.Alert)
        .filter(
            models.Alert.shipment_id == shipment_id,
            models.Alert.alert_type == alert_type,
            models.Alert.acknowledged.is_(False),
            models.Alert.created_at >= created_after,
        )
        .order_by(models.Alert.created_at.desc())
        .first()
    )


def acknowledge_alert(db: Session, alert: models.Alert) -> models.Alert:
    alert.acknowledged = True
    db.commit()
    db.refresh(alert)
    return alert


def count_alerts(db: Session, acknowledged: bool | None = None) -> int:
    query = db.query(models.Alert)
    if acknowledged is not None:
        query = query.filter(models.Alert.acknowledged == acknowledged)
    return query.count()
