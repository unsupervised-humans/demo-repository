"""Dataset management for loan risk scoring models.

Loads and preprocesses the real Kaggle Loan Approval Prediction Dataset
for production model training, and provides a synthetic generator for unit testing.
"""

from __future__ import annotations

from pathlib import Path
from typing import Optional, Tuple
import numpy as np
import pandas as pd

from risk.features import NUMERIC_FEATURE_NAMES

DEFAULT_RAW_DATA_PATH = (
    Path(__file__).resolve().parent / "data" / "raw" / "loan_approval_dataset.csv"
)


def generate_synthetic_loan_dataset(
    n_samples: int = 1000,
    random_state: int = 42,
) -> pd.DataFrame:
    """Generate synthetic dataset for unit testing only, not used for the production model.

    Args:
        n_samples: Number of synthetic records to produce.
        random_state: Random seed for reproducibility.

    Returns:
        pd.DataFrame containing feature columns and binary target 'approved'.
    """
    rng = np.random.default_rng(random_state)

    no_of_dependents = rng.integers(0, 6, size=n_samples).astype(float)
    education = rng.choice([0.0, 1.0], size=n_samples, p=[0.25, 0.75])
    self_employed = rng.choice([0.0, 1.0], size=n_samples, p=[0.8, 0.2])

    income_annum = np.clip(np.exp(rng.normal(15.2, 0.6, size=n_samples)), 200000, 10000000).round(2)
    loan_amount = np.clip(np.exp(rng.normal(16.0, 0.7, size=n_samples)), 300000, 35000000).round(2)
    loan_term = rng.choice([2.0, 4.0, 6.0, 8.0, 10.0, 12.0, 14.0, 16.0, 18.0, 20.0], size=n_samples)
    cibil_score = np.clip(rng.normal(620, 120, size=n_samples), 300, 900).round(1)

    residential_assets = np.clip(income_annum * rng.uniform(0.5, 3.0, size=n_samples), 0, 30000000).round(2)
    commercial_assets = np.clip(income_annum * rng.uniform(0.0, 2.0, size=n_samples), 0, 20000000).round(2)
    luxury_assets = np.clip(income_annum * rng.uniform(0.5, 4.0, size=n_samples), 0, 40000000).round(2)
    bank_asset_value = np.clip(income_annum * rng.uniform(0.2, 1.5, size=n_samples), 0, 15000000).round(2)

    loan_to_income_ratio = np.round(loan_amount / np.maximum(income_annum, 1.0), 4)

    df = pd.DataFrame(
        {
            "no_of_dependents": no_of_dependents,
            "education": education,
            "self_employed": self_employed,
            "income_annum": income_annum,
            "loan_amount": loan_amount,
            "loan_term": loan_term,
            "cibil_score": cibil_score,
            "residential_assets_value": residential_assets,
            "commercial_assets_value": commercial_assets,
            "luxury_assets_value": luxury_assets,
            "bank_asset_value": bank_asset_value,
            "loan_to_income_ratio": loan_to_income_ratio,
        }
    )

    # Ground truth approval driven primarily by CIBIL, loan_to_income_ratio, and asset coverage
    asset_total = residential_assets + commercial_assets + luxury_assets + bank_asset_value
    asset_coverage = asset_total / np.maximum(loan_amount, 1.0)

    log_odds = (
        0.025 * (cibil_score - 550)
        - 0.8 * (loan_to_income_ratio - 2.5)
        + 0.5 * (asset_coverage - 1.5)
        + 0.3 * education
        - 0.2 * self_employed
    )
    prob = 1.0 / (1.0 + np.exp(-log_odds))
    df["approved"] = (rng.uniform(0, 1, size=n_samples) < prob).astype(int)

    return df


def load_dataset(csv_path: Optional[str | Path] = None) -> pd.DataFrame:
    """Load and preprocess the real Kaggle Loan Approval Prediction Dataset.

    Preprocesses:
    - Strips whitespace from column names and string values
    - Encodes 'loan_status' as 0/1 binary target ('approved')
    - Encodes 'education' as binary (Graduate: 1, Not Graduate: 0)
    - Encodes 'self_employed' as binary (Yes: 1, No: 0)
    - Keeps all numerical columns as float
    - Computes derived 'loan_to_income_ratio'

    Args:
        csv_path: Optional path to CSV file. Defaults to risk/data/raw/loan_approval_dataset.csv.

    Returns:
        pd.DataFrame ready for model training.
    """
    target_path = Path(csv_path) if csv_path else DEFAULT_RAW_DATA_PATH

    if not target_path.exists():
        return generate_synthetic_loan_dataset()

    df = pd.read_csv(target_path)
    df.columns = df.columns.str.strip()

    # 1. Encode binary target 'approved' (Approved: 1, Rejected: 0)
    if "loan_status" in df.columns:
        status_clean = df["loan_status"].astype(str).str.strip().str.lower()
        df["approved"] = (status_clean == "approved").astype(int)

    # 2. Encode categorical features as binary
    if "education" in df.columns:
        edu_clean = df["education"].astype(str).str.strip().str.lower()
        df["education"] = (edu_clean == "graduate").astype(float)

    if "self_employed" in df.columns:
        se_clean = df["self_employed"].astype(str).str.strip().str.lower()
        df["self_employed"] = (se_clean == "yes").astype(float)

    # 3. Ensure numeric columns are floats
    numeric_base_cols = [
        "no_of_dependents",
        "income_annum",
        "loan_amount",
        "loan_term",
        "cibil_score",
        "residential_assets_value",
        "commercial_assets_value",
        "luxury_assets_value",
        "bank_asset_value",
    ]
    for col in numeric_base_cols:
        if col in df.columns:
            df[col] = df[col].astype(float)

    # 4. Compute derived feature: loan_to_income_ratio
    if "loan_amount" in df.columns and "income_annum" in df.columns:
        df["loan_to_income_ratio"] = (
            df["loan_amount"] / df["income_annum"].clip(lower=1.0)
        ).round(4)

    return df


def get_train_test_data(
    df: Optional[pd.DataFrame] = None,
    test_size: float = 0.2,
    random_state: int = 42,
) -> Tuple[pd.DataFrame, pd.DataFrame, pd.Series, pd.Series]:
    """Split dataset into train and test sets for model training.

    Args:
        df: DataFrame (loads production dataset by default).
        test_size: Proportion of dataset for test set.
        random_state: Seed for random shuffling.

    Returns:
        (X_train, X_test, y_train, y_test)
    """
    if df is None:
        df = load_dataset()

    feature_cols = [c for c in NUMERIC_FEATURE_NAMES if c in df.columns]
    X = df[feature_cols]
    y = df["approved"]

    rng = np.random.default_rng(random_state)
    indices = np.arange(len(df))
    rng.shuffle(indices)

    split_idx = int(len(df) * (1 - test_size))
    train_idx = indices[:split_idx]
    test_idx = indices[split_idx:]

    return X.iloc[train_idx], X.iloc[test_idx], y.iloc[train_idx], y.iloc[test_idx]
