import pytest
from risk.features import (
    DEFAULT_FEATURE_VALUES,
    NUMERIC_FEATURE_NAMES,
    extract_features_from_loan_file,
    validate_feature_safety,
)


def test_extract_features_from_sample_with_defaults():
    sample_loan_file = {
        "application_id": "APP-001",
        "applicant": {
            "name": "Jane Doe",
            "declared_income": 60000,  # 60k/month -> 720k/annum
            "loan_amount_requested": 1440000,
        },
        "extracted_fields": [
            {
                "field_name": "gross_monthly_income",
                "value": 60000,
                "confidence": 0.95,
                "needs_review": False,
            },
            {
                "field_name": "avg_monthly_deposit",
                "value": 55000,
                "confidence": 0.90,
                "needs_review": False,
            },
        ],
        "validation_findings": [],
        "fraud_flags": [],
        "documents": [{"doc_id": "d1"}],
    }

    features = extract_features_from_loan_file(sample_loan_file)

    assert isinstance(features, dict)
    assert features["income_annum"] == 720000.0
    assert features["loan_amount"] == 1440000.0
    assert features["loan_to_income_ratio"] == 2.0
    assert features["bank_asset_value"] == 55000 * 12.0

    # Verify defaulted fields
    assert features["cibil_score"] == DEFAULT_FEATURE_VALUES["cibil_score"]
    assert features["residential_assets_value"] == DEFAULT_FEATURE_VALUES["residential_assets_value"]
    assert "data_completeness_note" in features
    assert "cibil_score" in features["data_completeness_note"]


def test_extract_features_with_all_live_fields():
    sample_loan_file = {
        "application_id": "APP-002",
        "applicant": {
            "name": "John Doe",
            "declared_income": 1000000,
            "loan_amount_requested": 2000000,
        },
        "extracted_fields": [
            {"field_name": "annual_income", "value": 1000000},
            {"field_name": "loan_amount", "value": 2000000},
            {"field_name": "cibil_score", "value": 780},
            {"field_name": "education", "value": "Graduate"},
            {"field_name": "self_employed", "value": "No"},
            {"field_name": "no_of_dependents", "value": 1},
            {"field_name": "loan_term", "value": 15},
            {"field_name": "residential_assets_value", "value": 8000000},
            {"field_name": "commercial_assets_value", "value": 4000000},
            {"field_name": "luxury_assets_value", "value": 6000000},
            {"field_name": "bank_asset_value", "value": 3000000},
        ],
    }

    features = extract_features_from_loan_file(sample_loan_file)
    assert features["cibil_score"] == 780.0
    assert features["education"] == 1.0
    assert features["self_employed"] == 0.0
    assert features["no_of_dependents"] == 1.0
    assert features["loan_term"] == 15.0
    assert "All features extracted" in features["data_completeness_note"]


def test_validate_feature_safety_clean():
    clean_features = NUMERIC_FEATURE_NAMES
    violations = validate_feature_safety(clean_features)
    assert violations == []


def test_validate_feature_safety_catches_protected():
    tainted_features = ["income_annum", "applicant_gender", "caste_group", "age_in_years"]
    violations = validate_feature_safety(tainted_features)
    assert "applicant_gender" in violations
    assert "caste_group" in violations
    assert "age_in_years" in violations
    assert "income_annum" not in violations
