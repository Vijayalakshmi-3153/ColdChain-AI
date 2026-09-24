"""Autoencoder anomaly detection.

Trains ONLY on windows whose temperature stays inside the product's allowed
range (normal operation), then flags windows whose reconstruction error is
above a threshold calibrated on validation normal windows.

Two design choices make this work on cold-chain data:
  1. Scale-invariant channels from each row's KNOWN product bounds
     (available in real time): temperature as a fraction of the allowed
     range and humidity/100. Normal rows sit inside [0, 1]; excursions
     push values outside it.
  2. The anomaly score is the MAXIMUM per-timestep reconstruction error in
     the window (an excursion affects only part of a 24-reading window), not
     the window-average error which would dilute it.
"""
import argparse
import json
import sys
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

from ml.utils.common import (ARTIFACTS, save_json, save_pickle,
                             sliding_windows)  # noqa: E402

COLS = ["temperature", "humidity"]
SEQ = 24


def channel_matrix(g):
    """<- two scale-invariant channels per row (no future data used)."""
    lo = g["minimum_temperature"].to_numpy("float32")
    hi = g["maximum_temperature"].to_numpy("float32")
    width = np.maximum(hi - lo, 1e-3)
    temp = (g["temperature"].to_numpy("float32") - lo) / width   # 0..1 inside range
    hum = g["humidity"].to_numpy("float32") / 100.0              # 0..1
    return np.stack([temp, hum], axis=1).astype("float32")


def windows_for(df, seq=SEQ):
    """Sliding windows + flag marking windows fully inside the allowed range."""
    X_all, mask_all = [], []
    for _, g in df.sort_values("timestamp").groupby("shipment_id"):
        X, _ = sliding_windows(channel_matrix(g), seq, 0)
        raw, _ = sliding_windows(g["temperature"].to_numpy("float32"), seq, 0)
        lo, _ = sliding_windows(g["minimum_temperature"].to_numpy("float32"), seq, 0)
        hi, _ = sliding_windows(g["maximum_temperature"].to_numpy("float32"), seq, 0)
        if len(X):
            X_all.append(X)
            # squeeze the single-channel axis -> one boolean per window
            raw, lo, hi = raw[..., 0], lo[..., 0], hi[..., 0]
            mask_all.append(((lo <= raw) & (raw <= hi)).all(axis=1))
    return np.concatenate(X_all), np.concatenate(mask_all)


def flatten(X):
    return X.reshape(len(X), -1).astype("float32")


def anomaly_score(model, X_scaled, shape):
    """Per-window anomaly score = max over timesteps of the mean squared
    reconstruction error of the two channels for that timestep."""
    pred = model.predict(flatten(X_scaled), verbose=0)
    pred = np.asarray(pred, "float32").reshape(shape)
    per_step = ((X_scaled - pred) ** 2).mean(axis=2)   # (n_windows, seq)
    return per_step.max(axis=1)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--data", default=str(ROOT / "data/processed"))
    ap.add_argument("--epochs", type=int, default=30)
    ap.add_argument("--quantile", type=float, default=0.95,
                    help="threshold = quantile of VALIDATION normal scores")
    args = ap.parse_args()

    d = Path(args.data)
    tr, va, te = (pd.read_csv(d / f"{s}.csv") for s in ("train", "val", "test"))
    Xtr, mtr = windows_for(tr)
    Xva, mva = windows_for(va)
    Xte, mte = windows_for(te)
    print(f"[windows] seq={SEQ} train_normal={int(mtr.sum())}/{len(Xtr)} "
          f"val_normal={int(mva.sum())}/{len(Xva)} test_normal={int(mte.sum())}/{len(Xte)}")

    # Standardize channels using TRAIN NORMAL windows only (no leakage).
    mu = Xtr[mtr].reshape(-1, 2).mean(axis=0)
    sd = Xtr[mtr].reshape(-1, 2).std(axis=0) + 1e-6
    scale = lambda X: ((X - mu) / sd).astype("float32")
    Xtr, Xva, Xte = scale(Xtr), scale(Xva), scale(Xte)

    from tensorflow import keras
    inp = SEQ * 2
    model = keras.Sequential([
        keras.layers.Input((inp,)),
        keras.layers.Dense(64, activation="relu"),
        keras.layers.Dense(16, activation="relu"),
        keras.layers.Dense(64, activation="relu"),
        keras.layers.Dense(inp)])
    model.compile(optimizer="adam", loss="mse")
    Xn = flatten(Xtr[mtr])
    model.fit(Xn, Xn, validation_data=(flatten(Xva[mva]), flatten(Xva[mva])),
              epochs=args.epochs, batch_size=64, verbose=2)

    # Calibrate threshold on VALIDATION normal windows only.
    val_normal = anomaly_score(model, Xva[mva], (int(mva.sum()), SEQ, 2))
    threshold = float(np.quantile(val_normal, args.quantile))
    print(f"[scores] val normal mean={val_normal.mean():.4f} "
          f"| threshold q{args.quantile:.2f} = {threshold:.4f}")

    test_normal = anomaly_score(model, Xte[mte], (int(mte.sum()), SEQ, 2))
    abn = ~mte
    result = {"threshold": threshold, "val_normal_mean_score": float(val_normal.mean()),
              "test_normal_mean_score": float(test_normal.mean())}
    print(f"[TEST] normal mean score={result['test_normal_mean_score']:.4f}")
    if abn.any():
        test_exc = anomaly_score(model, Xte[abn], (int(abn.sum()), SEQ, 2))
        rate = float((test_exc > threshold).mean())
        false_pos = float((test_normal > threshold).mean())
        result.update({"test_excursion_mean_score": float(test_exc.mean()),
                       "excursion_detection_rate": rate,
                       "test_normal_false_positive_rate": false_pos})
        print(f"[TEST] excursion mean score={test_exc.mean():.4f} | "
              f"detection rate={rate:.1%} | normal false-positive rate={false_pos:.1%} "
              f"(SYNTHETIC sanity check)")
    else:
        print("[TEST] no excursion windows in test split; detection rate not computed.")

    ARTIFACTS.mkdir(parents=True, exist_ok=True)
    model.save(ARTIFACTS / "autoencoder.keras")
    save_json({**result, "seq_len": SEQ, "channels": COLS, "quantile": args.quantile,
               "channel_mean": [float(x) for x in mu], "channel_std": [float(x) for x in sd],
               "data_kind": "SYNTHETIC/DEMO",
               "note": "Scores/threshold from SYNTHETIC data - pipeline check only."},
              ARTIFACTS / "autoencoder_meta.json")
    save_pickle({"seq_len": SEQ, "channels": COLS, "mean": mu, "std": sd,
                 "threshold": threshold}, ARTIFACTS / "autoencoder_meta.pkl")
    print(f"saved -> {ARTIFACTS / 'autoencoder.keras'} + autoencoder_meta.json")


if __name__ == "__main__":
    main()