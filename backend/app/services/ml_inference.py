"""
ML serving / inference layer for ColdChain AI (Phase A, Step 5).

Loads the Step 4 artifacts from `ml/artifacts/` and turns live PostgreSQL
telemetry into model outputs. This module NEVER trains anything and NEVER
invents a prediction: when an artifact is missing, or the available telemetry
is not sufficient, it returns an explicit `unavailable` /
`insufficient_data` status.

Artifacts (produced by Step 4 - see ml/README.md):
  * xgboost_spoilage.ubj + xgboost_features.json            spoilage-risk model
  * lstm_forecast.keras + lstm_scaler.pkl + lstm_meta.json  forecasting
  * autoencoder.keras + autoencoder_meta.pkl/json           anomaly detection
  * cnn_packaging.keras + cnn_meta.json                     packaging condition
  * shap_importance.json / shap_explanations.json           SHAP outputs

Data provenance used throughout Step 5
--------------------------------------
REAL data          -> telemetry rows read from PostgreSQL
MODEL OUTPUT       -> XGBoost / LSTM / Autoencoder / CNN predictions plus the
                      SHAP attributions of the XGBoost prediction
RULE-BASED OUTPUT  -> services/risk.py, recommendations.py, alerts.py
SYNTHETIC/DEMO     -> only the *training* data behind the artifacts; each
                      artifact's `data_kind` is passed through to the API
                      responses so nothing looks like real-world validation.

Feature preparation reuses Step 4 logic:
  * `ml.utils.features` (past-only features + the shared exposure engine)
  * `ml.utils.common`   (sliding windows, scaler/artifact loaders)
  * `ml.training.train_autoencoder` (identical AE channel scaling)
"""

from __future__ import annotations

import io
import math
import sys
import threading
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from pathlib import Path
from types import SimpleNamespace
from typing import Any, Iterable, Sequence

import numpy as np

from ..config import get_settings

# E:\AI-final\backend\app\services\ml_inference.py -> E:\AI-final
PROJECT_ROOT = Path(__file__).resolve().parents[2]

# The ML package lives at the project root; make it importable when the
# backend is started from `backend/` (e.g. uvicorn app.main:app).
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

settings = get_settings()

DEFAULT_ARTIFACTS_DIR = PROJECT_ROOT.parent / "ml" / "artifacts"

# Artifact files per model group. Missing files are reported, never faked.
ARTIFACT_FILES: dict[str, tuple[str, ...]] = {
    "xgboost": ("xgboost_spoilage.ubj", "xgboost_features.json"),
    "lstm": ("lstm_forecast.keras", "lstm_scaler.pkl", "lstm_meta.json"),
    "autoencoder": ("autoencoder.keras", "autoencoder_meta.json", "autoencoder_meta.pkl"),
    "cnn": ("cnn_packaging.keras", "cnn_meta.json"),
    "shap": ("shap_importance.json",),
}

# Metadata file per model group (readable without loading the model).
META_FILES = {
    "xgboost": "xgboost_features.json",
    "lstm": "lstm_meta.json",
    "autoencoder": "autoencoder_meta.json",
    "cnn": "cnn_meta.json",
    "shap": "shap_importance.json",
}

# Model groups that need TensorFlow/Keras (loaded lazily by default).
KERAS_MODELS = ("lstm", "autoencoder", "cnn")

# Rolling windows used by ml/utils/features.py.
FEATURE_WINDOWS = (4, 12)


def _imputation_default(feature: str) -> float:
    """
    Documented fallback for a feature the live system cannot supply.

    Only `route_distance_km` is expected here: the XGBoost feature set
    contains the planned route length, but the PostgreSQL schema has no such
    column (documented limitation, deferred to a later step).
    """
    if feature == "route_distance_km":
        return float(settings.ml_route_distance_default_km)
    return 0.0


@dataclass
class ModelStatus:
    """Availability of one model / artifact group."""

    name: str
    kind: str
    path: str
    available: bool = False
    loaded: bool = False
    detail: str = ""
    data_kind: str | None = None

    def as_dict(self) -> dict[str, Any]:
        return {
            "name": self.name,
            "kind": self.kind,
            "available": self.available,
            "loaded": self.loaded,
            "path": self.path,
            "detail": self.detail,
            "data_kind": self.data_kind,
        }

