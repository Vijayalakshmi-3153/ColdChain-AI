"""Tests for Step 4 ML: features/leakage, split, XGB matrices, LSTM windows,
AE inference, CNN image preprocessing, artifact round-trip, SHAP."""
import sys
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

from ml.training import explain_xgboost as sx          # noqa: E402
from ml.training import train_cnn as cnn               # noqa: E402
from ml.utils import common, features                  # noqa: E402


def raw_frame(n_ship=3, n=40, seed=0):
    """Small deterministic telemetry frame (one excursion per ship 1..n-1)."""
    rng = np.random.default_rng(seed)
    rows = []
    for s in range(n_ship):
        lo, hi = 2.0, 6.0
        base = dict(shipment_id=s, batch_id=f"b{s}", product_id=1,
                    product_name="Fresh Milk", origin="A", destination="B",
                    route_distance_km=100.0, minimum_temperature=lo,
                    maximum_temperature=hi, shelf_life_hours=48.0, q10=2.5,
                    maximum_allowed_excursion_minutes=30.0, battery_level=99.0)
        start = pd.Timestamp("2026-01-01") + pd.Timedelta(days=s)
        for i in range(n):
            temp = 4.0 + rng.normal(0, 0.3)
            if s > 0 and i >= n - 8:          # late excursion -> spoil event
                temp = 9.0 + i * 0.1
            rows.append({**base, "timestamp": start + pd.Timedelta(minutes=15 * i),
                         "temperature": float(temp), "humidity": float(50 + rng.normal(0, 3)),
                         "door_open": int(rng.random() < 0.1),
                         "battery_level": 99.0 - i * 0.05,
                         "latitude": 12.9 + 0.001 * i, "longitude": 77.5 + 0.001 * i})
    return pd.DataFrame(rows)


def test_features_no_future_leak():
    """Changing the FUTURE of a shipment must not change its earlier features."""
    df = raw_frame()
    a = features.build_features(df)
    cut = pd.Timestamp("2026-01-01") + pd.Timedelta(minutes=15 * 20)
    df2 = df.copy()
    df2.loc[df2.timestamp >= cut, "temperature"] += 50.0
    b = features.build_features(df2)
    cols = ["total_excursion_minutes", "degree_minutes_outside_range",
            "temperature_above_max", "temp_mean_4", "remaining_shelf_life_hours"]
    first = a.shipment_id == 0
    n_before = int((a.loc[first, "timestamp"] < cut).sum())
    pd.testing.assert_frame_equal(a.loc[first, cols].iloc[:n_before],
                                  b.loc[b.shipment_id == 0, cols].iloc[:n_before],
                                  check_exact=False, rtol=1e-6, atol=1e-6)


def test_label_uses_future_only_for_label():
    df = raw_frame()
    fx = features.build_features(df)
    y = features.future_discard_target(fx, horizon=8)
    assert set(np.unique(y)) <= {0, 1} and y.sum() > 0, "expected some positives"


def test_chronological_split_no_group_overlap():
    df = features.build_features(raw_frame(n_ship=20))
    parts = common.group_chronological_split(df)
    ids = {k: set(v.shipment_id) for k, v in parts.items()}
    assert not (ids["train"] & ids["val"]) and not (ids["train"] & ids["test"])
    assert not (ids["val"] & ids["test"])
    start = df.groupby("shipment_id").timestamp.min()
    assert start[list(ids["train"])].max() <= start[list(ids["val"])].min()
    assert start[list(ids["val"])].max() <= start[list(ids["test"])].min()
    assert all(v.timestamp.is_monotonic_increasing for v in parts.values())


def test_xgb_preprocessing_matrix_ok():
    df = features.build_features(raw_frame())
    parts = common.group_chronological_split(df, ratios=(0.5, 0.25, 0.25))
    feats = features.feature_columns(parts["train"])
    mats = common.fit_matrices(parts["train"], parts["val"], parts["test"], feats)
    for X in mats:
        assert X.dtype == np.float32 and np.isfinite(X).all()
        assert X.shape[1] == len(feats)


