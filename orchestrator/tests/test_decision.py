"""Tests for orchestrator.agents.decision — the Decision/Policy Agent."""

import pytest

from orchestrator.agents.decision import evaluate_decision


def _make_loan_file(**overrides):
    """Create a minimal loan_file with defaults and optional overrides."""
    lf = {
        "extracted_fields": [],
        "missing_documents": [],
        "fraud_flags": [],
        "validation_findings": [],
        "risk_score": {"approval_probability": 0.85},
        "compliance": {"bias_check_passed": True, "notes": "All clear"},
    }
    lf.update(overrides)
    return lf


class TestEvaluateDecision:
    """Tests for the holistic decision agent."""

    def test_clean_high_prob_approves(self):
        lf = _make_loan_file(risk_score={"approval_probability": 0.90})
        result = evaluate_decision(lf)
        assert result["recommendation"] == "approve"
        assert result["needs_review"] is False

    def test_low_prob_rejects(self):
        lf = _make_loan_file(risk_score={"approval_probability": 0.20})
        result = evaluate_decision(lf)
        assert result["recommendation"] == "reject"
        assert result["needs_review"] is True

    def test_mid_prob_sends_to_review(self):
        lf = _make_loan_file(risk_score={"approval_probability": 0.55})
        result = evaluate_decision(lf)
        assert result["needs_review"] is True

    def test_missing_docs_requests_more_info(self):
        lf = _make_loan_file(
            missing_documents=[{"document_type": "tax_return", "reason": "Required"}]
        )
        result = evaluate_decision(lf)
        assert result["recommendation"] == "request_more_info"
        assert result["needs_review"] is True

    def test_high_fraud_forces_review(self):
        lf = _make_loan_file(
            fraud_flags=[{"severity": "high", "description": "Tampered payslip"}]
        )
        result = evaluate_decision(lf)
        assert result["needs_review"] is True
        assert any("fraud" in r.lower() for r in result["reasons"])

    def test_low_fraud_still_flags_review(self):
        lf = _make_loan_file(
            fraud_flags=[{"severity": "low", "description": "Minor inconsistency"}]
        )
        result = evaluate_decision(lf)
        assert result["needs_review"] is True

    def test_compliance_failure_forces_review(self):
        lf = _make_loan_file(
            compliance={"bias_check_passed": False, "notes": "Protected attribute used"}
        )
        result = evaluate_decision(lf)
        assert result["needs_review"] is True
        assert any("compliance" in r.lower() or "bias" in r.lower() for r in result["reasons"])

    def test_critical_findings_force_review(self):
        lf = _make_loan_file(
            validation_findings=[
                {"severity": "critical", "description": "Name mismatch"},
            ]
        )
        result = evaluate_decision(lf)
        assert result["needs_review"] is True

    def test_low_confidence_fields_force_review(self):
        lf = _make_loan_file(
            extracted_fields=[
                {"field_name": "id_expiry", "needs_review": True, "confidence": 0.4},
            ]
        )
        result = evaluate_decision(lf)
        assert result["needs_review"] is True
        assert any("confidence" in r.lower() for r in result["reasons"])

    def test_no_risk_score_uses_default(self):
        lf = _make_loan_file(risk_score=None)
        result = evaluate_decision(lf)
        # With default prob=0.5, should be in review band
        assert result["needs_review"] is True

    def test_multiple_issues_accumulate_reasons(self):
        lf = _make_loan_file(
            fraud_flags=[{"severity": "high", "description": "Fraud"}],
            validation_findings=[{"severity": "critical", "description": "Mismatch"}],
            extracted_fields=[{"field_name": "x", "needs_review": True, "confidence": 0.3}],
        )
        result = evaluate_decision(lf)
        assert result["needs_review"] is True
        assert len(result["reasons"]) >= 3