class MLRegistry:
    """
    Thread-safe, lazy artifact loader.

    * `load_lightweight()` runs at application startup: it records artifact
      availability and loads the small XGBoost booster plus every metadata
      file.
    * Keras models (LSTM, autoencoder, CNN) are cached on first use unless
      `ML_PRELOAD_KERAS_MODELS=true`, keeping startup fast.
    * Failures are captured in `ModelStatus.detail` and surfaced through the
      API instead of raising or fabricating a value.
    """

    def __init__(self, artifacts_dir: Path | str | None = None) -> None:
        if artifacts_dir is None:
            artifacts_dir = settings.ml_artifacts_dir or DEFAULT_ARTIFACTS_DIR
        self.artifacts_dir = Path(artifacts_dir)
        self._lock = threading.RLock()
        self._models: dict[str, Any] = {}
        self._meta: dict[str, dict] = {}
        self._status: dict[str, ModelStatus] = {
            "xgboost": ModelStatus("xgboost", "xgboost booster", str(self.artifacts_dir / "xgboost_spoilage.ubj")),
            "lstm": ModelStatus("lstm", "keras lstm", str(self.artifacts_dir / "lstm_forecast.keras")),
            "autoencoder": ModelStatus("autoencoder", "keras autoencoder", str(self.artifacts_dir / "autoencoder.keras")),
            "cnn": ModelStatus("cnn", "keras cnn", str(self.artifacts_dir / "cnn_packaging.keras")),
            "shap": ModelStatus("shap", "shap metadata", str(self.artifacts_dir / "shap_importance.json")),
        }

    # -------------------------------------------------------------- paths
    def artifact_path(self, filename: str) -> Path:
        return self.artifacts_dir / filename

    def files_present(self, name: str) -> tuple[bool, list[str]]:
        """Return (all_present, missing_files) for one model group."""
        missing = [f for f in ARTIFACT_FILES[name] if not self.artifact_path(f).exists()]
        return (not missing, missing)

    # ------------------------------------------------------------- status
    def status(self) -> dict[str, ModelStatus]:
        with self._lock:
            return dict(self._status)

    def summary(self) -> dict[str, Any]:
        """Compact status block used by /health and /ml/status."""
        models = {name: st.as_dict() for name, st in self.status().items()}
        return {
            "enabled": bool(settings.ml_enabled),
            "artifacts_dir": str(self.artifacts_dir),
            "models": models,
            "available": sorted(name for name, st in models.items() if st["available"]),
            "unavailable": sorted(name for name, st in models.items() if not st["available"]),
        }

    # --------------------------------------------------------- load logic
    def _read_json(self, filename: str) -> dict:
        from ml.utils.common import load_json

        return load_json(self.artifact_path(filename))

    def _load_keras(self, filename: str):
        from tensorflow import keras  # heavy import: only on first use

        return keras.models.load_model(str(self.artifact_path(filename)))

    def _load_group(self, name: str) -> bool:
        """Load every artifact file for `name`. Returns True on success."""
        if not settings.ml_enabled:
            with self._lock:
                self._status[name].available = False
                self._status[name].detail = "ML disabled via ML_ENABLED=false"
            return False

        with self._lock:
            if name in self._models:
                return self._models[name] is not None
            present, missing = self.files_present(name)
            if not present:
                self._status[name].available = False
                self._status[name].detail = f"missing artifact file(s): {', '.join(missing)}"
                print(f"[ml] {name}: {self._status[name].detail} -> reported as unavailable")
                return False
            try:
                model = self._instantiate(name)
                detail = "loaded"
            except Exception as exc:  # noqa: BLE001 - report, never crash the API
                model = None
                detail = f"failed to load artifact: {exc}"
                print(f"[ml] {name}: could not load artifact - {exc}")
            self._models[name] = model
            st = self._status[name]
            st.loaded = model is not None
            st.available = model is not None
            st.detail = detail
            return model is not None
    # -------------------------------------------------------- accessors
    def meta(self, name: str) -> dict | None:
        """
        Metadata for a model group (None when the artifact is missing).

        Metadata is what tells us *which* feature list / window length a model
        expects, so it must be readable even when the model cannot be loaded.
        """
        if name == "xgboost":
            with self._lock:
                if "xgboost" in self._meta:
                    return self._meta["xgboost"]
            if not self.artifact_path("xgboost_features.json").exists():
                return None
            try:
                meta = self._read_json("xgboost_features.json")
            except Exception as exc:  # noqa: BLE001
                print(f"[ml] xgboost metadata unreadable: {exc}")
                return None
            with self._lock:
                self._meta["xgboost"] = meta
                self._status["xgboost"].data_kind = meta.get("data_kind")
            return meta

        filename = META_FILES.get(name)
        if filename is None:
            return None
        with self._lock:
            if name in self._meta:
                return self._meta[name]
        if not self.artifact_path(filename).exists():
            return None
        try:
            meta = self._read_json(filename)
        except Exception as exc:  # noqa: BLE001
            print(f"[ml] {name} metadata unreadable: {exc}")
            return None
        with self._lock:
            self._meta[name] = meta
            self._status[name].data_kind = meta.get("data_kind")
        return meta

    def _model(self, name: str):
        with self._lock:
            if name in self._models:
                return self._models[name]
        self._load_group(name)
        with self._lock:
            return self._models.get(name)

    def xgboost_model(self):
        return self._model("xgboost")

    def lstm_model(self):
        return self._model("lstm")

    def autoencoder_model(self):
        return self._model("autoencoder")

    def cnn_model(self):
        return self._model("cnn")

    def lstm_scaler(self):
        """Train-only StandardScaler shipped with the LSTM artifacts."""
        if self._model("lstm") is None:
            return None
        with self._lock:
            return self._meta.get("lstm_scaler")

    # ------------------------------------------------------------- loading
    def _instantiate(self, name: str) -> Any:
        """Load one model group from disk (never trains, never downloads)."""
        if name == "xgboost":
            import xgboost as xgb

            meta = self.meta("xgboost") or {}
            model = xgb.XGBClassifier()
            model.load_model(str(self.artifact_path("xgboost_spoilage.ubj")))
            self._status["xgboost"].data_kind = meta.get("data_kind")
            return model

        if name == "lstm":
            from ml.utils.common import load_pickle

            meta = self._read_json("lstm_meta.json")
            scaler = load_pickle(self.artifact_path("lstm_scaler.pkl"))
            self._meta["lstm"] = meta
            self._meta["lstm_scaler"] = scaler
            model = self._load_keras("lstm_forecast.keras")
            self._status["lstm"].data_kind = meta.get("data_kind")
            return model

        if name == "autoencoder":
            from ml.utils.common import load_pickle

            meta = self._read_json("autoencoder_meta.json")
            scaler = load_pickle(self.artifact_path("autoencoder_meta.pkl"))
            self._meta["autoencoder"] = meta
            self._meta["autoencoder_scaler"] = scaler
            model = self._load_keras("autoencoder.keras")
            self._status["autoencoder"].data_kind = meta.get("data_kind")
            return model

        if name == "cnn":
            meta = self._read_json("cnn_meta.json")
            self._meta["cnn"] = meta
            model = self._load_keras("cnn_packaging.keras")
            self._status["cnn"].data_kind = meta.get("data_kind")
            return model

        if name == "shap":
            meta = self._read_json("shap_importance.json")
            self._meta["shap"] = meta
            self._status["shap"].data_kind = meta.get("data_kind")
            return meta

        raise KeyError(f"unknown model group: {name}")

    # --------------------------------------------------- startup helper
    def load_lightweight(self) -> dict[str, Any]:
        """
        Startup entry point: record artifact availability, load the small
        XGBoost booster + metadata, and keep the Keras models lazy (or preload
        them when ML_PRELOAD_KERAS_MODELS=true).
        """
        if not settings.ml_enabled:
            for st in self._status.values():
                st.available = False
                st.loaded = False
                st.detail = "ML disabled via ML_ENABLED=false"
            print("[ml] disabled via ML_ENABLED=false - risk endpoints report unavailable models")
            return self.summary()

        print(f"[ml] artifacts dir: {self.artifacts_dir}")
        for name in ("xgboost", "lstm", "autoencoder", "cnn", "shap"):
            present, missing = self.files_present(name)
            st = self._status[name]
            if present:
                st.available = True
                st.detail = "artifact file(s) present; model loads on first use (cached)"
            else:
                st.available = False
                st.detail = f"missing artifact file(s): {', '.join(missing)}"
                print(f"[ml] {name}: missing -> {', '.join(missing)}")

        for name in ("xgboost", "shap"):
            if self._status[name].available:
                self._load_group(name)

        if settings.ml_preload_keras_models:
            for name in KERAS_MODELS:
                if self._status[name].available:
                    self._load_group(name)
            print("[ml] Keras models preloaded (ML_PRELOAD_KERAS_MODELS=true)")

        for name in KERAS_MODELS:
            meta = self.meta(name)
            if meta:
                self._status[name].data_kind = meta.get("data_kind")

        summary = self.summary()
        print(f"[ml] available: {summary['available'] or 'none'} | unavailable: {summary['unavailable'] or 'none'}")
        return summary


