"""
Pydantic schemas for request validation and API responses.
"""

from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field


# ---------------------------------------------------------------------------
# Product
# ---------------------------------------------------------------------------
class ProductBase(BaseModel):
    name: str = Field(..., max_length=200)
    category: str = Field(..., max_length=100)
    minimum_temperature: float
    maximum_temperature: float
    minimum_humidity: float
    maximum_humidity: float
    shelf_life_hours: float = Field(..., gt=0)
    q10: float = Field(2.0, gt=0)
    maximum_allowed_excursion_minutes: int = Field(30, ge=0)
    packaging_class: str = Field(..., max_length=50)


class ProductCreate(ProductBase):
    pass


class ProductUpdate(BaseModel):
    """All fields optional - used for partial (PATCH) updates."""

    name: str | None = Field(None, max_length=200)
    category: str | None = Field(None, max_length=100)
    minimum_temperature: float | None = None
    maximum_temperature: float | None = None
    minimum_humidity: float | None = None
    maximum_humidity: float | None = None
    shelf_life_hours: float | None = Field(None, gt=0)
    q10: float | None = Field(None, gt=0)
    maximum_allowed_excursion_minutes: int | None = Field(None, ge=0)
    packaging_class: str | None = Field(None, max_length=50)


class ProductRead(ProductBase):
    id: int
    created_at: datetime

    model_config = ConfigDict(from_attributes=True)


# ---------------------------------------------------------------------------
# Shipment
# ---------------------------------------------------------------------------
class ShipmentBase(BaseModel):
    product_id: int
    origin: str = Field(..., max_length=200)
    destination: str = Field(..., max_length=200)
    vehicle_id: str = Field(..., max_length=100)
    status: str = Field("pending", max_length=50)
    start_time: datetime
    estimated_arrival_time: datetime | None = None
    latitude: float | None = None
    longitude: float | None = None


class ShipmentCreate(ShipmentBase):
    pass


class ShipmentUpdate(BaseModel):
    product_id: int | None = None
    origin: str | None = Field(None, max_length=200)
    destination: str | None = Field(None, max_length=200)
    vehicle_id: str | None = Field(None, max_length=100)
    status: str | None = Field(None, max_length=50)
    start_time: datetime | None = None
    estimated_arrival_time: datetime | None = None
    latitude: float | None = None
    longitude: float | None = None


class ShipmentRead(ShipmentBase):
    id: int
    created_at: datetime
    packaging_image_path: str | None = None
    packaging_result: dict | None = None

    model_config = ConfigDict(from_attributes=True)


# ---------------------------------------------------------------------------
# Telemetry
# ---------------------------------------------------------------------------
class TelemetryBase(BaseModel):
    shipment_id: int
    temperature: float
    humidity: float
    latitude: float | None = None
    longitude: float | None = None
    battery_level: float | None = Field(None, ge=0, le=100)
    door_open: bool = False


class TelemetryCreate(TelemetryBase):
    timestamp: datetime | None = None  # defaults to server time if omitted


class TelemetryRead(TelemetryBase):
    id: int
    timestamp: datetime

    model_config = ConfigDict(from_attributes=True)


# ---------------------------------------------------------------------------
# Alert
# ---------------------------------------------------------------------------
class AlertBase(BaseModel):
    shipment_id: int
    alert_type: str = Field(..., max_length=100)
    severity: str = Field("warning", max_length=50)
    message: str
    recommended_action: str | None = None


class AlertCreate(AlertBase):
    pass


class AlertRead(AlertBase):
    id: int
    created_at: datetime
    acknowledged: bool

    model_config = ConfigDict(from_attributes=True)


# ---------------------------------------------------------------------------
# Exposure (cumulative temperature-exposure summary)
# ---------------------------------------------------------------------------
class ExposureMetrics(BaseModel):
    """Derived metrics produced by the cumulative exposure engine."""

    total_readings: int
    excursion_readings: int
    percent_readings_outside_range: float
    monitored_minutes: float
    total_excursion_minutes: float
    degree_minutes_outside_range: float
    max_temperature: float | None
    min_temperature: float | None
    reference_temperature: float
    q10: float
    equivalent_age_hours: float
    remaining_shelf_life_hours: float
    excursion_limit_minutes: float
    status: str  # normal | warning | critical | no_data


