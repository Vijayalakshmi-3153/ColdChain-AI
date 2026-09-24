# ColdChain AI

**Real-Time Cold Chain Logistics Monitoring & Spoilage Risk Prediction**

> **Status: Phase A – Step 3 (IoT ingestion + cumulative exposure).**
> PostgreSQL + SQLAlchemy models, CRUD APIs, the MQTT telemetry pipeline,
> the IoT simulator and the cumulative temperature-exposure engine are in
> place. ML models, dashboard, maps and chatbot are planned for later steps.

## Tech stack

| Layer        | Technology |
|--------------|------------|
| Frontend     | React + Vite, Leaflet + OpenStreetMap |
| Backend      | FastAPI (Python) |
| Database     | PostgreSQL |
| Cache        | Redis |
| Object store | MinIO |
| Messaging    | MQTT (Mosquitto) |
| ML           | XGBoost, LSTM, Autoencoder, CNN |
| Explainability | SHAP |
| AI chatbot   | OpenAI API (via FastAPI backend) |
| Orchestration | Docker Compose |

## Project structure

```
AI-final/
├── backend/      FastAPI app (health endpoint at /health)
├── frontend/     React + Vite app
├── ml/           ML models (planned, not implemented yet)
├── simulator/    IoT sensor simulator (planned)
├── infra/        Service configs (Mosquitto, etc.)
├── data/         Datasets & model artifacts (git-ignored parts)
├── docs/         Architecture documentation
├── .env.example  Environment variable template
├── docker-compose.yml
└── README.md
```

## Quick start (local development)

### 1. Environment variables

Copy `.env.example` to `.env` (backend reads it) and set your PostgreSQL
credentials – **never hardcode passwords in source code**:

    DB_HOST=localhost
    DB_PORT=5432
    DB_NAME=coldchain
    DB_USER=postgres
    DB_PASSWORD=your-real-password

### 2. Database (PostgreSQL)

Make sure the PostgreSQL service is running, then initialize the schema
from the `backend/` folder:

    python -m app.init_db

This creates the database (if missing) and the tables `products`,
`shipments`, `telemetry`, `alerts`. For future schema changes use Alembic:

    alembic revision --autogenerate -m "initial schema"
    alembic upgrade head

### 3. Backend (FastAPI)

From the project root:

1. Create and activate a virtual environment: `python -m venv backend\.venv`
   then `backend\.venv\Scripts\activate` (Windows) or
   `source backend/.venv/bin/activate` (macOS/Linux).
2. Install dependencies: `pip install -r backend/requirements.txt`
3. Start the API: `cd backend && uvicorn app.main:app --reload --port 8000`
4. Open http://localhost:8000/health – `database` should be `connected`.
   Interactive docs: http://localhost:8000/docs

### 4. Frontend (React + Vite)

In a second terminal:

1. Install dependencies: `cd frontend && npm install`
2. Start the dev server: `npm run dev`
3. Open http://localhost:5173 – the page shows the backend status card.

The Vite dev server proxies `/api/*` requests to `http://localhost:8000`.

### 5. Full stack with Docker (optional)

With Docker installed, run `docker compose up --build`.
This also starts PostgreSQL, Redis, MinIO and Mosquitto.

## API overview (Step 2)

| Method | Endpoint                       | Purpose                       |
|--------|--------------------------------|-------------------------------|
| GET    | `/health`                      | API + database status         |
| GET/POST | `/products`                  | List / create products        |
| GET/PATCH/DELETE | `/products/{id}`  | Read / update / delete        |
| GET/POST | `/shipments`                 | List / create shipments       |
| GET/PATCH/DELETE | `/shipments/{id}` | Read / update / delete        |
| GET    | `/shipments/{id}/telemetry`    | Telemetry for a shipment      |
| GET    | `/shipments/{id}/alerts`       | Alerts for a shipment         |
| POST   | `/telemetry`                   | Ingest a sensor reading       |
| GET    | `/telemetry?shipment_id=1`     | Read latest telemetry         |
| GET    | `/shipments/{id}/exposure`     | Cumulative exposure summary   |

## MQTT ingestion (Step 3)

**Broker:** Mosquitto (local install or `docker compose up mosquitto`).
Config lives in `.env`: `MQTT_HOST`, `MQTT_PORT`, `MQTT_TOPIC_PREFIX`,
`MQTT_USERNAME`, `MQTT_PASSWORD`, `MQTT_ENABLED` (never hardcoded).

**Topic:** `coldchain/shipments/+/telemetry`

**Telemetry JSON:**

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

The subscriber (`backend/app/mqtt_client.py`) parses the JSON, validates
it with the Pydantic schema, checks the `shipment_id` exists, and stores
the row in `telemetry` with the existing model. It starts automatically
with the backend (lifespan) and logs rejections instead of crashing.

**Start Mosquitto:**

```powershell
# local Windows service (after installing Mosquitto)
net start mosquitto
# or manually with the project config
mosquitto -c infra\mosquitto\mosquitto.conf
# or via Docker
docker compose up mosquitto
```

**Run the simulator:**

```powershell
cd simulator
pip install -r requirements.txt
python device_simulator.py --count 30 --interval 1.0
```

See `simulator/README.md` for all flags and the realistic-value logic.

## Cumulative temperature exposure (Step 3)

`GET /shipments/{shipment_id}/exposure` combines the shipment's telemetry
history with its product limits
(`minimum_temperature`, `maximum_temperature`, `shelf_life_hours`, `q10`,
`maximum_allowed_excursion_minutes`):

1. Readings are sorted and the **gap** (minutes, capped at 60) between
   consecutive readings is attributed to the later reading - so exposure
   **accumulates over time**, it is never a single-threshold check.
2. Out-of-range readings add `total_excursion_minutes` and
   `degree_minutes_outside_range = deviation x gap`.
3. **Q10 thermal ageing** with `Tref` = centre of the allowed range:
   `equivalent_age += gap_hours * q10 ** ((T - Tref) / 10)`.
   `remaining_shelf_life = max(shelf_life_hours - equivalent_age, 0)`.
4. Status: `critical` if excursion minutes exceed the allowed limit,
   `warning` for any excursion, otherwise `normal` (`no_data` if empty).

Response: shipment id/status, the product, and metrics (total/excursion
readings, % outside range, monitored & excursion minutes, degree-minutes,
min/max observed temperature, equivalent age, remaining shelf life).

**Tests:** `cd backend && python -m pytest tests -v` (11 tests: normal,
above-max, below-min, consecutive excursions, cumulative/Q10 maths,
invalid shipment id, API response shape).

## Roadmap (later steps)

- [x] Project foundation + FastAPI health endpoint + React scaffold
- [x] PostgreSQL schema, SQLAlchemy models and CRUD APIs (Step 2)
- [x] MQTT ingestion (Mosquitto) + IoT simulator + exposure engine (Step 3)
- [ ] Redis caching and MinIO storage integration
- [ ] ML models (XGBoost, LSTM, Autoencoder, CNN) + SHAP explainability
- [ ] Dashboard with Leaflet/OpenStreetMap live map
- [ ] AI chatbot (OpenAI API through FastAPI)

## Documentation

See `docs/architecture.md` for the system design.