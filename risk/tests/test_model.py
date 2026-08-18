import os
import pytest
import numpy as np
import pandas as pd
from risk.dataset import generate_synthetic_loan_dataset, get_train_test_data
from risk.model import RiskModel


def test_model_fit_and_predict():
    df = generate_synthetic_loan_dataset(n_samples=200, random_state=42)
    X_train, X_test, y_train, y_test = get_train_test_data(df)

    model = RiskModel(model_version="risk-test-v1")
    model.fit(X_train, y_train)

    proba = model.predict_proba(X_test)
    assert proba.shape == (len(X_test), 2)
    assert (proba >= 0.0).all() and (proba <= 1.0).all()

    # Single feature dict prediction
    sample_dict = X_test.iloc[0].to_dict()
    prob_single = model.predict_approval_probability(sample_dict)
    assert 0.0 <= prob_single <= 1.0


def test_model_save_and_load(tmp_path):
    df = generate_synthetic_loan_dataset(n_samples=100, random_state=42)
    X_train, X_test, y_train, y_test = get_train_test_data(df)

    model = RiskModel(model_version="risk-test-save")
    model.fit(X_train, y_train)

    save_path = tmp_path / "model.pkl"
    model.save(save_path)
    assert save_path.exists()

    loaded_model = RiskModel.load(save_path)
    assert loaded_model.model_version == "risk-test-save"
    assert loaded_model.feature_names == model.feature_names

    sample_dict = X_test.iloc[0].to_dict()
    orig_prob = model.predict_approval_probability(sample_dict)
    loaded_prob = loaded_model.predict_approval_probability(sample_dict)
    assert np.isclose(orig_prob, loaded_prob, atol=1e-5)