# Single shared registry used by the FastAPI app and the services.
registry = MLRegistry()


def configure_registry(artifacts_dir: Path | str, *, lightweight: bool = True) -> MLRegistry:
    """
    Point the global registry at another artifacts folder (used by tests).

    Only the *loader* is swapped: no model is trained and no artifact is
    modified.
    """
    global registry
    registry = MLRegistry(artifacts_dir)
    if lightweight:
        registry.load_lightweight()
    return registry
# ---------------------------------------------------------------------------
# Feature preparation (past-only, same maths as the Step 4 training features)
# ---------------------------------------------------------------------------
def naive_utc(dt: datetime | None) -> datetime:
    """Normalize a datetime to naive UTC so values can be compared/sorted."""
    if dt is None:
        return datetime.min
    if dt.tzinfo is not None:
        return dt.astimezone(timezone.utc).replace(tzinfo=None)
    return dt


def reading_objects(readings: Iterable) -> list[SimpleNamespace]:
    """Normalize ORM rows / objects into simple objects sorted by timestamp."""
    items = [
        SimpleNamespace(
            timestamp=r.timestamp,
            temperature=float(r.temperature),
            humidity=float(getattr(r, "humidity")) if getattr(r, "humidity", None) is not None else float("nan"),
            latitude=getattr(r, "latitude", None),
            longitude=getattr(r, "longitude", None),
            door_open=bool(getattr(r, "door_open", False)),
            battery_level=getattr(r, "battery_level", None),
        )
        for r in readings
    ]
    items.sort(key=lambda r: naive_utc(r.timestamp))
    return items


