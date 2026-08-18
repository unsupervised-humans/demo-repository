import pytest
from risk.compliance import ComplianceAgent, run_compliance_check
from shared.schema_loader import validate_loan_file


def test_compliance_clean_features():
    agent = ComplianceAgent()
    features = ["income_to_loan_ratio", "deposit_consistency", "min_extraction_confidence"]
    report = agent.check_features(features)

    assert report["bias_check_passed"] is True
    assert "gender" in report["protected_attributes_excluded"]
    assert "religion" in report["protected_attributes_excluded"]
    assert "caste" in report["protected_attributes_excluded"]
    assert "age" in report["protected_attributes_excluded"]
    assert "no protected attributes" in report["notes"]


def test_compliance_violation_detection():
    agent = ComplianceAgent()
    features = ["income_to_loan_ratio", "applicant_gender", "age"]
    report = agent.check_features(features)

    assert report["bias_check_passed"] is False
    assert "Compliance violation" in report["notes"]


def test_run_compliance_check_on_loan_file():
    loan_file = {
        "extracted_fields": [
            {"field_name": "gross_monthly_income", "value": 50000},
            {"field_name": "employer_name", "value": "Acme Corp"},
        ]
    }
    report = run_compliance_check(loan_file)
    assert report["bias_check_passed"] is True
    assert len(report["protected_attributes_excluded"]) >= 4