def test_binary_metrics_and_threshold():
    y = np.array([0, 0, 0, 1, 1, 0, 1, 0])
    p = np.array([0.1, 0.2, 0.6, 0.7, 0.9, 0.4, 0.8, 0.2])
    m = common.binary_metrics(y, p, threshold=0.5)
    # threshold 0.5 -> predictions [0,0,1,1,1,0,1,0] -> TN=4 FP=1 FN=0 TP=3
    assert m["n"] == 8 and m["confusion_matrix"] == [[4, 1], [0, 3]]
    assert m["precision"] == pytest.approx(3 / 4) and m["recall"] == 1.0
    th = common.best_f1_threshold(y, p)
    assert 0.05 <= th <= 0.95


def test_sliding_windows_order_and_content():
    v = np.arange(20, dtype=np.float32).reshape(10, 2)
    X, Y = common.sliding_windows(v, seq_len=4, horizon=2)
    assert X.shape == (5, 4, 2) and Y.shape == (5, 2, 2)
    np.testing.assert_array_equal(X[0], v[0:4])
    np.testing.assert_array_equal(Y[0], v[4:6])
    np.testing.assert_array_equal(X[1], v[1:5])   # chronological step by 1
    np.testing.assert_array_equal(X[1][:-1], X[0][1:])  # consecutive overlap


def test_reconstruction_error_and_is_anomaly():
    class Zero:
        def predict(self, x, verbose=0):
            return np.zeros_like(x)

    class Identity:
        def predict(self, x, verbose=0):
            return x

    x = np.ones((4, 8), dtype=np.float32)
    err = common.reconstruction_error(Zero(), x)
    assert np.allclose(err, 1.0)
    assert common.is_anomaly(Zero(), x, 0.5).all()
    assert np.allclose(common.reconstruction_error(Identity(), x), 0.0)
    assert not common.is_anomaly(Identity(), x, 0.5).any()


def test_cnn_image_preprocessing(tmp_path):
    root = cnn.generate_demo_images(n_train=2, n_val=1, root=tmp_path / "img")
    paths = sorted((root / "train" / "ok").glob("*.png"))
    assert paths, "demo image generation failed"
    arr = cnn.preprocess_image(paths[0], size=32)
    assert arr.shape == (32, 32, 3)
    assert arr.dtype == np.float32 and 0.0 <= arr.min() and arr.max() <= 1.0
    X, y = cnn.load_split(root, "val", size=32)
    assert len(X) == len(cnn.CLASSES) and X.shape[1:] == (32, 32, 3)


def test_artifact_roundtrip(tmp_path):
    obj = {"a": 1, "b": [1.5, 2.5]}
    common.save_json(obj, tmp_path / "x.json")
    assert common.load_json(tmp_path / "x.json") == obj
    common.save_pickle({"w": np.arange(3)}, tmp_path / "y.pkl")
    out = common.load_pickle(tmp_path / "y.pkl")
    np.testing.assert_array_equal(out["w"], np.arange(3))


def test_shap_explanation_consistency():
    import xgboost as xgb
    rng = np.random.default_rng(1)
    X = rng.normal(size=(300, 4)).astype(np.float32)
    y = (X[:, 0] + 0.5 * X[:, 1] > 0).astype(int)
    model = xgb.XGBClassifier(n_estimators=15, max_depth=3, random_state=0)
    model.fit(X, y)
    names = ["f0", "f1", "f2", "f3"]
    sv = np.asarray(sx.shap_values(model, X[:25]))
    assert sv.shape == (25, 4)
    imp = sx.global_importance(sv, names)
    assert {d["feature"] for d in imp} == set(names)
    assert imp[0]["mean_abs_shap"] >= imp[-1]["mean_abs_shap"]
    contribs = sx.contributions(sv[0], names, top=4)
    assert {c["feature"] for c in contribs} == set(names)
    assert all(c["effect"] in ("increases_risk", "decreases_risk") for c in contribs)
    # SHAP additivity: expected_value + sum(shap) ~ raw margin
    import shap
    exp = np.asarray(shap.TreeExplainer(model).expected_value).ravel()[0]
    raw = model.get_booster().predict(xgb.DMatrix(X[:1]), output_margin=True)[0]
    assert abs(exp + sv[0].sum() - raw) < 0.05  # float32 SHAP additivity tolerance
