"""Model training script and pipeline for loan risk scoring.

Trains a classical ML model (XGBoost / Gradient Boosting) on loan approval datasets,
evaluates performance metrics, and serializes the model artifact.
"""

from __future__ import annotations

import argparse
from pathlib import Path
from typing import Any, Dict, Optional

from risk.dataset import get_train_test_data, load_dataset
from risk.model import DEFAULT_ARTIFACTS_DIR, DEFAULT_MODEL_VERSION, RiskModel


def train_baseline_model(
    csv_path: Optional[str] = None,
    output_path: Optional[str | Path] = None,
    model_version: str = DEFAULT_MODEL_VERSION,
) -> Dict[str, Any]:
    """Train baseline risk model, evaluate test performance, and save artifact.

    Args:
        csv_path: Optional path to training CSV data.
        output_path: Optional destination path for model artifact.
        model_version: Version identifier string.

    Returns:
        Dict with trained model instance, output path, and evaluation metrics.
    """
    df = load_dataset(csv_path)
    X_train, X_test, y_train, y_test = get_train_test_data(df)

    model = RiskModel(model_version=model_version, feature_names=list(X_train.columns))
    model.fit(X_train, y_train)

    # Evaluate
    y_pred_proba = model.predict_proba(X_test)[:, 1]
    y_pred = (y_pred_proba >= 0.5).astype(int)

    acc = float((y_pred == y_test).mean())

    try:
        from sklearn.metrics import roc_auc_score

        roc_auc = float(roc_auc_score(y_test, y_pred_proba))
    except Exception:
        roc_auc = 0.0

    if output_path is None:
        DEFAULT_ARTIFACTS_DIR.mkdir(parents=True, exist_ok=True)
        output_path = DEFAULT_ARTIFACTS_DIR / f"{model_version}.pkl"

    saved_path = model.save(output_path)

    metrics = {
        "accuracy": round(acc, 4),
        "roc_auc": round(roc_auc, 4),
        "train_samples": len(X_train),
        "test_samples": len(X_test),
        "model_version": model_version,
        "saved_path": str(saved_path),
    }
    return {"model": model, "metrics": metrics, "saved_path": saved_path}


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Train LoanIQ risk scoring model")
    parser.add_argument("--data", type=str, default=None, help="Path to training CSV data")
    parser.add_argument("--out", type=str, default=None, help="Output artifact path")
    args = parser.parse_args()

    result = train_baseline_model(csv_path=args.data, output_path=args.out)
    print("Model training complete:", result["metrics"])
