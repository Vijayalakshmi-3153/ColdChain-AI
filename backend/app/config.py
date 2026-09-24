"""
Central configuration for the ColdChain AI backend.

All secrets come from environment variables (or a local .env file).
Never hardcode passwords in the source code.
"""

from functools import lru_cache
from urllib.parse import quote

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Application settings loaded from environment variables / .env."""

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    # --- App ---
    app_name: str = "ColdChain AI API"
    backend_host: str = "0.0.0.0"
    backend_port: int = 8000
    frontend_url: str = "http://localhost:5173"

    # --- PostgreSQL (credentials come from env vars only) ---
    db_host: str = "localhost"
    db_port: int = 5432
    db_name: str = "coldchain"
    db_user: str = "coldchain"
    db_password: str = ""

    # Optional full URL - if set, it overrides the individual db_* values.
    database_url: str = ""

    # --- Other services (used in later steps) ---
    redis_url: str = "redis://localhost:6379/0"
    minio_endpoint: str = "http://localhost:9000"
    minio_root_user: str = "minioadmin"
    minio_root_password: str = "minioadmin"
    minio_bucket: str = "coldchain"
    mqtt_enabled: bool = True
    mqtt_host: str = "localhost"
    mqtt_port: int = 1883
    mqtt_topic_prefix: str = "coldchain"
    mqtt_username: str = ""
    mqtt_password: str = ""
    openai_api_key: str = ""
    openai_model: str = "gpt-4o-mini"

    # ------------------------------------------------------------------
    # --- ML serving (Step 5) ---
    # Artifacts trained in Step 4 are loaded from <project root>/ml/artifacts.
    # Nothing here retrains or downloads anything.
    # ------------------------------------------------------------------
    ml_enabled: bool = True
    # Optional override for the artifacts folder (defaults to ml/artifacts).
    ml_artifacts_dir: str = ""
    # Load the Keras models (LSTM/AE/CNN) at startup instead of on first use.
    ml_preload_keras_models: bool = False
    # Compute SHAP explanations for the XGBoost prediction (can be disabled
    # to make the risk endpoint cheaper).
    ml_shap_enabled: bool = True
    # How many telemetry readings are loaded per shipment for feature building.
    ml_max_readings_per_shipment: int = 5000
    # Cache TTL for a shipment risk assessment (polling-friendly).
    ml_cache_ttl_seconds: int = 15
    # The live PostgreSQL schema has no planned-route-distance column, while
    # the XGBoost feature set contains `route_distance_km`. When the value is
    # unknown it is imputed with this documented default (median route length
    # of the SYNTHETIC/DEMO training data) and reported in
    # `data_quality.imputed_features`.
    ml_route_distance_default_km: float = 621.55

    # ------------------------------------------------------------------
    # --- Risk classification (Step 5) ---
    # APPLICATION/DEMO thresholds only - NOT medical or regulatory limits.
    # Bands for a 0..1 risk score: LOW [0, low_max), MEDIUM [low_max, medium_max),
    # HIGH [medium_max, high_max), CRITICAL [high_max, 1].
    # ------------------------------------------------------------------
    risk_low_max: float = 0.25
    risk_medium_max: float = 0.50
    risk_high_max: float = 0.75
    # Weighting used to blend MODEL OUTPUT (XGBoost risk score) with
    # RULE-BASED OUTPUT (exposure/shelf-life severity). Weights are
    # re-normalized over whichever component is available.
    risk_model_weight: float = 0.6
    risk_rule_weight: float = 0.4
    # An XGBoost score at/above this is the model's own "spoilage risk" flag.
    risk_model_decision_threshold: float = 0.65

    # ------------------------------------------------------------------
    # --- Alerts (Step 5) ---
    # An existing UNACKNOWLEDGED alert of the same type is not raised again
    # while it is younger than this cooldown (deduplication window).
    # ------------------------------------------------------------------
    alert_dedup_cooldown_minutes: int = 30
    alert_low_battery_percent: float = 20.0
    alert_raise_forecast_breach: bool = True

    # ------------------------------------------------------------------
    # --- Dashboard (Step 5) ---
    # Shipments are assessed (ML + rules) for the dashboard summary/list.
    # This caps how many are assessed per refresh for predictable latency.
    # ------------------------------------------------------------------
    dashboard_max_shipments: int = 50

    @property
    def sqlalchemy_database_url(self) -> str:
        """Build the SQLAlchemy connection URL."""
        if self.database_url:
            return self.database_url
        # URL-encode credentials so passwords with '@', ':', '/' etc. work.
        user = quote(self.db_user, safe="")
        password = quote(self.db_password, safe="")
        return (
            f"postgresql://{user}:{password}"
            f"@{self.db_host}:{self.db_port}/{self.db_name}"
        )


@lru_cache
def get_settings() -> Settings:
    """Return a cached Settings instance (reads .env / environment once)."""
    return Settings()