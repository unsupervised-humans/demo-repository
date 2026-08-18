import json
import pytest
from risk.predict import RiskScoringAgent, process_risk_assessment
from shared.schema_loader import validate_loan_file


@pytest.fixture
def sample_loan_file():
    return {
        "application_id": "APP-2026-TEST",
        "created_at": "2026-08-17T09:00:00Z",
        "status": "scoring",
        "applicant": {
            "name": "Alex Smith",
            "declared_income": 75000,
            "loan_amount_requested": 300000,
            "loan_type": "personal",
        },
        "documents": [
            {
                "doc_id": "doc-01",
                "file_path": "uploads/doc-01.pdf",
                "type": "payslip",
                "classification_confidence": 0.98,
                "page_count": 1,
            }
        ],
        "extracted_fields": [
            {
                "field_name": "gross_monthly_income",
                "value": 75000,
                "confidence": 0.95,
                "source": {"doc_id": "doc-01", "page": 1},
                "needs_review": False,
            }
        ],
        "validation_findings": [],
        "missing_documents": [],
        "fraud_flags": [],
        "audit_log": [],
    }


def test_risk_scoring_agent(sample_loan_file):
    agent = RiskScoringAgent()
    score_dict = agent.score_loan_file(sample_loan_file)

    assert "approval_probability" in score_dict
    assert 0.0 <= score_dict["approval_probability"] <= 1.0
    assert "model_version" in score_dict
    assert "factors" in score_dict
    assert isinstance(score_dict["factors"], list)


def test_process_risk_assessment_schema_compliance(sample_loan_file):
    result = process_risk_assessment(sample_loan_file)

    assert result["risk_score"] is not None
    assert result["compliance"] is not None
    assert result["compliance"]["bias_check_passed"] is True

    # Audit log check
    audit_agents = [entry["agent"] for entry in result["audit_log"]]
    assert "risk_scoring" in audit_agents
    assert "compliance" in audit_agents

    # Validate against JSON schema
    validate_loan_file(result)
