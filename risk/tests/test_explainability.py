import pytest
from risk.explain import compute_factor_breakdown
from risk.features import extract_features_from_loan_file
from risk.model import RiskModel


def test_factor_breakdown_structure():
    sample_features = {
        "income_to_loan_ratio": 0.25,
        "deposit_consistency": 0.95,
        "min_extraction_confidence": 0.98,
        "critical_findings_count": 0.0,
        "fraud_flags_count": 0.0,
    }

    factors = compute_factor_breakdown(
        model=None,
        feature_dict=sample_features,
        top_n=3,
    )

    assert isinstance(factors, list)
    assert len(factors) <= 3
    for f in factors:
        assert "feature" in f
        assert "contribution" in f
        assert isinstance(f["contribution"], float)

    # Check sorted descending by absolute contribution
    abs_contribs = [abs(f["contribution"]) for f in factors]
    assert abs_contribs == sorted(abs_contribs, reverse=True)


def test_factor_breakdown_with_trained_model():
    from risk.dataset import generate_synthetic_loan_dataset, get_train_test_data

    df = generate_synthetic_loan_dataset(n_samples=100, random_state=42)
    X_train, X_test, y_train, y_test = get_train_test_data(df)

    model = RiskModel(model_version="risk-explain-test")
    model.fit(X_train, y_train)

    sample_dict = X_test.iloc[0].to_dict()
    factors = compute_factor_breakdown(
        model=model,
        feature_dict=sample_dict,
        feature_names=model.feature_names,
        top_n=5,
    )

    assert len(factors) > 0
    abs_contribs = [abs(f["contribution"]) for f in factors]
    assert abs_contribs == sorted(abs_contribs, reverse=True)