class ExposureRead(BaseModel):
    """Response for GET /shipments/{shipment_id}/exposure."""

    shipment_id: int
    shipment_status: str
    product: ProductRead
    metrics: ExposureMetrics


# ---------------------------------------------------------------------------
# Step 5: ML serving, risk assessment, recommendations, alerts, dashboard
# ---------------------------------------------------------------------------
class LatestReadingRead(BaseModel):
    """Most recent telemetry reading (REAL data from PostgreSQL)."""

    timestamp: datetime
    temperature: float
    humidity: float | None = None
    latitude: float | None = None
    longitude: float | None = None
    battery_level: float | None = None
    door_open: bool = False


class PositionRead(BaseModel):
    """Last known position (from telemetry, else the shipment record)."""

    latitude: float
    longitude: float
    timestamp: datetime | None = None
    source: str


class ModelStatusRead(BaseModel):
    """Availability of one ML artifact group (never a fabricated prediction)."""

    name: str
    kind: str
    available: bool
    loaded: bool
    path: str
    detail: str
    data_kind: str | None = None


class ForecastRead(BaseModel):
    """LSTM forecast (MODEL OUTPUT). Empty values when unavailable."""

    status: str
    model: str = "lstm"
    detail: str | None = None
    seq_len: int | None = None
    horizon_readings: int | None = None
    interval_minutes: float | None = None
    temperature: list[float] | None = None
    humidity: list[float] | None = None
    timestamps: list[datetime] | None = None
    predicted_breach: dict | None = None
    test_metrics: dict | None = None
    data_kind: str | None = None
    note: str | None = None


class AnomalyRead(BaseModel):
    """Autoencoder anomaly score (MODEL OUTPUT)."""

    status: str
    model: str = "autoencoder"
    score: float | None = None
    threshold: float | None = None
    score_ratio: float | None = None
    is_anomaly: bool | None = None
    seq_len: int | None = None
    readings_used: int | None = None
    bands: dict | None = None
    data_kind: str | None = None
    detail: str | None = None


class PackagingRead(BaseModel):
    """CNN packaging-condition result (MODEL OUTPUT) or an explicit no_data."""

    status: str
    model: str = "cnn_packaging"
    predicted_class: str | None = None
    confidence: float | None = None
    probabilities: dict[str, float] | None = None
    classes: list[str] | None = None
    data_kind: str | None = None
    detail: str | None = None
    note: str | None = None


class ShapFactorRead(BaseModel):
    """One SHAP attribution of the XGBoost prediction (MODEL OUTPUT)."""

    feature: str
    shap_value: float
    effect: str  # increases_risk | decreases_risk


class RecommendationRead(BaseModel):
    """One RULE-BASED recommendation for the operator."""

    code: str
    severity: str
    priority: int
    reason: str
    action: str
    source: str = "RULE-BASED"
    evidence: dict = Field(default_factory=dict)


class DataQualityRead(BaseModel):
    """What the assessment used, and what had to be imputed/skipped."""

    imputed_features: list[str] = Field(default_factory=list)
    notes: list[str] = Field(default_factory=list)
    readings_used: int = 0
    first_reading_at: datetime | None = None


