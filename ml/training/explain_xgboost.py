"""SHAP explanations for the XGBoost spoilage model (TreeExplainer)."""
import argparse
import json
import sys
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

from ml.utils.common import ARTIFACTS, fit_matrices, load_json, save_json  # noqa: E402


def shap_values(model, X):
    """SHAP values for an XGBoost tree model over rows of X."""
    import shap
    import numpy as np

    X = np.asarray(X, dtype=np.float32)

    explainer = shap.TreeExplainer(
        model,
        feature_perturbation="tree_path_dependent"
    )

    explanation = explainer(X)

    values = explanation.values

    # Handle binary-class output shape if returned as 3D
    if values.ndim == 3:
        values = values[:, :, 0]

    return np.asarray(values, dtype=np.float64)

def global_importance(sv, feature_names):
    """Global feature importance = mean(|SHAP|), sorted descending."""
    imp = np.abs(np.asarray(sv)).mean(axis=0)
    order = np.argsort(imp)[::-1]
    return [{"feature": feature_names[i], "mean_abs_shap": float(imp[i])} for i in order]


def contributions(row_sv, feature_names, top=10):
    """Per-prediction contributions: which factors increased/decreased risk."""
    row = np.asarray(row_sv).ravel()
    order = np.argsort(np.abs(row))[::-1][:top]
    return [{"feature": feature_names[i], "shap_value": float(row[i]),
             "effect": "increases_risk" if row[i] > 0 else "decreases_risk"}
            for i in order]


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--data", default=str(ROOT / "data/processed"))
    ap.add_argument("--sample", type=int, default=500, help="test rows to explain")
    args = ap.parse_args()

    import xgboost as xgb
    d = Path(args.data)
    feats = load_json(ARTIFACTS / "xgboost_features.json")["features"]
    tr, te = pd.read_csv(d / "train.csv"), pd.read_csv(d / "test.csv")
    meta = json.loads((d / "metadata.json").read_text())
    model = xgb.XGBClassifier()
    model.load_model(ARTIFACTS / "xgboost_spoilage.ubj")

    Xtr, _, Xte = fit_matrices(tr, tr, te, feats)
    Xte = Xte[:args.sample]
    sv = shap_values(model, Xte)
    imp = global_importance(sv, feats)
    risk = model.predict_proba(Xte)[:, 1]
    top_idx = np.argsort(risk)[::-1][:10]
    explains = [{"row_in_test": int(i), "risk_probability": float(risk[i]),
                 "contributions": contributions(sv[i], feats)} for i in top_idx]

    save_json({"data_kind": meta.get("data_kind", "SYNTHETIC/DEMO"),
               "n_explained": int(len(Xte)),
               "base_value": float(np.asarray(
                   __import__("shap").TreeExplainer(model).expected_value).ravel()[0]),
               "importance": imp}, ARTIFACTS / "shap_importance.json")
    save_json({"note": "SHAP on SYNTHETIC/DEMO data; explanations are per-prediction "
                       "factors increasing/decreasing spoilage risk.",
               "predictions": explains}, ARTIFACTS / "shap_explanations.json")
    print("[top features by mean |SHAP|]")
    for row in imp[:10]:
        print(f"  {row['feature']:<35} {row['mean_abs_shap']:.5f}")
    print(f"saved -> {ARTIFACTS / 'shap_importance.json'} + shap_explanations.json")


if __name__ == "__main__":
    main()
