"""Model wrapper for loan risk scoring.

Supports XGBoost and scikit-learn models with persistent serialization
and version tracking.
"""

from __future__ import annotations

import os
import pickle
from pathlib import Path
from typing import Any, List, Optional
import numpy as np
import pandas as pd

from risk.features import NUMERIC_FEATURE_NAMES

DEFAULT_MODEL_VERSION = "risk-xgb-v1"
DEFAULT_ARTIFACTS_DIR = Path(__file__).resolve().parent / "artifacts"


class RiskModel:
    """Trained risk model wrapper producing approval probabilities."""

    def __init__(
        self,
        model_version: str = DEFAULT_MODEL_VERSION,
        feature_names: Optional[List[str]] = None,
        estimator: Optional[Any] = None,
    ):
        self.model_version = model_version
        self.feature_names = feature_names or list(NUMERIC_FEATURE_NAMES)
        self.estimator = estimator

    def fit(self, X: pd.DataFrame | np.ndarray, y: pd.Series | np.ndarray) -> RiskModel:
        """Train the underlying model (XGBoost or GradientBoostingClassifier)."""
        if isinstance(X, pd.DataFrame):
            self.feature_names = list(X.columns)

        try:
            from xgboost import XGBClassifier

            self.estimator = XGBClassifier(
                n_estimators=100,
                max_depth=4,
                learning_rate=0.08,
                random_state=42,
                eval_metric="logloss",
            )
        except ImportError:
            from sklearn.ensemble import GradientBoostingClassifier

            self.estimator = GradientBoostingClassifier(
                n_estimators=100,
                max_depth=4,
                learning_rate=0.08,
                random_state=42,
            )

        self.estimator.fit(X, y)
        return self

    def predict_proba(self, X: pd.DataFrame | np.ndarray) -> np.ndarray:
        """Predict probability of loan approval [0.0, 1.0]."""
        if self.estimator is None:
            # Fallback heuristic baseline if model has not been trained yet
            if isinstance(X, pd.DataFrame):
                values = X.values
            else:
                values = np.asarray(X)
            # Default moderate approval probability
            return np.full((values.shape[0], 2), [0.3, 0.7])

        if isinstance(X, pd.DataFrame):
            # Ensure columns match expected feature order
            missing = [col for col in self.feature_names if col not in X.columns]
            for col in missing:
                X[col] = 0.0
            X = X[self.feature_names]

        return self.estimator.predict_proba(X)

    def predict_approval_probability(self, feature_dict: dict) -> float:
        """Score a single feature dictionary and return approval probability."""
        df = pd.DataFrame([feature_dict])
        proba = self.predict_proba(df)[0, 1]
        return float(np.clip(proba, 0.0, 1.0))

    def save(self, path: Optional[str | Path] = None) -> Path:
        """Serialize model and metadata to disk."""
        if path is None:
            DEFAULT_ARTIFACTS_DIR.mkdir(parents=True, exist_ok=True)
            path = DEFAULT_ARTIFACTS_DIR / f"{self.model_version}.pkl"
        else:
            path = Path(path)
            path.parent.mkdir(parents=True, exist_ok=True)

        payload = {
            "model_version": self.model_version,
            "feature_names": self.feature_names,
            "estimator": self.estimator,
        }
        with open(path, "wb") as f:
            pickle.dump(payload, f)
        return path

    @classmethod
    def load(cls, path: Optional[str | Path] = None) -> RiskModel:
        """Load serialized model artifact from disk."""
        if path is None:
            path = DEFAULT_ARTIFACTS_DIR / f"{DEFAULT_MODEL_VERSION}.pkl"
        else:
            path = Path(path)

        if not path.exists():
            # Return fresh untrained model wrapper
            return cls(model_version=DEFAULT_MODEL_VERSION)

        with open(path, "rb") as f:
            payload = pickle.load(f)

        model = cls(
            model_version=payload.get("model_version", DEFAULT_MODEL_VERSION),
            feature_names=payload.get("feature_names", list(NUMERIC_FEATURE_NAMES)),
            estimator=payload.get("estimator"),
        )
        return model
