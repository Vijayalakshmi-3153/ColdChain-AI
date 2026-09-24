"""Past-only ML feature engineering. Reuses backend compute_exposure (shared logic, no duplication)."""
import sys
from pathlib import Path
from types import SimpleNamespace

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "backend"))
from app.services.exposure import compute_exposure  # noqa: E402

ID_COLUMNS = ["timestamp", "shipment_id", "batch_id", "product_id", "product_name",
              "origin", "destination", "latitude", "longitude", "future_discard"]


def _haversine(a_lat, a_lon, b_lat, b_lon):
    p1, p2 = np.radians(a_lat), np.radians(b_lat)
    dp, dl = np.radians(b_lat - a_lat), np.radians(b_lon - a_lon)
    h = np.sin(dp / 2) ** 2 + np.cos(p1) * np.cos(p2) * np.sin(dl / 2) ** 2
    return 2 * 6371.0 * np.arcsin(np.sqrt(h))


def _run_lengths(flags):
    out, cur = np.zeros(len(flags), int), 0
    for i, f in enumerate(flags):
        cur = cur + 1 if f else 0
        out[i] = cur
    return out


def build_features(raw: pd.DataFrame) -> pd.DataFrame:
    parts = []
    for _, grp in raw.sort_values("timestamp").groupby("shipment_id", sort=False):
        parts.append(_shipment_features(grp))
    return pd.concat(parts, ignore_index=True)


def _shipment_features(g):
    g = g.sort_values("timestamp").reset_index(drop=True)
    p = SimpleNamespace(
        minimum_temperature=g.minimum_temperature.iloc[0],
        maximum_temperature=g.maximum_temperature.iloc[0],
        shelf_life_hours=g.shelf_life_hours.iloc[0], q10=g.q10.iloc[0],
        maximum_allowed_excursion_minutes=g.maximum_allowed_excursion_minutes.iloc[0])
    readings = [SimpleNamespace(timestamp=t, temperature=c)
                for t, c in zip(g.timestamp, g.temperature)]
    # Cumulative exposure from the BACKEND engine, applied to past-only prefixes.
    prefixes = [compute_exposure(p, readings[:i + 1]) for i in range(len(readings))]
    out = g.copy()
    for col in ["total_excursion_minutes", "degree_minutes_outside_range",
                "equivalent_age_hours", "remaining_shelf_life_hours",
                "percent_readings_outside_range"]:
        out[col] = [x[col] for x in prefixes]
    out["observed_max_temperature"] = [x["max_temperature"] for x in prefixes]
    out["observed_min_temperature"] = [x["min_temperature"] for x in prefixes]
    lo, hi = p.minimum_temperature, p.maximum_temperature
    t = out.temperature.to_numpy()
    out["temperature_above_max"] = np.maximum(t - hi, 0.0)
    out["temperature_below_min"] = np.maximum(lo - t, 0.0)
    out["temperature_diff_mid"] = t - (lo + hi) / 2.0
    out["excursion_run_minutes"] = _run_lengths((t < lo) | (t > hi)) * 15.0
    out["door_opens_so_far"] = out.door_open.cumsum().astype(int)
    for w in (4, 12):  # rolling stats over past+current rows only
        out[f"temp_mean_{w}"] = out.temperature.rolling(w, min_periods=1).mean()
        out[f"temp_std_{w}"] = out.temperature.rolling(w, min_periods=1).std().fillna(0.0)
        out[f"hum_mean_{w}"] = out.humidity.rolling(w, min_periods=1).mean()
    lat, lon = out.latitude.to_numpy(), out.longitude.to_numpy()
    step = np.zeros(len(out))
    step[1:] = _haversine(lat[:-1], lon[:-1], lat[1:], lon[1:])
    out["distance_km_so_far"] = np.cumsum(step)
    ts = pd.to_datetime(out.timestamp)
    out["hour_sin"] = np.sin(2 * np.pi * ts.dt.hour / 24.0)
    out["hour_cos"] = np.cos(2 * np.pi * ts.dt.hour / 24.0)
    out["reading_index"] = np.arange(len(out))
    return out


def feature_columns(df):
    skip = set(ID_COLUMNS)
    return [c for c in df.columns if c not in skip
            and pd.api.types.is_numeric_dtype(df[c])]


def future_discard_target(df, horizon=24):
    """Label =1 if the discard/spoil event happens AFTER row t and within `horizon`
    readings. Future data is used ONLY to build the label, never a feature."""
    y = pd.Series(0, index=df.index, dtype=int)
    for _, grp in df.sort_values("timestamp").groupby("shipment_id", sort=False):
        idx = grp.index.to_numpy()
        hits = np.where(grp.total_excursion_minutes.to_numpy()
                        > grp.maximum_allowed_excursion_minutes.iloc[0])[0]
        if len(hits):
            ev = hits[0]
            y.loc[idx[max(0, ev - horizon):ev]] = 1
    return y
