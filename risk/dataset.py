"""Dataset management for loan risk scoring models.

Supports loading external datasets (e.g., Kaggle loan approval datasets)
and generating synthetic training data for development and testing.
"""

from __future__ import annotations

from typing import Optional, Tuple
import numpy as np
import pandas as pd

from risk.features import NUMERIC_FEATURE_NAMES


def generate_synthetic_loan_dataset(
    n_samples: int = 1000,
    random_state: int = 42,
) -> pd.DataFrame:
    """Generate a realistic synthetic dataset for loan approval training.

    Args:
        n_samples: Number of samples to generate.
        random_state: Random seed for reproducibility.

    Returns:
        pd.DataFrame containing feature columns and target 'approved' (0 or 1).
    """
    rng = np.random.default_rng(random_state)

    # Incomes: 25k to 250k
    declared_income = np.exp(rng.normal(loc=11.0, scale=0.5, size=n_samples))
    declared_income = np.clip(declared_income, 20000, 300000).round(2)

    # Loan amounts requested: 50k to 1M
    loan_amount = np.exp(rng.normal(loc=12.5, scale=0.6, size=n_samples))
    loan_amount = np.clip(loan_amount, 50000, 1500000).round(2)

    income_to_loan_ratio = declared_income / loan_amount

    # Gross income and bank deposits with some noise/variance
    income_noise = rng.normal(0, 0.08, size=n_samples)
    gross_monthly_income = declared_income
    avg_monthly_deposit = np.maximum(0, declared_income * (1.0 + income_noise)).round(2)

    deposit_to_income_ratio = avg_monthly_deposit / np.maximum(gross_monthly_income, 1.0)
    denom = np.maximum(gross_monthly_income, avg_monthly_deposit)
    deposit_consistency = np.maximum(
        0.0, 1.0 - (np.abs(gross_monthly_income - avg_monthly_deposit) / denom)
    )

    # Extraction confidence metrics
    avg_extraction_conf = np.clip(rng.beta(a=9, b=1, size=n_samples), 0.5, 1.0)
    min_extraction_conf = np.clip(avg_extraction_conf - rng.uniform(0, 0.2, size=n_samples), 0.3, 1.0)
    low_conf_count = (avg_extraction_conf < 0.85).astype(float) * rng.integers(0, 3, size=n_samples)

    # Validation findings and fraud flags
    critical_findings = rng.poisson(lam=0.15, size=n_samples)
    warning_findings = rng.poisson(lam=0.5, size=n_samples)
    total_findings = critical_findings + warning_findings
    fraud_flags = rng.poisson(lam=0.08, size=n_samples)
    docs_count = rng.integers(1, 6, size=n_samples)

    df = pd.DataFrame(
        {
            "declared_income": declared_income,
            "loan_amount_requested": loan_amount,
            "income_to_loan_ratio": income_to_loan_ratio,
            "gross_monthly_income": gross_monthly_income,
            "avg_monthly_deposit": avg_monthly_deposit,
            "deposit_to_income_ratio": deposit_to_income_ratio,
            "deposit_consistency": deposit_consistency,
            "min_extraction_confidence": min_extraction_conf,
            "avg_extraction_confidence": avg_extraction_conf,
            "low_confidence_fields_count": low_conf_count,
            "critical_findings_count": critical_findings.astype(float),
            "warning_findings_count": warning_findings.astype(float),
            "total_findings_count": total_findings.astype(float),
            "fraud_flags_count": fraud_flags.astype(float),
            "documents_count": docs_count.astype(float),
        }
    )

    # Calculate ground truth approval probability with non-linear factors
    log_odds = (
        1.5 * (df["income_to_loan_ratio"] * 10 - 1.2)
        + 2.0 * (df["deposit_consistency"] - 0.8)
        + 1.0 * (df["avg_extraction_confidence"] - 0.9)
        - 3.5 * df["critical_findings_count"]
        - 1.2 * df["warning_findings_count"]
        - 4.0 * df["fraud_flags_count"]
        - 0.5 * df["low_confidence_fields_count"]
    )
    prob = 1.0 / (1.0 + np.exp(-log_odds))
    approved = (rng.uniform(0, 1, size=n_samples) < prob).astype(int)
    df["approved"] = approved

    return df


def load_dataset(csv_path: Optional[str] = None) -> pd.DataFrame:
    """Load dataset from a CSV path or fallback to synthetic generation."""
    if csv_path:
        df = pd.read_csv(csv_path)
        return df
    return generate_synthetic_loan_dataset()


def get_train_test_data(
    df: Optional[pd.DataFrame] = None,
    test_size: float = 0.2,
    random_state: int = 42,
) -> Tuple[pd.DataFrame, pd.DataFrame, pd.Series, pd.Series]:
    """Split dataset into train and test sets."""
    if df is None:
        df = generate_synthetic_loan_dataset(random_state=random_state)

    feature_cols = [c for c in NUMERIC_FEATURE_NAMES if c in df.columns]
    X = df[feature_cols]
    y = df["approved"]

    # Use numpy split
    rng = np.random.default_rng(random_state)
    indices = np.arange(len(df))
    rng.shuffle(indices)

    split_idx = int(len(df) * (1 - test_size))
    train_idx = indices[:split_idx]
    test_idx = indices[split_idx:]

    return X.iloc[train_idx], X.iloc[test_idx], y.iloc[train_idx], y.iloc[test_idx]