def product_stub(product) -> SimpleNamespace:
    """Minimal product view (the exposure engine needs exactly these fields)."""
    return SimpleNamespace(
        minimum_temperature=float(product.minimum_temperature),
        maximum_temperature=float(product.maximum_temperature),
        shelf_life_hours=float(product.shelf_life_hours),
        q10=float(product.q10),
        maximum_allowed_excursion_minutes=float(product.maximum_allowed_excursion_minutes),
        minimum_humidity=float(getattr(product, "minimum_humidity", 0.0)),
        maximum_humidity=float(getattr(product, "maximum_humidity", 100.0)),
    )


def _distance_so_far(rows: Sequence[SimpleNamespace]) -> float:
    """Cumulative haversine distance over the readings (as in features.py)."""
    from ml.utils.features import _haversine

    total = 0.0
    previous: tuple[float, float] | None = None
    for row in rows:
        if row.latitude is None or row.longitude is None:
            continue
        if previous is not None:
            total += float(_haversine(previous[0], previous[1], float(row.latitude), float(row.longitude)))
        previous = (float(row.latitude), float(row.longitude))
    return total


def latest_feature_row(readings: Sequence[SimpleNamespace], product) -> tuple[dict[str, float], dict[str, Any]]:
    """
    Build the engineered feature row for the MOST RECENT reading.

    Reuses the Step 4 logic:
      * `ml.utils.features._run_lengths` / `_haversine` (identical maths)
      * the shared exposure engine `backend.app.services.exposure.compute_exposure`
        (the same function `ml.utils.features` uses) for the cumulative
        features.

    `ml.utils.features.build_features()` loops over every prefix of a shipment
    (O(n^2)) - fine for the 96-reading training batches, too slow for long
    live histories. Because `compute_exposure` is cumulative, its value over
    the full history equals its value on the last prefix, so the same last-row
    vector is produced here in O(n).
    `backend/tests/test_ml_inference.py` asserts both implementations agree.

    Returns (features, data_quality). `data_quality` lists every feature that
    had to be imputed, so a consumer can tell model input from real data.
    """
    from ml.utils.features import _run_lengths  # reuse the exact helper

    from .exposure import compute_exposure  # shared engine (also used by Step 4)

    imputed: list[str] = []
    notes: list[str] = []
    rows = list(readings)

    if not rows:
        return {}, {
            "imputed_features": [],
            "notes": ["no telemetry available for this shipment"],
            "readings_used": 0,
            "first_reading_at": None,
            "last_reading_at": None,
        }

    p = product_stub(product)
    temperatures = np.asarray([r.temperature for r in rows], dtype=float)
    humidity = np.asarray([r.humidity for r in rows], dtype=float)
    door = np.asarray([bool(r.door_open) for r in rows])
    timestamps = [r.timestamp for r in rows]

    metrics = compute_exposure(p, rows)  # cumulative values == last prefix

    last_temp = float(temperatures[-1])
    lo, hi = p.minimum_temperature, p.maximum_temperature
    mid = (lo + hi) / 2.0

    features: dict[str, float] = {
        "minimum_temperature": lo,
        "maximum_temperature": hi,
        "shelf_life_hours": p.shelf_life_hours,
        "q10": p.q10,
        "maximum_allowed_excursion_minutes": p.maximum_allowed_excursion_minutes,
        "temperature": last_temp,
        "humidity": float(humidity[-1]) if math.isfinite(humidity[-1]) else 0.0,
        "door_open": float(bool(door[-1])),
        "battery_level": float(rows[-1].battery_level) if rows[-1].battery_level is not None else 0.0,
        "total_excursion_minutes": float(metrics["total_excursion_minutes"]),
        "degree_minutes_outside_range": float(metrics["degree_minutes_outside_range"]),
        "equivalent_age_hours": float(metrics["equivalent_age_hours"]),
        "remaining_shelf_life_hours": float(metrics["remaining_shelf_life_hours"]),
        "percent_readings_outside_range": float(metrics["percent_readings_outside_range"]),
        "observed_max_temperature": float(metrics["max_temperature"]),
        "observed_min_temperature": float(metrics["min_temperature"]),
        "temperature_above_max": max(last_temp - hi, 0.0),
        "temperature_below_min": max(lo - last_temp, 0.0),
        "temperature_diff_mid": last_temp - mid,
        # features.py assumes 15-minute readings for this run-length feature;
        # the same constant is used here so the model input stays consistent
        # with how it was trained (documented limitation for faster ticks).
        "excursion_run_minutes": float(_run_lengths((temperatures < lo) | (temperatures > hi))[-1]) * 15.0,
        "door_opens_so_far": float(door.cumsum()[-1]),
        "distance_km_so_far": _distance_so_far(rows),
        "hour_sin": math.sin(2 * math.pi * naive_utc(timestamps[-1]).hour / 24.0),
        "hour_cos": math.cos(2 * math.pi * naive_utc(timestamps[-1]).hour / 24.0),
        "reading_index": float(len(rows) - 1),
    }

    for window_size in FEATURE_WINDOWS:
        window = temperatures[-window_size:]
        features[f"temp_mean_{window_size}"] = float(np.mean(window))
        std = float(np.std(window, ddof=1)) if len(window) > 1 else 0.0
        features[f"temp_std_{window_size}"] = std if math.isfinite(std) else 0.0
        hum = humidity[-window_size:]
        hum = hum[np.isfinite(hum)]
        features[f"hum_mean_{window_size}"] = float(np.mean(hum)) if len(hum) else 0.0

    if rows[-1].battery_level is None:
        imputed.append("battery_level")
        notes.append("latest reading has no battery_level; 0.0 used for the model input")
    if not math.isfinite(humidity[-1]):
        imputed.append("humidity")
        notes.append("latest reading has no humidity; 0.0 used for the model input")

    # The live DB has no planned-route-distance column -> documented default.
    features["route_distance_km"] = _imputation_default("route_distance_km")
    imputed.append("route_distance_km")
    notes.append(
        "route_distance_km is not stored in PostgreSQL; imputed with the documented default "
        f"{settings.ml_route_distance_default_km} km (median of the SYNTHETIC/DEMO training data)"
    )

    quality = {
        "imputed_features": sorted(set(imputed)),
        "notes": notes,
        "readings_used": len(rows),
        "first_reading_at": _iso(timestamps[0]),
        "last_reading_at": _iso(timestamps[-1]),
    }
    return features, quality


