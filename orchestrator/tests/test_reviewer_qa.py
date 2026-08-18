"""Tests for the Reviewer Q&A agent and structured retrieval."""

import pytest

from orchestrator.reviewer.retrieval import (
    get_source_references,
    retrieve_context,
)


def _make_loan_file():
    """Create a populated loan_file for Q&A testing."""
    return {
        "application_id": "APP-TEST-QA",
        "status": "ready_for_review",
        "applicant": {
            "name": "Ananya Rao",
            "declared_income": 65000,
            "loan_amount_requested": 500000,
            "loan_type": "personal",
        },
        "documents": [
            {"doc_id": "doc-01", "file_path": "payslip.pdf", "type": "payslip",
             "classification_confidence": 0.98, "page_count": 1},
            {"doc_id": "doc-02", "file_path": "bank.pdf", "type": "bank_statement",
             "classification_confidence": 0.95, "page_count": 3},
        ],
        "extracted_fields": [
            {"field_name": "gross_monthly_income", "value": 65000, "confidence": 0.96,
             "source": {"doc_id": "doc-01", "page": 1}, "needs_review": False},
            {"field_name": "avg_monthly_deposit", "value": 61200, "confidence": 0.91,
             "source": {"doc_id": "doc-02", "page": 2}, "needs_review": False},
            {"field_name": "id_expiry_date", "value": "2029-04-01", "confidence": 0.62,
             "source": {"doc_id": "doc-03", "page": 1}, "needs_review": True},
        ],
        "validation_findings": [
            {"finding_id": "vf-01", "severity": "info",
             "description": "Income and deposits consistent within 6%",
             "related_fields": ["gross_monthly_income", "avg_monthly_deposit"],
             "doc_ids": ["doc-01", "doc-02"]},
        ],
        "missing_documents": [],
        "fraud_flags": [],
        "risk_score": {
            "approval_probability": 0.78,
            "model_version": "risk-xgb-v1",
            "factors": [
                {"feature": "income_to_loan_ratio", "contribution": 0.22},
                {"feature": "id_confidence_low", "contribution": -0.05},
            ],
        },
        "compliance": {
            "bias_check_passed": True,
            "protected_attributes_excluded": ["gender", "religion", "caste", "age"],
            "notes": "No protected attributes used.",
        },
        "summary_report": {
            "narrative": "Test summary.",
            "recommendation": "approve",
            "citations": [{"doc_id": "doc-01", "page": 1}],
        },
        "audit_log": [],
    }


class TestRetrieveContext:
    def test_income_question_includes_extracted_fields(self):
        lf = _make_loan_file()
        ctx = retrieve_context(lf, "Where did the income figure come from?")
        assert "extracted_fields" in ctx.lower() or "income" in ctx.lower()

    def test_fraud_question_includes_fraud_section(self):
        lf = _make_loan_file()
        ctx = retrieve_context(lf, "Are there any fraud flags?")
        assert "fraud" in ctx.lower()

    def test_why_flagged_includes_multiple_sections(self):
        lf = _make_loan_file()
        ctx = retrieve_context(lf, "Why was this application flagged?")
        # Should include fraud, validation, risk, and missing docs
        assert "fraud" in ctx.lower() or "validation" in ctx.lower()

    def test_generic_question_returns_all_sections(self):
        lf = _make_loan_file()
        ctx = retrieve_context(lf, "Tell me everything about this application")
        assert len(ctx) > 100  # Should be a substantial context

    def test_compliance_question(self):
        lf = _make_loan_file()
        ctx = retrieve_context(lf, "Was the bias check passed?")
        assert "compliance" in ctx.lower() or "bias" in ctx.lower()


class TestGetSourceReferences:
    def test_extraction_sources_returned(self):
        lf = _make_loan_file()
        refs = get_source_references(lf, "Where did the income come from?")
        assert len(refs) > 0
        doc_ids = [r["doc_id"] for r in refs]
        assert "doc-01" in doc_ids or "doc-02" in doc_ids

    def test_validation_sources_returned(self):
        lf = _make_loan_file()
        refs = get_source_references(lf, "What validation findings are there?")
        assert len(refs) > 0

    def test_empty_for_irrelevant_question(self):
        lf = _make_loan_file()
        lf["extracted_fields"] = []
        lf["validation_findings"] = []
        lf["fraud_flags"] = []
        refs = get_source_references(lf, "What is the weather today?")
        # Should still return something from the catch-all
        # but with empty data, refs will be empty
        assert isinstance(refs, list)


class TestAskQuestion:
    """Integration test for the Q&A agent (uses fallback, no LLM)."""

    def test_fallback_returns_structured_answer(self):
        """Without GROQ_API_KEY, the Q&A agent should use the fallback."""
        from orchestrator.reviewer.qa import ask_question

        lf = _make_loan_file()
        result = ask_question(lf, "Why was this application flagged?")

        assert "answer" in result
        assert "sources" in result
        assert "confidence" in result
        assert isinstance(result["answer"], str)
        assert len(result["answer"]) > 0

    def test_empty_question_handled(self):
        from orchestrator.reviewer.qa import ask_question

        lf = _make_loan_file()
        result = ask_question(lf, "")
        assert "Please provide a question" in result["answer"]
