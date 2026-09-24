"""
ColdChain AI - Backend entry point (FastAPI).

Step 2: PostgreSQL via SQLAlchemy.
- /health reports API + database status
- CRUD APIs for products and shipments
- Telemetry ingestion API
"""

from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from .config import get_settings
from .database import Base, check_connection, engine
from .mqtt_client import subscriber
from .routers import alerts, chat, dashboard, products, risk, shipments, telemetry
from .services import ml_inference
from . import models  # noqa: F401  (register tables on Base.metadata)

settings = get_settings()

# Holds the result of the startup DB check so /health can report it.
db_status: dict = {"connected": False, "error": None}


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Runs once at startup: verify DB connection and create tables."""
    try:
        check_connection()
        Base.metadata.create_all(bind=engine)
        db_status.update(connected=True, error=None)
        print("[startup] PostgreSQL connected; tables are up to date.")
    except Exception as exc:  # surface a clear message instead of crashing
        db_status.update(connected=False, error=str(exc))
        print(f"[startup] WARNING - PostgreSQL connection failed: {exc}")

    # Step 5: load the small ML artifacts once at startup (Keras stays lazy).
    try:
        ml_inference.registry.load_lightweight()
    except Exception as exc:  # noqa: BLE001 - backend must boot without ML
        print(f"[startup] WARNING - ML artifacts could not be loaded: {exc}")

    # Step 3: start the MQTT telemetry subscriber (background thread).
    subscriber.start()
    yield
    subscriber.stop()
    print("[shutdown] Bye!")


app = FastAPI(
    title=settings.app_name,
    description="Real-Time Cold Chain Logistics Monitoring & Spoilage Risk Prediction",
    version="0.2.0",
    lifespan=lifespan,
)

# Allow the Vite dev server (http://localhost:5173) to call the API.
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# --- Routers ---
app.include_router(products.router)
app.include_router(shipments.router)
app.include_router(telemetry.router)
app.include_router(risk.router)
app.include_router(alerts.router)
app.include_router(dashboard.router)
app.include_router(chat.router)


@app.get("/health")
def health() -> dict:
    """Health check for the API, database and ML artifacts."""
    ml = ml_inference.registry.summary()
    return {
        "status": "ok" if db_status["connected"] else "degraded",
        "service": "coldchain-ai-backend",
        "version": "0.2.0",
        "database": "connected" if db_status["connected"] else "error",
        "database_error": db_status["error"],
        "ml_enabled": ml.get("enabled", False),
        "ml_available": ml.get("available", []),
        "ml_unavailable": ml.get("unavailable", []),
    }


@app.get("/ml/status")
def ml_status() -> dict:
    """ML artifact availability (nothing trained, nothing fabricated)."""
    return ml_inference.registry.summary()


@app.get("/")
def root() -> dict:
    return {
        "message": "ColdChain AI backend is running.",
        "docs": "/docs",
        "health": "/health",
    }