def _iso(value) -> str | None:
    """isoformat helper that tolerates non-datetime values."""
    if value is None:
        return None
    return value.isoformat() if hasattr(value, "isoformat") else str(value)
# ---------------------------------------------------------------------------
# MODEL OUTPUT: XGBoost spoilage risk + SHAP explanation
# ---------------------------------------------------------------------------
def _feature_vector(features: dict[str, float], feature_names: Sequence[str]) -> tuple[np.ndarray, list[str]]:
    """Ordered float32 vector + the names of features that had to be imputed."""
    values: list[float] = []
    imputed: list[str] = []
    for name in feature_names:
        value = features.get(name)
        if value is None or not isinstance(value, (int, float)) or not math.isfinite(float(value)):
            values.append(_imputation_default(name))
            imputed.append(name)
        else:
            values.append(float(value))
    return np.asarray([values], dtype=np.float32), imputed


def predict_spoilage_risk(features: dict[str, float]) -> dict[str, Any]:
    """
    MODEL OUTPUT: XGBoost spoilage-risk score for one feature row.

    The value is the model's `predict_proba` output. It is NOT calibrated, so
    it is reported as a *risk score* (0..1) - never as a real-world
    probability - and `flag` simply compares it with the decision threshold
    that Step 4 tuned on the validation split.
    """
    model = registry.xgboost_model()
    meta = registry.meta("xgboost")
    if model is None or not meta:
        return {
            "status": "unavailable",
            "model": "xgboost_spoilage",
            "risk_score": None,
            "detail": registry.status()["xgboost"].detail or "XGBoost artifact unavailable",
        }

    feature_names = meta.get("features", [])
    X, imputed = _feature_vector(features, feature_names)
    try:
        score = float(model.predict_proba(X)[0, 1])
    except Exception as exc:  # noqa: BLE001
        return {"status": "error", "model": "xgboost_spoilage", "risk_score": None,
                "detail": f"inference failed: {exc}"}

    threshold = float(meta.get("threshold", settings.risk_model_decision_threshold))
    return {
        "status": "ok",
        "model": "xgboost_spoilage",
        "risk_score": round(score, 6),
        "decision_threshold": round(threshold, 6),
        "flag": bool(score >= threshold),
        "n_features": len(feature_names),
        "imputed_features": imputed,
        "data_kind": meta.get("data_kind", "SYNTHETIC/DEMO"),
        "test_metrics": meta.get("test_metrics"),
        "detail": None,
    }


