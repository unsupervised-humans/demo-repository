import pytest
import pandas as pd
from risk.dataset import generate_synthetic_loan_dataset, get_train_test_data, load_dataset
from risk.features import NUMERIC_FEATURE_NAMES


def test_generate_synthetic_loan_dataset():
    df = generate_synthetic_loan_dataset(n_samples=100, random_state=42)
    assert isinstance(df, pd.DataFrame)
    assert len(df) == 100
    assert "approved" in df.columns
    for feature in NUMERIC_FEATURE_NAMES:
        assert feature in df.columns
    assert set(df["approved"].unique()).issubset({0, 1})


def test_get_train_test_data():
    df = generate_synthetic_loan_dataset(n_samples=200, random_state=42)
    X_train, X_test, y_train, y_test = get_train_test_data(df, test_size=0.25)
    assert len(X_train) == 150
    assert len(X_test) == 50
    assert len(y_train) == 150
    assert len(y_test) == 50
    assert list(X_train.columns) == [col for col in NUMERIC_FEATURE_NAMES if col in df.columns]


def test_load_dataset_fallback():
    df = load_dataset()
    assert isinstance(df, pd.DataFrame)
    assert len(df) > 0
