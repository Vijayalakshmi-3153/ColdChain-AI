"""
SQLAlchemy ORM models for ColdChain AI.

Entities: Product, Shipment, Telemetry, Alert.
"""

from datetime import datetime

from sqlalchemy import (
    JSON,
    Boolean,
    DateTime,
    Float,
    ForeignKey,
    Integer,
    String,
    Text,
    func,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from .database import Base


class Product(Base):
    """A cold-chain product and its storage requirements."""

    __tablename__ = "products"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    name: Mapped[str] = mapped_column(String(200), nullable=False, index=True)
    category: Mapped[str] = mapped_column(String(100), nullable=False, index=True)

    # Temperature / humidity requirements
    minimum_temperature: Mapped[float] = mapped_column(Float, nullable=False)  # °C
    maximum_temperature: Mapped[float] = mapped_column(Float, nullable=False)  # °C
    minimum_humidity: Mapped[float] = mapped_column(Float, nullable=False)     # % RH
    maximum_humidity: Mapped[float] = mapped_column(Float, nullable=False)     # % RH

    # Spoilage-relevant parameters
    shelf_life_hours: Mapped[float] = mapped_column(Float, nullable=False)
    q10: Mapped[float] = mapped_column(Float, nullable=False, default=2.0)
    maximum_allowed_excursion_minutes: Mapped[int] = mapped_column(
        Integer, nullable=False, default=30
    )
    packaging_class: Mapped[str] = mapped_column(String(50), nullable=False)

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )

    # Relationships
    shipments: Mapped[list["Shipment"]] = relationship(back_populates="product")

    def __repr__(self) -> str:
        return f"<Product id={self.id} name={self.name!r}>"


class Shipment(Base):
    """A shipment/trip carrying a product from origin to destination."""

    __tablename__ = "shipments"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    product_id: Mapped[int] = mapped_column(
        ForeignKey("products.id", ondelete="CASCADE"), nullable=False, index=True
    )

    origin: Mapped[str] = mapped_column(String(200), nullable=False)
    destination: Mapped[str] = mapped_column(String(200), nullable=False)
    vehicle_id: Mapped[str] = mapped_column(String(100), nullable=False, index=True)

    # e.g. pending, in_transit, delayed, delivered, cancelled
    status: Mapped[str] = mapped_column(
        String(50), nullable=False, default="pending", index=True
    )

    start_time: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=func.now()
    )
    estimated_arrival_time: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )

    # Last known position
    latitude: Mapped[float | None] = mapped_column(Float, nullable=True)
    longitude: Mapped[float | None] = mapped_column(Float, nullable=True)

    # Latest packaging inspection image (local disk) and cached CNN result.
    packaging_image_path: Mapped[str | None] = mapped_column(String(500), nullable=True)
    packaging_result: Mapped[dict | None] = mapped_column(JSON, nullable=True)

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )

    # Relationships
    product: Mapped["Product"] = relationship(back_populates="shipments")
    telemetry: Mapped[list["Telemetry"]] = relationship(
        back_populates="shipment", cascade="all, delete-orphan"
    )
    alerts: Mapped[list["Alert"]] = relationship(
        back_populates="shipment", cascade="all, delete-orphan"
    )

    def __repr__(self) -> str:
        return f"<Shipment id={self.id} vehicle={self.vehicle_id!r} status={self.status!r}>"


class Telemetry(Base):
    """A single sensor reading for a shipment (IoT telemetry)."""

    __tablename__ = "telemetry"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    shipment_id: Mapped[int] = mapped_column(
        ForeignKey("shipments.id", ondelete="CASCADE"), nullable=False, index=True
    )

    timestamp: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=func.now(), index=True
    )

    temperature: Mapped[float] = mapped_column(Float, nullable=False)  # °C
    humidity: Mapped[float] = mapped_column(Float, nullable=False)     # % RH
    latitude: Mapped[float | None] = mapped_column(Float, nullable=True)
    longitude: Mapped[float | None] = mapped_column(Float, nullable=True)

    battery_level: Mapped[float | None] = mapped_column(Float, nullable=True)  # %
    door_open: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)

    # Relationships
    shipment: Mapped["Shipment"] = relationship(back_populates="telemetry")

    def __repr__(self) -> str:
        return f"<Telemetry id={self.id} shipment_id={self.shipment_id} temp={self.temperature}>"


class Alert(Base):
    """An alert raised for a shipment (e.g. temperature excursion)."""

    __tablename__ = "alerts"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    shipment_id: Mapped[int] = mapped_column(
        ForeignKey("shipments.id", ondelete="CASCADE"), nullable=False, index=True
    )

    alert_type: Mapped[str] = mapped_column(String(100), nullable=False, index=True)
    # e.g. info, warning, critical
    severity: Mapped[str] = mapped_column(
        String(50), nullable=False, default="warning", index=True
    )
    message: Mapped[str] = mapped_column(Text, nullable=False)
    recommended_action: Mapped[str | None] = mapped_column(Text, nullable=True)

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), index=True
    )
    acknowledged: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=False, index=True
    )

    # Relationships
    shipment: Mapped["Shipment"] = relationship(back_populates="alerts")

    def __repr__(self) -> str:
        return f"<Alert id={self.id} type={self.alert_type!r} severity={self.severity!r}>"