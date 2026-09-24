# IoT Telemetry Simulator

A beginner-friendly simulator that pretends to be the sensor gateway of
cold-chain trucks. It fetches the real shipments from the backend API,
generates **realistic, changing** temperature/humidity/GPS values, and
publishes them as JSON over **MQTT**.

## Prerequisites

1. Mosquitto broker running (see root `README.md` or `infra/mosquitto/mosquitto.conf`).
2. Backend running at http://127.0.0.1:8000 with at least one product + shipment.
3. Python dependencies: `pip install -r simulator/requirements.txt`
   (only `paho-mqtt`; you can reuse the backend virtual environment).

## Run

```powershell
cd simulator
python device_simulator.py --count 30 --interval 1.0
```

Options:

| Flag | Default | Purpose |
|------|---------|---------|
| `--api-base` | `http://127.0.0.1:8000` | Backend used to discover shipments/products |
| `--host` / `--port` | `localhost` / `1883` | MQTT broker (`MQTT_HOST`/`MQTT_PORT` env also work) |
| `--prefix` | `coldchain` | Topic prefix (`MQTT_TOPIC_PREFIX`) |
| `--count` | `20` | Number of ticks per shipment |
| `--interval` | `1.0` | Seconds between ticks |

MQTT credentials (if your broker needs them) come from the environment
variables `MQTT_USERNAME` / `MQTT_PASSWORD` - never hardcode them.

## MQTT topic

```
coldchain/shipments/<shipment_id>/telemetry
```

## Telemetry JSON structure

```json
{
  "shipment_id": 1,
  "timestamp": "2026-09-23T08:00:00+00:00",
  "temperature": 4.82,
  "humidity": 55.3,
  "latitude": 28.6134,
  "longitude": 77.2019,
  "battery_level": 88.4,
  "door_open": false
}
```

## How realistic values are produced

- **Temperature**: random walk that drifts back to the centre of the
  product's allowed range, plus noise. ~10% of ticks add a spike outside
  the allowed range and open-door events push the temperature up, so the
  exposure engine always has interesting data to accumulate.
- **Humidity**: random walk clamped to 0-100%.
- **GPS**: small random drift each tick (the truck is moving).
- **Battery**: slowly drains.
- **Door**: ~5% chance of being open on a tick.

The backend's MQTT subscriber (`backend/app/mqtt_client.py`) validates
each message (shipment must exist) and stores it in the `telemetry` table.