def explain_prediction(features: dict[str, float], top: int = 8) -> dict[str, Any]:
    """MODEL OUTPUT: SHAP top contributing factors for the current feature row."""
    if not settings.ml_shap_enabled:
        return {"status": "disabled", "top_factors": None, "base_value": None,
                "detail": "SHAP disabled via ML_SHAP_ENABLED=false"}
    if not registry.status()["xgboost"].available:
        return {"status": "unavailable", "top_factors": None, "base_value": None,
                "detail": registry.status()["xgboost"].detail}

    model = registry.xgboost_model()
    meta = registry.meta("xgboost")
    if model is None or not meta:
        return {"status": "unavailable", "top_factors": None, "base_value": None,
                "detail": registry.status()["xgboost"].detail}
    feature_names = meta.get("features", [])
    X, _ = _feature_vector(features, feature_names)
    try:
        import shap

        from ml.training.explain_xgboost import contributions, shap_values

        row = np.asarray(shap_values(model, X))[0]
        base = float(np.asarray(shap.TreeExplainer(model).expected_value).ravel()[0])
        factors = contributions(row, feature_names, top=top)
    except Exception as exc:  # noqa: BLE001
        return {"status": "error", "top_factors": None, "base_value": None,
                "detail": f"SHAP explanation failed: {exc}"}

    return {
        "status": "ok",
        "top_factors": factors,
        "base_value": round(base, 6),
        "detail": "SHAP attributes the XGBoost Model Output (log-odds space) to individual features.",
    }


def global_importance(top: int = 10) -> list[dict] | None:
    """MODEL OUTPUT: pre-computed global SHAP importance from Step 4 artifacts."""
    meta = registry.meta("shap")
    if not meta:
        return None
    importance = meta.get("importance") or []
    return importance[:top] if importance else None
