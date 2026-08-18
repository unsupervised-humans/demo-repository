import pytest
import pandas as pd
from risk.dataset import (
    generate_synthetic_loan_dataset,
    get_train_test_data,
    load_dataset,
)
from risk.features import NUMERIC_FEATURE_NAMES


def test_load_dataset_real_csv():
    df = load_dataset()
    assert isinstance(df, pd.DataFrame)
    assert len(df) == 4269
    assert "approved" in df.columns
    assert set(df["approved"].unique()).issubset({0, 1})
    assert set(df["education"].unique()).issubset({0.0, 1.0})
    assert set(df["self_employed"].unique()).issubset({0.0, 1.0})
    assert "loan_to_income_ratio" in df.columns
    for col in NUMERIC_FEATURE_NAMES:
        assert col in df.columns


def test_generate_synthetic_loan_dataset():
    df = generate_synthetic_loan_dataset(n_samples=100, random_state=42)
    assert isinstance(df, pd.DataFrame)
    assert len(df) == 100
    assert "approved" in df.columns
    for feature in NUMERIC_FEATURE_NAMES:
        assert feature in df.columns
    assert set(df["approved"].unique()).issubset({0, 1})


def test_get_train_test_data():
    df = load_dataset()
    X_train, X_test, y_train, y_test = get_train_test_data(df, test_size=0.2)
    assert len(X_train) == int(len(df) * 0.8)
    assert len(X_test) == len(df) - len(X_train)
    assert list(X_train.columns) == NUMERIC_FEATURE_NAMES
