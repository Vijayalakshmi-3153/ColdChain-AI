"""LSTM temperature/humidity forecasting: chronological sliding windows, train-only scaler."""
import argparse
import json
import sys
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

from ml.utils.common import ARTIFACTS, save_json, save_pickle, sliding_windows  # noqa: E402

COLS = ["temperature", "humidity"]


def build_windows(df, seq, horizon):
    """Sliding windows built strictly INSIDE each shipment (no cross-shipment windows)."""
    Xs, Ys = [], []
    for _, g in df.sort_values("timestamp").groupby("shipment_id"):
        X, Y = sliding_windows(g[COLS].to_numpy("float32"), seq, horizon)
        if len(X):
            Xs.append(X)
            Ys.append(Y)
    return np.concatenate(Xs), np.concatenate(Ys)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--data", default=str(ROOT / "data/processed"))
    ap.add_argument("--seq", type=int, default=48, help="window length 30-60 readings")
    ap.add_argument("--horizon", type=int, default=6, help="forecast horizon (readings)")
    ap.add_argument("--epochs", type=int, default=6)
    args = ap.parse_args()

    d = Path(args.data)
    tr, va, te = (pd.read_csv(d / f"{s}.csv") for s in ("train", "val", "test"))

    from sklearn.preprocessing import StandardScaler
    sc = StandardScaler().fit(tr[COLS].to_numpy("float32"))  # fit on TRAIN only (no leakage)
    trs, vas, tes = tr.copy(), va.copy(), te.copy()
    trs[COLS] = sc.transform(tr[COLS])
    vas[COLS] = sc.transform(va[COLS])
    tes[COLS] = sc.transform(te[COLS])

    Xtr, Ytr = build_windows(trs, args.seq, args.horizon)
    Xva, Yva = build_windows(vas, args.seq, args.horizon)
    Xte, Yte = build_windows(tes, args.seq, args.horizon)
    print(f"[windows] seq={args.seq} horizon={args.horizon} "
          f"train={len(Xtr)} val={len(Xva)} test={len(Xte)}")
    if len(Xtr) < 200:
        print("[LIMITATION] very few windows: LSTM result will NOT be reliable.")

    from tensorflow import keras
    model = keras.Sequential([
        keras.layers.Input((args.seq, 2)),
        keras.layers.LSTM(64),
        keras.layers.Dense(32, activation="relu"),
        keras.layers.Dense(args.horizon * 2)])
    model.compile(optimizer="adam", loss="mse", metrics=["mae"])
    model.fit(Xtr, Ytr.reshape(len(Ytr), -1),
              validation_data=(Xva, Yva.reshape(len(Yva), -1)),
              epochs=args.epochs, batch_size=64, verbose=2)

    pred = model.predict(Xte, verbose=0).reshape(-1, args.horizon, 2)
    err = (pred - Yte) * sc.scale_  # back to original units (deg C / %RH)
    metrics = {}
    for i, col in enumerate(COLS):
        rmse = float((err[..., i] ** 2).mean() ** 0.5)
        mae = float(abs(err[..., i]).mean())
        metrics[col] = {"rmse": rmse, "mae": mae}
        print(f"[TEST {col}] RMSE={rmse:.3f}  MAE={mae:.3f}")

    ARTIFACTS.mkdir(parents=True, exist_ok=True)
    model.save(ARTIFACTS / "lstm_forecast.keras")
    save_pickle(sc, ARTIFACTS / "lstm_scaler.pkl")
    save_json({"seq_len": args.seq, "horizon": args.horizon, "features": COLS,
               "epochs": args.epochs,
               "windows": {"train": len(Xtr), "val": len(Xva), "test": len(Xte)},
               "test_metrics": metrics, "data_kind": "SYNTHETIC/DEMO",
               "note": "Development metrics on synthetic data; not real-world validation."},
              ARTIFACTS / "lstm_meta.json")
    print(f"saved -> {ARTIFACTS / 'lstm_forecast.keras'} + lstm_scaler.pkl + lstm_meta.json")


if __name__ == "__main__":
    main()
