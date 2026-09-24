# ColdChain AI – Architecture (v0.3, Phase A Step 3)

## High-level design

Sensor data flows through the system in stages:

1. **IoT devices / simulator** publish telemetry over MQTT.
2. **Mosquitto** broker receives messages on
   `coldchain/shipments/+/telemetry`.
3. **FastAPI backend** subscribes to MQTT, validates data, caches the latest
   readings in **Redis**, and persists history in **PostgreSQL**.
4. **MinIO** stores larger artifacts (raw files, model binaries, images).
5. **ML layer** (XGBoost, LSTM, Autoencoder, CNN + SHAP) computes spoilage
   risk and anomaly scores; results are exposed through the backend API.
6. **React + Vite frontend** renders the dashboard, Leaflet/OpenStreetMap
   routes, alerts, and the AI chatbot (OpenAI API proxied via FastAPI).

## Planned technology stack

- Frontend: React + Vite, Leaflet + OpenStreetMap
- Backend: FastAPI (Python)
- Database: PostgreSQL, cache: Redis, object storage: MinIO
- Messaging: MQTT (Mosquitto)
- ML: XGBoost, LSTM, Autoencoder, CNN; explainability with SHAP
- Chatbot: OpenAI API accessed only through the FastAPI backend
- Orchestration: Docker Compose

## Current status (Phase A, Step 3)

Implemented so far:

- **Foundation**: FastAPI `/health` endpoint, React + Vite scaffold,
  folder structure, Docker Compose wiring.
- **Database (Step 2)**: PostgreSQL + SQLAlchemy models
  (`products`, `shipments`, `telemetry`, `alerts`), CRUD APIs,
  `python -m app.init_db`, Alembic scaffolding.
- **MQTT ingestion (Step 3)**: `backend/app/mqtt_client.py` subscribes to
  `coldchain/shipments/+/telemetry`, validates JSON (Pydantic) and the
  `shipment_id`, and stores readings in PostgreSQL. Started/stopped by the
  FastAPI lifespan. Broker + credentials come from environment variables.
- **IoT simulator (Step 3)**: `simulator/device_simulator.py` discovers
  shipments via the API and publishes realistic random-walk telemetry.
- **Cumulative exposure engine (Step 3)**: `backend/app/services/exposure.py`
  computes, over the whole telemetry history:
  - `total_excursion_minutes` (time outside `[min_temperature, max_temperature]`)
  - `degree_minutes_outside_range` (deviation x minutes)
  - observed `max_temperature` / `min_temperature`
  - `percent_readings_outside_range`
  - `equivalent_age_hours` via the Q10 model
    (`age += gap_hours * q10 ** ((T - Tref) / 10)`, `Tref` = range centre)
  - `remaining_shelf_life_hours = max(shelf_life - equivalent_age, 0)`
  - status: `normal` / `warning` / `critical` / `no_data`
  Exposed through `GET /shipments/{id}/exposure`.
- **Tests**: `backend/tests/` (pytest, in-memory SQLite) - 11 tests covering
  normal, above-max, below-min, consecutive excursions, cumulative maths,
  invalid shipment ids.

Intentionally not implemented yet: Redis caching, MinIO storage, dashboard,
Leaflet maps, ML models (XGBoost/LSTM/Autoencoder/CNN), SHAP, AI chatbot.
