"""
Modular MQTT subscriber for ColdChain AI.

Subscribes to:  <prefix>/shipments/+/telemetry   (e.g. coldchain/shipments/+/telemetry)

Flow for each message:
  1. Parse JSON payload
  2. Validate with the TelemetryCreate Pydantic schema
  3. Check that the shipment exists in PostgreSQL
  4. Store the reading with the existing Telemetry model

Configuration (host, port, credentials, topic prefix) comes from
environment variables via app.config.Settings - no hardcoded secrets.
"""

import json
import threading

import paho.mqtt.client as mqtt
from paho.mqtt.enums import CallbackAPIVersion

from . import crud, schemas
from .config import get_settings
from .database import SessionLocal

settings = get_settings()

# Reconnect automatically if the broker restarts.
RECONNECT_DELAY_SECONDS = 5


class TelemetrySubscriber:
    """Thin, reusable wrapper around a paho-mqtt client."""

    def __init__(self) -> None:
        self._client: mqtt.Client | None = None
        self._lock = threading.Lock()
        self.received_count = 0
        self.stored_count = 0
        self.rejected_count = 0

    # ------------------------------------------------------------------
    # Lifecycle
    # ------------------------------------------------------------------
    def start(self) -> None:
        """Connect to the broker and start the network loop (background)."""
        if not settings.mqtt_enabled:
            print("[mqtt] MQTT disabled via MQTT_ENABLED=false")
            return

        client_id = "coldchain-backend"
        self._client = mqtt.Client(
            callback_api_version=CallbackAPIVersion.VERSION2,
            client_id=client_id,
            protocol=mqtt.MQTTv311,
        )

        if settings.mqtt_username:
            self._client.username_pw_set(
                settings.mqtt_username, settings.mqtt_password
            )

        self._client.on_connect = self._on_connect
        self._client.on_message = self._on_message
        self._client.on_disconnect = self._on_disconnect
        self._client.reconnect_delay_set(min_delay=1, max_delay=RECONNECT_DELAY_SECONDS)

        try:
            self._client.connect(settings.mqtt_host, settings.mqtt_port, keepalive=60)
        except OSError as exc:
            print(
                f"[mqtt] Could not reach broker at "
                f"{settings.mqtt_host}:{settings.mqtt_port} - {exc}"
            )
            print("[mqtt] Backend keeps running; MQTT will retry on next start.")
            return

        self._client.loop_start()
        print(
            f"[mqtt] Connecting to {settings.mqtt_host}:{settings.mqtt_port} "
            f"topic '{self.topic_filter}'"
        )

    def stop(self) -> None:
        """Stop the network loop cleanly (called at app shutdown)."""
        if self._client is None:
            return
        try:
            self._client.loop_stop()
            self._client.disconnect()
        finally:
            self._client = None
        print("[mqtt] Stopped.")

    # ------------------------------------------------------------------
    # Properties
    # ------------------------------------------------------------------
    @property
    def topic_filter(self) -> str:
        return f"{settings.mqtt_topic_prefix}/shipments/+/telemetry"

    # ------------------------------------------------------------------
    # MQTT callbacks
    # ------------------------------------------------------------------
    def _on_connect(self, client, userdata, flags, reason_code, properties=None) -> None:
        if reason_code.is_failure:
            print(f"[mqtt] Connection failed: {reason_code}")
            return
        client.subscribe(self.topic_filter, qos=1)
        print(f"[mqtt] Connected. Subscribed to {self.topic_filter}")

    def _on_disconnect(self, client, userdata, flags, reason_code, properties=None) -> None:
        print(f"[mqtt] Disconnected ({reason_code}); auto-reconnect is on.")

    def _on_message(self, client, userdata, msg) -> None:
        with self._lock:
            self.received_count += 1
        try:
            payload = json.loads(msg.payload.decode("utf-8"))
        except (UnicodeDecodeError, json.JSONDecodeError) as exc:
            self.rejected_count += 1
            print(f"[mqtt] Rejected non-JSON message on {msg.topic}: {exc}")
            return

        self.handle_telemetry_payload(payload)

    # ------------------------------------------------------------------
    # Business logic (also handy for tests)
    # ------------------------------------------------------------------
    def handle_telemetry_payload(self, payload: dict) -> bool:
        """Validate and persist one telemetry payload. Returns True if stored."""
        try:
            reading = schemas.TelemetryCreate(**payload)
        except Exception as exc:  # pydantic ValidationError
            self.rejected_count += 1
            print(f"[mqtt] Rejected invalid payload: {exc}")
            return False

        db = SessionLocal()
        try:
            if crud.get_shipment(db, reading.shipment_id) is None:
                self.rejected_count += 1
                print(
                    f"[mqtt] Rejected reading: shipment_id "
                    f"{reading.shipment_id} does not exist"
                )
                return False
            crud.create_telemetry(db, reading)
            self.stored_count += 1
            try:
                from .services.alerts import evaluate_after_telemetry

                evaluate_after_telemetry(db, reading.shipment_id)
            except Exception as exc:  # noqa: BLE001 - ingest must still succeed
                print(f"[mqtt] Telemetry stored; alert evaluation failed: {exc}")
            return True
        except Exception as exc:
            db.rollback()
            self.rejected_count += 1
            print(f"[mqtt] Failed to store telemetry: {exc}")
            return False
        finally:
            db.close()


# Single shared instance used by the FastAPI app.
subscriber = TelemetrySubscriber()