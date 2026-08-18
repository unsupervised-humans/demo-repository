"""Explainability module for loan risk scoring.

Generates SHAP-style factor breakdowns explaining which features drove the
loan approval probability up or down, sorted with the most influential first.
"""

from __future__ import annotations

from typing import Any, Dict, List, Optional
import numpy as np
import pandas as pd

from risk.features import NUMERIC_FEATURE_NAMES


def compute_factor_breakdown(
    model: Any,
    feature_dict: Dict[str, Any],
    feature_names: Optional[List[str]] = None,
    top_n: int = 5,
) -> List[Dict[str, Any]]:
    """Generate SHAP-style factor breakdown for a scored loan file.

    Args:
        model: Trained RiskModel instance or underlying estimator.
        feature_dict: Dictionary of feature names and numerical values.
        feature_names: Ordered list of feature names.
        top_n: Maximum number of influential factors to return.

    Returns:
        List of dicts: [{"feature": str, "contribution": float}, ...]
        sorted by descending absolute contribution.
    """
    estimator = getattr(model, "estimator", model)
    raw_names = feature_names or getattr(model, "feature_names", NUMERIC_FEATURE_NAMES)
    names = [n for n in raw_names if n in NUMERIC_FEATURE_NAMES]

    # Convert to numeric DataFrame row
    df_sample = pd.DataFrame(
        [[float(feature_dict.get(k, 0.0)) for k in names]], columns=names
    )

    factors: List[Dict[str, Any]] = []

    # 1. Try SHAP TreeExplainer / Explainer if estimator is trained
    if estimator is not None:
        try:
            import shap

            explainer = shap.TreeExplainer(estimator)
            shap_values = explainer.shap_values(df_sample)

            # Handle multi-output or single-output shap values
            if isinstance(shap_values, list) and len(shap_values) == 2:
                # Class 1 (approval) SHAP values
                vals = shap_values[1][0]
            elif isinstance(shap_values, np.ndarray):
                if shap_values.ndim == 3:
                    vals = shap_values[0, :, 1]
                else:
                    vals = shap_values[0]
            else:
                vals = np.array(shap_values)[0]

            for feat, val in zip(names, vals):
                factors.append({"feature": feat, "contribution": round(float(val), 4)})
        except Exception:
            # Fallback if SHAP fails or model is heuristic
            factors = []

    # 2. Fallback heuristic contribution calculation if SHAP is not available or model untrained
    if not factors:
        cibil = float(feature_dict.get("cibil_score", 600.0))
        loan_to_income = float(feature_dict.get("loan_to_income_ratio", 2.0))
        income = float(feature_dict.get("income_annum", 500000.0))
        loan_amt = float(feature_dict.get("loan_amount", 1000000.0))
        bank_assets = float(feature_dict.get("bank_asset_value", 500000.0))

        heuristic_contributions = {
            "cibil_score": round((cibil - 600.0) / 300.0, 4),
            "loan_to_income_ratio": round(-(loan_to_income - 2.5) * 0.15, 4),
            "bank_asset_value": round((bank_assets - (income * 0.5)) / max(income, 1.0) * 0.1, 4),
            "loan_amount": round(-(loan_amt - 1000000.0) / 10000000.0, 4),
        }

        for feat, contrib in heuristic_contributions.items():
            if abs(contrib) > 0.0001:
                factors.append({"feature": feat, "contribution": contrib})

    # Sort factors by absolute contribution descending (most influential first)
    factors.sort(key=lambda x: abs(x["contribution"]), reverse=True)

    return factors[:top_n]
