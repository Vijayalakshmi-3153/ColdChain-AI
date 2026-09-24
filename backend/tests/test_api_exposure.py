"""
API tests for GET /shipments/{shipment_id}/exposure.

Runs against FastAPI's TestClient with an in-memory SQLite database,
so the real PostgreSQL data is untouched.
"""

from datetime import datetime, timedelta, timezone

from app import models

BASE_TIME = datetime(2026, 1, 1, 12, 0, 0, tzinfo=timezone.utc)


def seed_data(db_session) -> None:
    """Create one product, one shipment and four telemetry readings."""
    product = models.Product(
        name="Fresh Milk",
        category="dairy",
        minimum_temperature=2.0,
        maximum_temperature=6.0,
        minimum_humidity=40.0,
        maximum_humidity=70.0,
        shelf_life_hours=48.0,
        q10=2.0,
        maximum_allowed_excursion_minutes=30,
        packaging_class="A",
    )
    db_session.add(product)
    db_session.flush()

    shipment = models.Shipment(
        product_id=product.id,
        origin="Delhi",
        destination="Mumbai",
        vehicle_id="TRK-001",
        status="in_transit",
        start_time=BASE_TIME,
        latitude=28.61,
        longitude=77.20,
    )
    db_session.add(shipment)
    db_session.flush()

    # Two normal readings, two hot readings (excursion).
    temperatures = [(0, 4.0), (10, 4.5), (20, 8.5), (30, 9.0)]
    for offset, temp in temperatures:
        db_session.add(
            models.Telemetry(
                shipment_id=shipment.id,
                temperature=temp,
                humidity=55.0,
                latitude=28.61,
                longitude=77.20,
                battery_level=90.0,
                door_open=False,
                timestamp=BASE_TIME + timedelta(minutes=offset),
            )
        )
    db_session.commit()


# ---------------------------------------------------------------------------
# Invalid shipment id
# ---------------------------------------------------------------------------
def test_exposure_invalid_shipment_id_returns_404(client):
    resp = client.get("/shipments/99999/exposure")
    assert resp.status_code == 404
    assert resp.json()["detail"] == "Shipment not found"


# ---------------------------------------------------------------------------
# Valid shipment: cumulative exposure summary
# ---------------------------------------------------------------------------
def test_exposure_returns_cumulative_metrics(client, db_session):
    seed_data(db_session)

    resp = client.get("/shipments/1/exposure")
    assert resp.status_code == 200
    body = resp.json()

    # Structure
    assert body["shipment_id"] == 1
    assert body["shipment_status"] == "in_transit"
    assert body["product"]["name"] == "Fresh Milk"
    metrics = body["metrics"]

    # Cumulative exposure over the two hot readings:
    # gap 10 min at 8.5 degC (2.5 above max) + gap 10 min at 9.0 (3.0 above)
    assert metrics["total_readings"] == 4
    assert metrics["excursion_readings"] == 2
    assert metrics["total_excursion_minutes"] == 20.0
    assert metrics["degree_minutes_outside_range"] == 2.5 * 10 + 3.0 * 10  # 55
    assert metrics["percent_readings_outside_range"] == 50.0
    assert metrics["max_temperature"] == 9.0
    assert metrics["min_temperature"] == 4.0
    assert metrics["remaining_shelf_life_hours"] < 48.0
    assert metrics["status"] == "warning"  # 20 min <= 30 min allowed


def test_exposure_invalid_shipment_does_not_exist_after_other_shipment(client, db_session):
    """A different unknown id must still 404 even with data present."""
    seed_data(db_session)
    assert client.get("/shipments/1/exposure").status_code == 200
    assert client.get("/shipments/42/exposure").status_code == 404