# ---------------------------------------------------------------------------
# MODEL OUTPUT: LSTM temperature/humidity forecast
# ---------------------------------------------------------------------------
def forecast_series(
    readings: Sequence[SimpleNamespace], product, *, horizon: int | None = None
) -> dict[str, Any]:
    """
    Forecast the next `horizon` readings with the Step 4 LSTM.

    Returns `insufficient_data` when fewer than `seq_len` readings exist and
    `unavailable` when the artifact cannot be loaded - never a guess.
    Windows are built with `ml.utils.common.sliding_windows`, the same builder
    used in training, over the train-only scaler shipped with the model.
    """
    meta = registry.meta("lstm")
    result: dict[str, Any] = {
        "status": "unavailable",
        "model": "lstm",
        "detail": None,
        "seq_len": None,
        "horizon_readings": None,
        "interval_minutes": None,
        "temperature": None,
        "humidity": None,
        "timestamps": None,
        "predicted_breach": None,
    }
    if not meta or not registry.status()["lstm"].available:
        result["detail"] = registry.status()["lstm"].detail or "LSTM artifact unavailable"
        return result

    seq_len = int(meta.get("seq_len", 48))
    horizon = int(horizon or meta.get("horizon", 6))
    result["seq_len"] = seq_len
    result["horizon_readings"] = horizon

    if len(readings) < seq_len:
        return {
            **result,
            "status": "insufficient_data",
            "detail": (
                f"LSTM needs {seq_len} readings (the training window length); only "
                f"{len(readings)} are available for this shipment"
            ),
        }

    model = registry.lstm_model()
    scaler = registry.lstm_scaler()
    if model is None or scaler is None:
        result["detail"] = "LSTM model or scaler could not be loaded"
        return result

    from ml.utils.common import sliding_windows

    window = list(readings[-seq_len:])
    values = np.asarray(
        [[r.temperature, 0.0 if not math.isfinite(r.humidity) else r.humidity] for r in window],
        dtype=np.float32,
    )
    try:
        scaled = scaler.transform(values).astype(np.float32)
        X, _ = sliding_windows(scaled, seq_len, 0)
        if len(X) == 0:
            return {**result, "status": "insufficient_data", "detail": "no complete window available"}
        pred = np.asarray(model.predict(X[-1:], verbose=0), dtype=np.float32).reshape(horizon, 2)
        unscaled = scaler.inverse_transform(pred)
    except Exception as exc:  # noqa: BLE001
        return {**result, "status": "error", "detail": f"forecast failed: {exc}"}

    deltas = [
        (naive_utc(b.timestamp) - naive_utc(a.timestamp)).total_seconds() / 60.0
        for a, b in zip(window, window[1:])
    ]
    interval = float(np.median(deltas)) if deltas else 15.0
    if not math.isfinite(interval) or interval <= 0:
        interval = 15.0

    last_ts = window[-1].timestamp
    timestamps = [last_ts + timedelta(minutes=interval * (i + 1)) for i in range(horizon)]
    temperatures = [round(float(v), 4) for v in unscaled[:, 0]]
    humidities = [round(float(v), 4) for v in unscaled[:, 1]]

    lo, hi = float(product.minimum_temperature), float(product.maximum_temperature)
    breach = None
    for i, temp in enumerate(temperatures):
        if temp > hi or temp < lo:
            breach = {
                "step": i + 1,
                "minutes_ahead": round(interval * (i + 1), 2),
                "predicted_temperature": temp,
                "direction": "above_max" if temp > hi else "below_min",
                "at": _iso(timestamps[i]),
            }
            break

    return {
        **result,
        "status": "ok",
        "detail": None,
        "interval_minutes": round(interval, 3),
        "temperature": temperatures,
        "humidity": humidities,
        "timestamps": [_iso(t) for t in timestamps],
        "predicted_breach": breach,
        "test_metrics": meta.get("test_metrics"),
        "data_kind": meta.get("data_kind", "SYNTHETIC/DEMO"),
        "note": meta.get("note"),
    }
