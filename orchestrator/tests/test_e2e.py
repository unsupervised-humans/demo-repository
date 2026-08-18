"""End-to-end test using the golden fixture (schema/loan_file.example.json).

This test runs the pipeline against the example fixture with mocked
node adapters, validating that the output conforms to the schema
and all required fields are populated.
"""

import json
from pathlib import Path
from unittest.mock import patch

import pytest

from orchestrator.graph import run_pipeline
from orchestrator.state import apply_reviewer_decision


def _load_example():
    fixture = Path(__file__).resolve().parent.parent.parent / "schema" / "loan_file.example.json"
    with open(fixture, "r", encoding="utf-8") as f:
        return json.load(f)


class TestEndToEnd:
    """End-to-end smoke test with the golden fixture."""

    @patch("orchestrator.nodes.summary.run_summary")
    @patch("orchestrator.nodes.risk.run_risk_assessment")
    @patch("orchestrator.nodes.validation.run_validation")
    @patch("orchestrator.nodes.extraction.run_extraction")
    def test_example_fixture_produces_valid_output(
        self, mock_extract, mock_validate, mock_risk, mock_summary,
    ):
        """Pipeline output should validate against the schema."""
        lf = _load_example()
        mock_extract.side_effect = lambda x: x
        mock_validate.side_effect = lambda x: x
        mock_risk.side_effect = lambda x: x
        mock_summary.side_effect = lambda x: x

        result = run_pipeline(lf)

        # Clean internal fields before schema validation
        result.pop("_pipeline_results", None)
        result.pop("_review_reasons", None)
        result.pop("consistency_graph", None)

        from shared.schema_loader import validate_loan_file
        validate_loan_file(result)  # Should not raise

    @patch("orchestrator.nodes.summary.run_summary")
    @patch("orchestrator.nodes.risk.run_risk_assessment")
    @patch("orchestrator.nodes.validation.run_validation")
    @patch("orchestrator.nodes.extraction.run_extraction")
    def test_all_fields_populated(
        self, mock_extract, mock_validate, mock_risk, mock_summary,
    ):
        """All loan_file top-level keys should be present after pipeline."""
        lf = _load_example()
        mock_extract.side_effect = lambda x: x
        mock_validate.side_effect = lambda x: x
        mock_risk.side_effect = lambda x: x
        mock_summary.side_effect = lambda x: x

        result = run_pipeline(lf)

        assert result.get("application_id")
        assert result.get("status")
        assert result.get("documents")
        assert result.get("extracted_fields") is not None
        assert result.get("audit_log") is not None
        # Summary should be generated (mocked as passthrough, data already exists)
        assert result.get("summary_report") is not None

    @patch("orchestrator.nodes.summary.run_summary")
    @patch("orchestrator.nodes.risk.run_risk_assessment")
    @patch("orchestrator.nodes.validation.run_validation")
    @patch("orchestrator.nodes.extraction.run_extraction")
    def test_audit_log_has_workflow_entries(
        self, mock_extract, mock_validate, mock_risk, mock_summary,
    ):
        """Audit log should have orchestrator entries for workflow lifecycle."""
        lf = _load_example()
        mock_extract.side_effect = lambda x: x
        mock_validate.side_effect = lambda x: x
        mock_risk.side_effect = lambda x: x
        mock_summary.side_effect = lambda x: x

        result = run_pipeline(lf)

        audit = result.get("audit_log", [])
        actions = [e.get("action", "") for e in audit]

        # Should have workflow start and completion
        assert any("workflow started" in a for a in actions)
        assert any("workflow completed" in a for a in actions)

    @patch("orchestrator.nodes.summary.run_summary")
    @patch("orchestrator.nodes.risk.run_risk_assessment")
    @patch("orchestrator.nodes.validation.run_validation")
    @patch("orchestrator.nodes.extraction.run_extraction")
    def test_summary_report_structure(
        self, mock_extract, mock_validate, mock_risk, mock_summary,
    ):
        """Summary report should have narrative, recommendation, citations."""
        lf = _load_example()
        mock_extract.side_effect = lambda x: x
        mock_validate.side_effect = lambda x: x
        mock_risk.side_effect = lambda x: x
        mock_summary.side_effect = lambda x: x

        result = run_pipeline(lf)

        sr = result.get("summary_report")
        assert sr is not None
        assert "narrative" in sr
        assert "recommendation" in sr
        assert sr["recommendation"] in ("approve", "reject", "request_more_info")
        assert "citations" in sr
        assert isinstance(sr["citations"], list)

    @patch("orchestrator.nodes.summary.run_summary")
    @patch("orchestrator.nodes.risk.run_risk_assessment")
    @patch("orchestrator.nodes.validation.run_validation")
    @patch("orchestrator.nodes.extraction.run_extraction")
    def test_reviewer_qa_after_pipeline(
        self, mock_extract, mock_validate, mock_risk, mock_summary,
    ):
        """Reviewer Q&A should work on the pipeline output."""
        lf = _load_example()
        mock_extract.side_effect = lambda x: x
        mock_validate.side_effect = lambda x: x
        mock_risk.side_effect = lambda x: x
        mock_summary.side_effect = lambda x: x

        result = run_pipeline(lf)

        from orchestrator.reviewer.qa import ask_question

        answer = ask_question(result, "Why was this application flagged?")
        assert "answer" in answer
        assert len(answer["answer"]) > 0
        assert "sources" in answer

    @patch("orchestrator.nodes.summary.run_summary")
    @patch("orchestrator.nodes.risk.run_risk_assessment")
    @patch("orchestrator.nodes.validation.run_validation")
    @patch("orchestrator.nodes.extraction.run_extraction")
    def test_status_transitions(
        self, mock_extract, mock_validate, mock_risk, mock_summary,
    ):
        """Pipeline should produce a valid final status."""
        lf = _load_example()
        mock_extract.side_effect = lambda x: x
        mock_validate.side_effect = lambda x: x
        mock_risk.side_effect = lambda x: x
        mock_summary.side_effect = lambda x: x

        result = run_pipeline(lf)

        valid_statuses = {
            "ingested", "classifying", "extracting", "validating",
            "scoring", "ready_for_review", "more_docs_requested",
            "approved", "rejected",
        }
        assert result["status"] in valid_statuses


def test_duplicate_reviewer_decision_is_rejected():
    loan_file = {
        "application_id": "APP-TEST-DUPLICATE",
        "status": "rejected",
        "reviewer_decision": {
            "decision": "rejected",
            "reviewer": "Alex",
            "decided_at": "2026-08-18T10:00:00Z",
            "notes": "",
        },
        "audit_log": [],
    }

    with pytest.raises(ValueError) as exc_info:
        apply_reviewer_decision(
            loan_file,
            decision="rejected",
            reviewer="Alex",
            notes="",
        )

    assert "already marked" in str(exc_info.value)
    assert any(
        "duplicate human review decision ignored" in entry["action"]
        for entry in loan_file["audit_log"]
    )
