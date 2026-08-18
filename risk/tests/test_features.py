import pytest
from risk.features import (
    NUMERIC_FEATURE_NAMES,
    PROTECTED_ATTRIBUTES,
    extract_features_from_loan_file,
    validate_feature_safety,
)


def test_extract_features_from_sample():
    sample_loan_file = {
        "application_id": "APP-001",
        "applicant": {
            "name": "Jane Doe",
            "declared_income": 80000,
            "loan_amount_requested": 400000,
        },
        "extracted_fields": [
            {
                "field_name": "gross_monthly_income",
                "value": 80000,
                "confidence": 0.95,
                "needs_review": False,
            },
            {
                "field_name": "avg_monthly_deposit",
                "value": 78000,
                "confidence": 0.90,
                "needs_review": False,
            },
        ],
        "validation_findings": [
            {"finding_id": "vf-1", "severity": "info", "description": "Good consistency"}
        ],
        "fraud_flags": [],
        "documents": [{"doc_id": "d1"}],
    }

    features = extract_features_from_loan_file(sample_loan_file)

    assert isinstance(features, dict)
    assert features["declared_income"] == 80000.0
    assert features["loan_amount_requested"] == 400000.0
    assert features["income_to_loan_ratio"] == 0.2
    assert features["critical_findings_count"] == 0.0
    assert features["total_findings_count"] == 1.0
    assert features["fraud_flags_count"] == 0.0
    assert features["documents_count"] == 1.0


def test_validate_feature_safety_clean():
    clean_features = NUMERIC_FEATURE_NAMES
    violations = validate_feature_safety(clean_features)
    assert violations == []


def test_validate_feature_safety_catches_protected():
    tainted_features = ["declared_income", "applicant_gender", "caste_group", "age_in_years"]
    violations = validate_feature_safety(tainted_features)
    assert "applicant_gender" in violations
    assert "caste_group" in violations
    assert "age_in_years" in violations
    assert "declared_income" not in violations
