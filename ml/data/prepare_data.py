"""Preprocess raw telemetry -> validate -> features + target -> chronological splits.

Saves processed datasets under data/processed/ (train/val/test + metadata.json).
Raw data is only read, never modified.
"""
import argparse
import json
import sys
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

from ml.utils.common import group_chronological_split            # noqa: E402
from ml.utils.features import build_features, feature_columns, future_discard_target  # noqa: E402

REQUIRED = ["timestamp", "shipment_id", "temperature", "humidity",
            "minimum_temperature", "maximum_temperature", "shelf_life_hours", "q10",
            "maximum_allowed_excursion_minutes", "door_open", "latitude", "longitude",
            "battery_level"]


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--raw", default=str(ROOT / "data/raw/coldchain_synthetic_v1.csv"))
    ap.add_argument("--out", default=str(ROOT / "data/processed"))
    ap.add_argument("--horizon", type=int, default=24,
                    help="label horizon: readings before the discard event")
    args = ap.parse_args()

    df = pd.read_csv(args.raw, parse_dates=["timestamp"])
    missing = [c for c in REQUIRED if c not in df.columns]
    if missing:
        raise SystemExit(f"VALIDATION FAILED, missing columns: {missing}")
    n_in = len(df)
    df = df.dropna(subset=["temperature"]).sort_values(["shipment_id", "timestamp"])
    if df.duplicated(["shipment_id", "timestamp"]).any():
        raise SystemExit("VALIDATION FAILED: duplicate shipment/timestamp rows")

    df = build_features(df)                                # past-only features
    df["future_discard"] = future_discard_target(df, args.horizon)  # future label

    splits = group_chronological_split(df)                 # 70/15/15 by shipment start
    out = Path(args.out)
    out.mkdir(parents=True, exist_ok=True)
    for name, part in splits.items():
        part.to_csv(out / f"{name}.csv", index=False)

    feats = feature_columns(splits["train"])
    meta = {
        "source": str(args.raw), "data_kind": "SYNTHETIC/DEMO",
        "rows_in": n_in, "rows": {k: len(v) for k, v in splits.items()},
        "target": "future_discard", "horizon": args.horizon,
        "split": "group-chronological 70/15/15 by shipment start time",
        "features": feats,
        "class_distribution": {k: {"neg": int((v.future_discard == 0).sum()),
                                   "pos": int(v.future_discard.sum()),
                                   "pos_rate": round(float(v.future_discard.mean()), 4)}
                               for k, v in splits.items()},
        "note": "Built from SYNTHETIC/DEMO data; metrics are development metrics only.",
    }
    (out / "metadata.json").write_text(json.dumps(meta, indent=2))
    print("class_distribution:", json.dumps(meta["class_distribution"], indent=2))
    print(f"feature count = {len(feats)}")
    print(f"processed -> {out} (train/val/test.csv, metadata.json)")


if __name__ == "__main__":
    main()