class RiskAssessmentRead(BaseModel):
    """
    Response of GET /shipments/{shipment_id}/risk.

    Provenance: `shipment`, `exposure`, `latest_reading` and `position` are REAL
    data from PostgreSQL; `model_risk_score`, `lstm_forecast`, `anomaly`,
    `packaging` and `shap_top_factors` are MODEL OUTPUT; `risk_level`,
    `risk_score`, `rule_based_score` and `recommendations` combine model output
    with RULE-BASED formulas (see `risk_reasons`, `notes`, `disclaimer`).
    """

    # `model_*` names are intentional here (they mark MODEL OUTPUT fields), so
    # Pydantic's protected "model_" namespace is disabled for this schema.
    model_config = ConfigDict(protected_namespaces=())

    shipment_id: int
    shipment: ShipmentRead
    product: ProductRead | None = None
    assessed_at: datetime

    risk_level: str                      # LOW | MEDIUM | HIGH | CRITICAL | UNKNOWN
    risk_score: float | None = None      # 0..1 blended score (not calibrated)
    risk_percent: float | None = None    # risk_score * 100 (display only)
    risk_level_basis: str = "unknown"    # which components were available
    risk_reasons: list[str] = Field(default_factory=list)

    model_risk_score: float | None = None          # XGBoost MODEL OUTPUT
    model_decision_threshold: float | None = None
    model_flag: bool | None = None
    rule_based_score: float | None = None          # RULE-BASED OUTPUT
    score_components: dict = Field(default_factory=dict)
    thresholds: dict = Field(default_factory=dict)

    exposure: ExposureMetrics | None = None        # cumulative exposure engine
    remaining_shelf_life_hours: float | None = None
    lstm_forecast: ForecastRead | None = None
    anomaly: AnomalyRead | None = None
    packaging: PackagingRead | None = None
    shap_top_factors: list[ShapFactorRead] | None = None
    shap_status: str | None = None
    global_shap_importance: list[dict] | None = None

    recommendations: list[RecommendationRead] = Field(default_factory=list)
    latest_reading: LatestReadingRead | None = None
    position: PositionRead | None = None
    readings_used: int = 0
    model_status: list[ModelStatusRead] = Field(default_factory=list)
    data_quality: DataQualityRead | None = None
    notes: list[str] = Field(default_factory=list)
    disclaimer: str = ""


class MLStatusRead(BaseModel):
    """Response of GET /ml/status."""

    enabled: bool
    artifacts_dir: str
    available: list[str]
    unavailable: list[str]
    models: list[ModelStatusRead]


# ---------------------------------------------------------------------------
# Step 5: dashboard
# ---------------------------------------------------------------------------
class DashboardShipmentRow(BaseModel):
    """One row of the dashboard shipment table / one point on the live map."""

    model_config = ConfigDict(protected_namespaces=())

    shipment_id: int
    vehicle_id: str
    origin: str
    destination: str
    status: str
    product_id: int | None = None
    product_name: str | None = None
    product_category: str | None = None

    temperature: float | None = None
    humidity: float | None = None
    door_open: bool | None = None
    battery_level: float | None = None
    last_updated: datetime | None = None
    readings_count: int = 0

    risk_level: str = "UNKNOWN"
    risk_score: float | None = None
    model_risk_score: float | None = None
    exposure_status: str | None = None
    cumulative_excursion_minutes: float | None = None
    remaining_shelf_life_hours: float | None = None
    anomaly_status: str | None = None
    active_alerts: int = 0

    latitude: float | None = None
    longitude: float | None = None
    position_source: str | None = None
    estimated_arrival_time: datetime | None = None


class DashboardSummaryRead(BaseModel):
    """Top-level summary cards - every number is computed from live data."""

    total_shipments: int
    active_shipments: int
    high_or_critical_risk: int
    active_alerts: int
    risk_breakdown: dict[str, int] = Field(default_factory=dict)
    active_statuses: list[str] = Field(default_factory=list)
    shipments_assessed: int = 0
    generated_at: datetime
    ml_available: list[str] = Field(default_factory=list)
    ml_unavailable: list[str] = Field(default_factory=list)
    data_sources: dict = Field(default_factory=dict)
    notes: list[str] = Field(default_factory=list)


class DashboardMapRead(BaseModel):
    """Live map payload: shipments with coordinates, origins/destinations noted."""

    generated_at: datetime
    shipments: list[DashboardShipmentRow] = Field(default_factory=list)
    notes: list[str] = Field(default_factory=list)

    last_reading_at: datetime | None = None


class AlertGenerationRead(BaseModel):
    """Summary of one alert-evaluation pass."""

    shipment_id: int
    evaluated: int
    created: int
    suppressed: int
    suppressed_types: list[str] = Field(default_factory=list)
    alerts: list[AlertRead] = Field(default_factory=list)


class ChatRequest(BaseModel):
    """POST /chat body. shipment_id is optional; when set, risk context is attached."""

    message: str = Field(..., min_length=1, max_length=4000)
    shipment_id: int | None = None


class ChatResponse(BaseModel):
    """POST /chat reply. `source` is openai or fallback (never the API key)."""

    reply: str
    shipment_id: int | None = None
    source: str = "fallback"

