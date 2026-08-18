"""Tests for orchestrator.graph — pipeline executor and state transitions."""


import json
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from orchestrator.error_handling import NoCriticalDataError
from orchestrator.graph import run_pipeline


def _load_example_loan_file():
    """Load the golden test fixture."""
    fixture = Path(__file__).resolve().parent.parent.parent / "schema" / "loan_file.example.json"
    with open(fixture, "r", encoding="utf-8") as f:
        return json.load(f)


class TestRunPipelineWithMocks:
    """Test pipeline flow with mocked node adapters."""

    @patch("orchestrator.nodes.summary.run_summary")
    @patch("orchestrator.nodes.risk.run_risk_assessment")
    @patch("orchestrator.nodes.validation.run_validation")
    @patch("orchestrator.nodes.extraction.run_extraction")
    def test_full_pipeline_with_pre_ingested_data(
        self, mock_extract, mock_validate, mock_risk, mock_summary,
    ):
        """Pipeline should run through all stages with pre-ingested data."""
        lf = _load_example_loan_file()

        # Mocks return the loan_file as-is (data already populated)
        mock_extract.side_effect = lambda x: x
        mock_validate.side_effect = lambda x: x
        mock_risk.side_effect = lambda x: x
        mock_summary.side_effect = lambda x: x

        result = run_pipeline(lf)

        assert result["status"] in (
            "ready_for_review", "approved", "rejected", "more_docs_requested",
        )
        assert len(result.get("audit_log", [])) > 0
        assert "_pipeline_results" in result

    @patch("orchestrator.nodes.summary.run_summary")
    @patch("orchestrator.nodes.risk.run_risk_assessment")
    @patch("orchestrator.nodes.validation.run_validation")
    @patch("orchestrator.nodes.extraction.run_extraction")
    def test_pipeline_records_all_stages(
        self, mock_extract, mock_validate, mock_risk, mock_summary,
    ):
        """Each stage should produce a StageResult."""
        lf = _load_example_loan_file()
        mock_extract.side_effect = lambda x: x
        mock_validate.side_effect = lambda x: x
        mock_risk.side_effect = lambda x: x
        mock_summary.side_effect = lambda x: x

        result = run_pipeline(lf)

        stages = result.get("_pipeline_results", [])
        stage_names = [s["stage_name"] for s in stages]
        assert "ingestion" in stage_names
        assert "extraction" in stage_names
        assert "validation" in stage_names
        assert "risk_assessment" in stage_names
        assert "decision" in stage_names
        assert "summary" in stage_names

    def test_pipeline_stops_on_empty_documents(self):
        """Pipeline should fail early if no documents are present."""
        lf = {
            "application_id": "APP-EMPTY",
            "created_at": "2026-01-01T00:00:00Z",
            "status": "ingested",
            "documents": [],
            "audit_log": [],
        }

        result = run_pipeline(lf)

        # Should be marked as failed
        assert "failed" in result.get("status", "").lower() or any(
            s.get("status") == "failed"
            for s in result.get("_pipeline_results", [])
        )

    @patch("orchestrator.nodes.summary.run_summary")
    @patch("orchestrator.nodes.risk.run_risk_assessment")
    @patch("orchestrator.nodes.validation.run_validation")
    @patch("orchestrator.nodes.extraction.run_extraction")
    def test_extraction_failure_continues_if_fields_exist(
        self, mock_extract, mock_validate, mock_risk, mock_summary,
    ):
        """If extraction fails but fields already exist, pipeline continues."""
        lf = _load_example_loan_file()

        def failing_extract(loan_file):
            raise RuntimeError("Grok API timeout")

        mock_extract.side_effect = failing_extract
        mock_validate.side_effect = lambda x: x
        mock_risk.side_effect = lambda x: x
        mock_summary.side_effect = lambda x: x

        result = run_pipeline(lf)

        # Should still have results (pipeline didn't hard-stop)
        assert "_pipeline_results" in result
        stages = result["_pipeline_results"]
        extraction = next(s for s in stages if s["stage_name"] == "extraction")
        assert extraction["status"] in ("failed", "partial_failure")

    @patch("orchestrator.nodes.summary.run_summary")
    @patch("orchestrator.nodes.risk.run_risk_assessment")
    @patch("orchestrator.nodes.validation.run_validation")
    @patch("orchestrator.nodes.extraction.run_extraction")
    def test_validation_failure_is_non_critical(
        self, mock_extract, mock_validate, mock_risk, mock_summary,
    ):
        """Validation failure should not stop the pipeline."""
        lf = _load_example_loan_file()
        mock_extract.side_effect = lambda x: x
        mock_validate.side_effect = RuntimeError("validation crash")
        mock_risk.side_effect = lambda x: x
        mock_summary.side_effect = lambda x: x

        result = run_pipeline(lf)

        # Pipeline should still complete
        assert result.get("_pipeline_results") is not None
        stages = result["_pipeline_results"]
        val_result = next(s for s in stages if s["stage_name"] == "validation")
        assert val_result["status"] in ("failed", "partial_failure")

    @patch("orchestrator.nodes.summary.run_summary")
    @patch("orchestrator.nodes.risk.run_risk_assessment")
    @patch("orchestrator.nodes.validation.run_validation")
    @patch("orchestrator.nodes.extraction.run_extraction")
    def test_risk_failure_is_non_critical(
        self, mock_extract, mock_validate, mock_risk, mock_summary,
    ):
        """Risk failure should not stop the pipeline."""
        lf = _load_example_loan_file()
        mock_extract.side_effect = lambda x: x
        mock_validate.side_effect = lambda x: x
        mock_risk.side_effect = RuntimeError("model not found")
        mock_summary.side_effect = lambda x: x

        result = run_pipeline(lf)

        assert result.get("_pipeline_results") is not None
        # Should be flagged for review due to stage failure
        assert result.get("_review_reasons") is not None

    @patch("orchestrator.nodes.summary.run_summary")
    @patch("orchestrator.nodes.risk.run_risk_assessment")
    @patch("orchestrator.nodes.validation.run_validation")
    @patch("orchestrator.nodes.extraction.run_extraction")
    def test_stage_failures_trigger_review(
        self, mock_extract, mock_validate, mock_risk, mock_summary,
    ):
        """Any stage failure should add to review reasons."""
        lf = _load_example_loan_file()
        mock_extract.side_effect = lambda x: x
        mock_validate.side_effect = RuntimeError("crash")
        mock_risk.side_effect = lambda x: x
        mock_summary.side_effect = lambda x: x

        result = run_pipeline(lf)

        review_reasons = result.get("_review_reasons", [])
        assert any("failure" in r.lower() or "failed" in r.lower() for r in review_reasons)
