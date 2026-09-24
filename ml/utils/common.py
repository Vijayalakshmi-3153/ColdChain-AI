"""Shared ML utilities: artifacts, chronological split, matrices, metrics, windows, AE inference."""
import json
import pickle
from pathlib import Path

import numpy as np
import pandas as pd
from sklearn.metrics import (average_precision_score, confusion_matrix,
                             precision_recall_fscore_support)

ARTIFACTS = Path(__file__).resolve().parents[1] / "artifacts"


def save_json(obj, path):
    Path(path).parent.mkdir(parents=True, exist_ok=True)
    Path(path).write_text(json.dumps(obj, indent=2, default=float))


def load_json(path):
    return json.loads(Path(path).read_text())


def save_pickle(obj, path):
    Path(path).parent.mkdir(parents=True, exist_ok=True)
    Path(path).open("wb").write(pickle.dumps(obj))


def load_pickle(path):
    return pickle.loads(Path(path).read_bytes())


def group_chronological_split(df, time_col="timestamp", group_col="shipment_id",
                              ratios=(0.70, 0.15, 0.15)):
    """Split by whole groups ordered by start time: chronological, and no
    shipment appears in two splits (prevents group leakage)."""
    starts = df.groupby(group_col)[time_col].min().sort_values()
    ids = list(starts.index)
    n1, n2 = int(len(ids) * ratios[0]), int(len(ids) * (ratios[0] + ratios[1]))
    parts = {"train": ids[:n1], "val": ids[n1:n2], "test": ids[n2:]}
    return {k: df[df[group_col].isin(v)].sort_values(time_col).reset_index(drop=True)
            for k, v in parts.items()}


def fit_matrices(train, val, test, cols):
    """Numeric float32 matrices; imputation stats fit on TRAIN only (no leakage)."""
    med = train[cols].apply(pd.to_numeric, errors="coerce").median().fillna(0.0)
    out = []
    for d in (train, val, test):
        X = (d[cols].apply(pd.to_numeric, errors="coerce")
             .replace([np.inf, -np.inf], np.nan).fillna(med).fillna(0.0))
        out.append(X.to_numpy(np.float32))
    return out


def binary_metrics(y_true, y_prob, threshold=0.5):
    y, p = np.asarray(y_true), np.asarray(y_prob)
    yhat = (p >= threshold).astype(int)
    prec, rec, f1, _ = precision_recall_fscore_support(y, yhat, average="binary",
                                                       zero_division=0)
    return {"n": int(len(y)), "positives": int(y.sum()),
            "threshold": float(threshold),
            "accuracy": float((yhat == y).mean()),
            "majority_baseline_accuracy": float(max(y.mean(), 1 - y.mean())),
            "precision": float(prec), "recall": float(rec), "f1": float(f1),
            "pr_auc": float(average_precision_score(y, p)) if y.sum() else None,
            "confusion_matrix": confusion_matrix(y, yhat, labels=[0, 1]).tolist()}


def best_f1_threshold(y_true, y_prob, grid=None):
    """Tune decision threshold on validation data (never on test)."""
    grid = grid or np.arange(0.05, 0.95, 0.05)
    y, p = np.asarray(y_true), np.asarray(y_prob)
    best_th, best_f1 = 0.5, -1.0
    for th in grid:
        _, _, f1, _ = precision_recall_fscore_support(y, (p >= th).astype(int),
                                                      average="binary", zero_division=0)
        if f1 > best_f1:
            best_th, best_f1 = float(th), float(f1)
    return best_th


def sliding_windows(values, seq_len, horizon):
    """Chronological windows in one series: X = last seq_len rows, Y = next horizon rows."""
    v = np.asarray(values, dtype=np.float32)
    n = len(v) - seq_len - horizon + 1
    f = v.shape[-1] if v.ndim > 1 else 1
    if v.ndim == 1:
        v = v[:, None]
    if n <= 0:
        return (np.empty((0, seq_len, f), np.float32),
                np.empty((0, horizon, f), np.float32))
    X = np.stack([v[i:i + seq_len] for i in range(n)])
    Y = np.stack([v[i + seq_len:i + seq_len + horizon] for i in range(n)])
    return X, Y


def reconstruction_error(model, x):
    """Per-sample mean squared reconstruction error (works for Keras or any predict())."""
    x = np.asarray(x, dtype=np.float32)
    try:
        xh = model.predict(x, verbose=0)
    except TypeError:
        xh = model.predict(x)
    xh = np.asarray(xh, dtype=np.float32).reshape(x.shape)
    return np.mean((x - xh) ** 2, axis=tuple(range(1, x.ndim)))


def is_anomaly(model, x, threshold):
    """True where reconstruction error exceeds the calibrated threshold."""
    return reconstruction_error(model, x) > threshold
