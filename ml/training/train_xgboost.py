"""Train XGBoost spoilage-risk model with class-imbalance handling and honest metrics."""
import argparse
import json
import sys
from pathlib import Path

import pandas as pd
import xgboost as xgb

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

from ml.utils.common import (ARTIFACTS, best_f1_threshold, binary_metrics,
                             fit_matrices, save_json)  # noqa: E402


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--data", default=str(ROOT / "data/processed"))
    args = ap.parse_args()
    d = Path(args.data)
    tr = pd.read_csv(d / "train.csv")
    va = pd.read_csv(d / "val.csv")
    te = pd.read_csv(d / "test.csv")
    meta = json.loads((d / "metadata.json").read_text())
    feats = meta["features"]

    Xtr, Xva, Xte = fit_matrices(tr, va, te, feats)
    ytr, yva, yte = tr.future_discard.values, va.future_discard.values, te.future_discard.values
    pos, neg = int(ytr.sum()), int((ytr == 0).sum())
    print(f"[data] SYNTHETIC/DEMO dataset | features={len(feats)}")
    print(f"[imbalance] TRAIN class distribution: pos={pos} ({pos/len(ytr):.2%})  neg={neg}")
    if pos == 0 or neg == 0:
        raise SystemExit("Training split must contain both classes")
    scale = neg / pos  # strategy: inverse class-frequency weighting

    model = xgb.XGBClassifier(
        n_estimators=400, max_depth=5, learning_rate=0.05, subsample=0.8,
        colsample_bytree=0.8, min_child_weight=5, scale_pos_weight=scale,
        eval_metric="aucpr", early_stopping_rounds=40, random_state=42, n_jobs=4)
    model.fit(Xtr, ytr, eval_set=[(Xva, yva)], verbose=False)

    thr = best_f1_threshold(yva, model.predict_proba(Xva)[:, 1])  # tuned on VAL
    test_metrics = binary_metrics(yte, model.predict_proba(Xte)[:, 1], thr)
    print("[TEST metrics]", json.dumps(test_metrics, indent=2))
    if test_metrics["majority_baseline_accuracy"] >= test_metrics["accuracy"]:
        print("[note] accuracy <= majority baseline: use PR-AUC/precision/recall, not accuracy.")

    ARTIFACTS.mkdir(parents=True, exist_ok=True)
    model.save_model(ARTIFACTS / "xgboost_spoilage.ubj")
    save_json({"features": feats, "threshold": thr, "scale_pos_weight": scale,
               "params": {"n_estimators": 400, "max_depth": 5, "learning_rate": 0.05,
                          "subsample": 0.8, "colsample_bytree": 0.8, "min_child_weight": 5},
               "test_metrics": test_metrics,
               "data_kind": meta.get("data_kind", "SYNTHETIC/DEMO")},
              ARTIFACTS / "xgboost_features.json")
    print(f"saved -> {ARTIFACTS / 'xgboost_spoilage.ubj'} + xgboost_features.json")


if __name__ == "__main__":
    main()