# ---------------------------------------------------------------------------
# MODEL OUTPUT: autoencoder anomaly detection
# ---------------------------------------------------------------------------
def detect_anomaly(readings: Sequence[SimpleNamespace], product) -> dict[str, Any]:
    """
    Reconstruction-error anomaly score from the Step 4 autoencoder.

    Preprocessing is identical to training: temperature scaled to a fraction
    of the product's allowed range, humidity/100, then standardized with the
    train-only statistics in `autoencoder_meta.pkl`
    (`ml/training/train_autoencoder.channel_matrix` + `anomaly_score` are
    reused directly). The decision threshold itself comes from the artifact;
    the `elevated` / `anomalous` bands below are application bands.
    """
    meta = registry.meta("autoencoder")
    result: dict[str, Any] = {
        "status": "unavailable",
        "model": "autoencoder",
        "score": None,
        "threshold": None,
        "score_ratio": None,
        "is_anomaly": None,
        "seq_len": None,
        "readings_used": None,
        "detail": None,
    }
    if not meta or not registry.status()["autoencoder"].available:
        result["detail"] = registry.status()["autoencoder"].detail or "autoencoder artifact unavailable"
        return result

    seq_len = int(meta.get("seq_len", 24))
    result["seq_len"] = seq_len
    threshold = float(meta.get("threshold"))
    result["threshold"] = round(threshold, 6)

    window = list(readings[-seq_len:])
    result["readings_used"] = len(window)
    if len(window) < seq_len:
        return {
            **result,
            "status": "insufficient_data",
            "detail": (
                f"autoencoder needs {seq_len} readings (the training window length); only "
                f"{len(window)} are available for this shipment"
            ),
        }

    model = registry.autoencoder_model()
    if model is None:
        result["detail"] = "autoencoder model could not be loaded"
        return result

    try:
        import pandas as pd

        from ml.training.train_autoencoder import anomaly_score, channel_matrix

        p = product_stub(product)
        frame = pd.DataFrame(
            {
                "minimum_temperature": [p.minimum_temperature] * len(window),
                "maximum_temperature": [p.maximum_temperature] * len(window),
                "temperature": [r.temperature for r in window],
                "humidity": [0.0 if not math.isfinite(r.humidity) else r.humidity for r in window],
            }
        )
        channels = channel_matrix(frame)
        mean = np.asarray(meta["channel_mean"], dtype=np.float32)
        std = np.asarray(meta["channel_std"], dtype=np.float32)
        scaled = ((channels - mean) / std).astype(np.float32)
        score = float(anomaly_score(model, scaled[None, ...], (1, seq_len, 2))[0])
    except Exception as exc:  # noqa: BLE001
        return {**result, "status": "error", "detail": f"anomaly scoring failed: {exc}"}

    ratio = score / threshold if threshold else None
    if ratio is None:
        status = "unknown"
    elif ratio > 1.0:
        status = "anomalous"
    elif ratio > 0.5:
        status = "elevated"
    else:
        status = "normal"

    return {
        **result,
        "status": status,
        "score": round(score, 6),
        "score_ratio": round(ratio, 4) if ratio is not None else None,
        "is_anomaly": bool(ratio is not None and ratio > 1.0),
        "detail": None,
        "bands": {"elevated_ratio": 0.5, "anomalous_ratio": 1.0},
        "data_kind": meta.get("data_kind", "SYNTHETIC/DEMO"),
        "note": meta.get("note"),
    }
# ---------------------------------------------------------------------------
# MODEL OUTPUT: CNN packaging-condition classification
# ---------------------------------------------------------------------------
def classify_packaging(image_bytes: bytes) -> dict[str, Any]:
    """
    Classify one packaging image with the Step 4 CNN.

    Preprocessing matches training (RGB, `image_size` x `image_size`, /255 -
    the same steps as `ml/training/train_cnn.preprocess_image`). Step 4 only
    had DEMO/SYNTHETIC images, so the response carries that caveat.
    """
    meta = registry.meta("cnn")
    result: dict[str, Any] = {
        "status": "unavailable",
        "model": "cnn_packaging",
        "predicted_class": None,
        "confidence": None,
        "probabilities": None,
        "classes": None,
        "detail": None,
        "data_kind": None,
    }
    if not meta or not registry.status()["cnn"].available:
        result["detail"] = registry.status()["cnn"].detail or "CNN artifact unavailable"
        return result

    model = registry.cnn_model()
    if model is None:
        result["detail"] = "CNN model could not be loaded"
        return result

    size = int(meta.get("image_size", 96))
    classes = list(meta.get("classes", []))
    try:
        from PIL import Image

        with Image.open(io.BytesIO(image_bytes)) as image:
            array = np.asarray(image.convert("RGB").resize((size, size)), dtype=np.float32) / 255.0
        probabilities = np.asarray(model.predict(array[None, ...], verbose=0), dtype=np.float32).ravel()
    except Exception as exc:  # noqa: BLE001
        return {**result, "status": "error", "detail": f"packaging classification failed: {exc}"}

    index = int(np.argmax(probabilities))
    return {
        **result,
        "status": "ok",
        "predicted_class": classes[index] if index < len(classes) else str(index),
        "confidence": round(float(probabilities[index]), 6),
        "probabilities": {c: round(float(p), 6) for c, p in zip(classes, probabilities)},
        "classes": classes,
        "detail": None,
        "data_kind": meta.get("data_kind"),
        "note": meta.get("note"),
    }


def packaging_no_data() -> dict[str, Any]:
    """Explicit `no_data` block used when a shipment has no packaging image."""
    return {
        "status": "no_data",
        "model": "cnn_packaging",
        "predicted_class": None,
        "confidence": None,
        "probabilities": None,
        "classes": None,
        "detail": (
            "No packaging image/inspection record is stored for this shipment "
            "(object storage is planned for a later step), so no CNN packaging "
            "condition is reported."
        ),
        "data_kind": None,
    }
