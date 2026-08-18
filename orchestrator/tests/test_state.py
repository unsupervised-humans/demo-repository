"""Tests for orchestrator.state — workflow states, init, review triggers."""

import pytest

from orchestrator.state import (
    WorkflowStatus,
    initialize_loan_file,
    requires_human_review,
    set_status,
)


class TestInitializeLoanFile:
    """Tests for initialize_loan_file()."""

    def test_creates_valid_structure(self):
        lf = initialize_loan_file("APP-TEST-001")
        assert lf["application_id"] == "APP-TEST-001"
        assert lf["status"] == "ingested"
        assert isinstance(lf["documents"], list)
        assert isinstance(lf["extracted_fields"], list)
        assert isinstance(lf["audit_log"], list)
        assert lf["risk_score"] is None
        assert lf["compliance"] is None
        assert lf["summary_report"] is None
        assert lf["reviewer_decision"] is None

    def test_auto_generates_application_id(self):
        lf = initialize_loan_file()
        assert lf["application_id"].startswith("APP-")
        assert len(lf["application_id"]) > 8

    def test_has_timestamp(self):
        lf = initialize_loan_file()
        assert "T" in lf["created_at"]
        assert lf["created_at"].endswith("Z")

    def test_validates_against_schema(self):
        """The initialized loan_file should pass schema validation."""
        from shared.schema_loader import validate_loan_file
        lf = initialize_loan_file("APP-TEST-SCHEMA")
        # Need at least one document for the schema to be happy
        lf["documents"] = [{
            "doc_id": "doc-01",
            "file_path": "test.pdf",
            "type": "payslip",
            "classification_confidence": 0.95,
            "page_count": 1,
            "is_synthetic": True,
        }]
        validate_loan_file(lf)  # Should not raise


class TestSetStatus:
    """Tests for set_status()."""

    def test_maps_workflow_to_schema(self):
        lf = {"status": "ingested"}
        set_status(lf, WorkflowStatus.EXTRACTING)
        assert lf["status"] == "extracting"

    def test_review_required_maps_correctly(self):
        lf = {"status": "ingested"}
        set_status(lf, WorkflowStatus.REVIEW_REQUIRED)
        assert lf["status"] == "ready_for_review"

    def test_risk_assessment_maps_to_scoring(self):
        lf = {"status": "ingested"}
        set_status(lf, WorkflowStatus.RISK_ASSESSMENT)
        assert lf["status"] == "scoring"


class TestRequiresHumanReview:
    """Tests for requires_human_review()."""

    def test_clean_file_no_review(self):
        lf = {
            "extracted_fields": [
                {"field_name": "income", "confidence": 0.95, "needs_review": False},
            ],
            "missing_documents": [],
            "fraud_flags": [],
            "validation_findings": [],
            "risk_score": {"approval_probability": 0.85},
            "compliance": {"bias_check_passed": True},
            "audit_log": [],
        }
        needs, reasons = requires_human_review(lf)
        assert not needs
        assert len(reasons) == 0

    def test_low_confidence_triggers_review(self):
        lf = {
            "extracted_fields": [
                {"field_name": "id_expiry", "confidence": 0.55, "needs_review": True},
            ],
            "missing_documents": [],
            "fraud_flags": [],
            "validation_findings": [],
            "risk_score": {"approval_probability": 0.90},
            "compliance": {"bias_check_passed": True},
            "audit_log": [],
        }
        needs, reasons = requires_human_review(lf)
        assert needs
        assert any("Low-confidence" in r for r in reasons)

    def test_missing_docs_triggers_review(self):
        lf = {
            "extracted_fields": [],
            "missing_documents": [{"document_type": "tax_return"}],
            "fraud_flags": [],
            "validation_findings": [],
            "risk_score": {"approval_probability": 0.90},
            "compliance": {"bias_check_passed": True},
            "audit_log": [],
        }
        needs, reasons = requires_human_review(lf)
        assert needs
        assert any("Missing" in r for r in reasons)

    def test_fraud_flag_triggers_review(self):
        lf = {
            "extracted_fields": [],
            "missing_documents": [],
            "fraud_flags": [
                {"severity": "high", "description": "Income tampering suspected"},
            ],
            "validation_findings": [],
            "risk_score": {"approval_probability": 0.90},
            "compliance": {"bias_check_passed": True},
            "audit_log": [],
        }
        needs, reasons = requires_human_review(lf)
        assert needs
        assert any("Fraud" in r for r in reasons)

    def test_low_risk_score_triggers_review(self):
        lf = {
            "extracted_fields": [],
            "missing_documents": [],
            "fraud_flags": [],
            "validation_findings": [],
            "risk_score": {"approval_probability": 0.45},
            "compliance": {"bias_check_passed": True},
            "audit_log": [],
        }
        needs, reasons = requires_human_review(lf)
        assert needs
        assert any("Risk score" in r for r in reasons)

    def test_compliance_failure_triggers_review(self):
        lf = {
            "extracted_fields": [],
            "missing_documents": [],
            "fraud_flags": [],
            "validation_findings": [],
            "risk_score": {"approval_probability": 0.90},
            "compliance": {"bias_check_passed": False},
            "audit_log": [],
        }
        needs, reasons = requires_human_review(lf)
        assert needs
        assert any("bias" in r.lower() for r in reasons)

    def test_critical_finding_triggers_review(self):
        lf = {
            "extracted_fields": [],
            "missing_documents": [],
            "fraud_flags": [],
            "validation_findings": [
                {"severity": "critical", "description": "Name mismatch across docs"},
            ],
            "risk_score": {"approval_probability": 0.90},
            "compliance": {"bias_check_passed": True},
            "audit_log": [],
        }
        needs, reasons = requires_human_review(lf)
        assert needs
        assert any("Critical" in r for r in reasons)

    def test_agent_failure_in_audit_triggers_review(self):
        lf = {
            "extracted_fields": [],
            "missing_documents": [],
            "fraud_flags": [],
            "validation_findings": [],
            "risk_score": {"approval_probability": 0.90},
            "compliance": {"bias_check_passed": True},
            "audit_log": [
                {"agent": "extraction", "action": "extraction failed for doc-01", "timestamp": "2026-01-01T00:00:00Z"},
            ],
        }
        needs, reasons = requires_human_review(lf)
        assert needs
        assert any("failure" in r.lower() for r in reasons)
