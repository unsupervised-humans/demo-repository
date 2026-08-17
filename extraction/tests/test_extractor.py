"""extraction/tests/test_extractor.py
Unit tests for extraction.extractor.

Covers:
- Successful extraction (mocked model)
- Low-confidence extraction → needs_review=True
- Malformed model output (invalid JSON)
- Unsupported document type → falls back gracefully
- Empty documents list → no crash
- Missing source (page fallback)
- Audit log entries are appended with correct agent name and schema shape
- extract_fields returns a valid loan_file structure

The Grok model is mocked via unittest.mock so no real API key is needed.
"""

from __future__ import annotations

import json
from unittest.mock import MagicMock, patch

import pytest

from extraction.extractor import AGENT_NAME, extract_fields


# ── Test helpers ──────────────────────────────────────────────────────────────

def _make_loan_file(documents: list[dict]) -> dict:
    return {
        "application_id": "APP-TEST-001",
        "created_at": "2026-08-17T09:00:00Z",
        "status": "extracting",
        "documents": documents,
        "extracted_fields": [],
        "audit_log": [],
    }


def _model_response(fields: list[dict]) -> MagicMock:
    """Create a mock OpenAI response object containing *fields* as JSON."""
    content = json.dumps({"fields": fields})
    mock_choice = MagicMock()
    mock_choice.message.content = content
    mock_response = MagicMock()
    mock_response.choices = [mock_choice]
    return mock_response


def _patch_model(mock_response: MagicMock):
    """Context manager: patches get_llm_client so no real API is called."""
    mock_client = MagicMock()
    mock_client.chat.completions.create.return_value = mock_response
    return patch("extraction.extractor.get_llm_client", return_value=mock_client)


# ── Tests ─────────────────────────────────────────────────────────────────────

class TestSuccessfulExtraction:
    def test_basic_payslip(self):
        doc = {
            "doc_id": "doc-01",
            "file_path": "",
            "type": "payslip",
            "classification_confidence": 0.98,
        }
        loan_file = _make_loan_file([doc])

        mock_resp = _model_response([
            {
                "field_name": "employer_name",
                "value": "Acme Corp",
                "confidence": 0.95,
                "page": 1,
                "bbox": [0.1, 0.2, 0.3, 0.04],
            },
            {
                "field_name": "gross_monthly_income",
                "value": 80000,
                "confidence": 0.92,
                "page": 1,
                "bbox": None,
            },
        ])

        with _patch_model(mock_resp):
            result = extract_fields(loan_file)

        fields = result["extracted_fields"]
        assert len(fields) == 2

        employer = next(f for f in fields if f["field_name"] == "employer_name")
        assert employer["value"] == "Acme Corp"
        assert employer["confidence"] == pytest.approx(0.95)
        assert employer["needs_review"] is False
        assert employer["source"]["doc_id"] == "doc-01"
        assert employer["source"]["page"] == 1
        assert employer["source"]["bbox"] == pytest.approx([0.1, 0.2, 0.3, 0.04])

        income = next(f for f in fields if f["field_name"] == "gross_monthly_income")
        assert income["value"] == 80000
        assert "bbox" not in income["source"]

    def test_multi_document(self):
        docs = [
            {"doc_id": "doc-01", "file_path": "", "type": "payslip", "classification_confidence": 0.95},
            {"doc_id": "doc-02", "file_path": "", "type": "bank_statement", "classification_confidence": 0.90},
        ]
        loan_file = _make_loan_file(docs)

        payslip_resp = _model_response([
            {"field_name": "employer_name", "value": "TestCo", "confidence": 0.88, "page": 1, "bbox": None},
        ])
        bank_resp = _model_response([
            {"field_name": "avg_monthly_deposit", "value": 60000, "confidence": 0.85, "page": 2, "bbox": None},
        ])

        mock_client = MagicMock()
        mock_client.chat.completions.create.side_effect = [payslip_resp, bank_resp]

        with patch("extraction.extractor.get_llm_client", return_value=mock_client):
            result = extract_fields(loan_file)

        assert len(result["extracted_fields"]) == 2
        doc_ids = {f["source"]["doc_id"] for f in result["extracted_fields"]}
        assert doc_ids == {"doc-01", "doc-02"}


class TestLowConfidenceExtraction:
    def test_low_confidence_sets_needs_review(self):
        doc = {"doc_id": "doc-03", "file_path": "", "type": "kyc_id", "classification_confidence": 0.99}
        loan_file = _make_loan_file([doc])

        mock_resp = _model_response([
            {"field_name": "id_expiry_date", "value": "2028-01-01", "confidence": 0.55, "page": 1, "bbox": None},
        ])

        with _patch_model(mock_resp):
            result = extract_fields(loan_file)

        field = result["extracted_fields"][0]
        assert field["needs_review"] is True
        assert field["confidence"] == pytest.approx(0.55)

    def test_exactly_at_threshold_no_review(self):
        doc = {"doc_id": "doc-04", "file_path": "", "type": "payslip", "classification_confidence": 0.90}
        loan_file = _make_loan_file([doc])

        mock_resp = _model_response([
            {"field_name": "net_monthly_income", "value": 50000, "confidence": 0.70, "page": 1, "bbox": None},
        ])

        with _patch_model(mock_resp):
            result = extract_fields(loan_file)

        field = result["extracted_fields"][0]
        assert field["needs_review"] is False
        assert field["confidence"] == pytest.approx(0.70)


class TestMalformedModelOutput:
    def test_invalid_json_produces_failure_sentinel(self):
        doc = {"doc_id": "doc-05", "file_path": "", "type": "payslip", "classification_confidence": 0.9}
        loan_file = _make_loan_file([doc])

        mock_choice = MagicMock()
        mock_choice.message.content = "This is not JSON at all!"
        mock_response = MagicMock()
        mock_response.choices = [mock_choice]

        with _patch_model(mock_response):
            result = extract_fields(loan_file)

        fields = result["extracted_fields"]
        assert len(fields) == 1
        sentinel = fields[0]
        assert sentinel["confidence"] == 0.0
        assert sentinel["needs_review"] is True
        assert sentinel["value"] is None

    def test_json_missing_fields_key_produces_sentinel(self):
        doc = {"doc_id": "doc-06", "file_path": "", "type": "bank_statement", "classification_confidence": 0.9}
        loan_file = _make_loan_file([doc])

        mock_choice = MagicMock()
        mock_choice.message.content = json.dumps({"result": []})  # wrong key
        mock_response = MagicMock()
        mock_response.choices = [mock_choice]

        with _patch_model(mock_response):
            result = extract_fields(loan_file)

        assert result["extracted_fields"][0]["needs_review"] is True

    def test_field_without_field_name_is_skipped(self):
        doc = {"doc_id": "doc-07", "file_path": "", "type": "payslip", "classification_confidence": 0.9}
        loan_file = _make_loan_file([doc])

        mock_resp = _model_response([
            # missing field_name
            {"value": "mystery", "confidence": 0.9, "page": 1, "bbox": None},
            # valid
            {"field_name": "employer_name", "value": "Acme", "confidence": 0.9, "page": 1, "bbox": None},
        ])

        with _patch_model(mock_resp):
            result = extract_fields(loan_file)

        # Only the valid field should be in output
        fields = result["extracted_fields"]
        assert len(fields) == 1
        assert fields[0]["field_name"] == "employer_name"


class TestUnsupportedDocumentType:
    def test_other_type_uses_generic_prompt_and_succeeds(self):
        """'other' doc type should not crash — uses generic prompt."""
        doc = {"doc_id": "doc-08", "file_path": "", "type": "other", "classification_confidence": 0.6}
        loan_file = _make_loan_file([doc])

        mock_resp = _model_response([
            {"field_name": "some_field", "value": "some_value", "confidence": 0.75, "page": 1, "bbox": None},
        ])

        with _patch_model(mock_resp):
            result = extract_fields(loan_file)

        assert len(result["extracted_fields"]) == 1

    def test_api_error_does_not_crash_loan_file(self):
        """API errors should be caught; other documents should still process."""
        docs = [
            {"doc_id": "doc-bad", "file_path": "", "type": "payslip", "classification_confidence": 0.9},
            {"doc_id": "doc-good", "file_path": "", "type": "bank_statement", "classification_confidence": 0.9},
        ]
        loan_file = _make_loan_file(docs)

        good_resp = _model_response([
            {"field_name": "closing_balance", "value": 50000, "confidence": 0.88, "page": 1, "bbox": None},
        ])

        call_count = 0

        def side_effect(*args, **kwargs):
            nonlocal call_count
            call_count += 1
            if call_count == 1:
                raise TimeoutError("simulated API timeout")
            return good_resp

        mock_client = MagicMock()
        mock_client.chat.completions.create.side_effect = side_effect

        with patch("extraction.extractor.get_llm_client", return_value=mock_client):
            result = extract_fields(loan_file)

        # doc-bad produced a failure sentinel; doc-good produced a real field
        fields = result["extracted_fields"]
        good_field = next(
            (f for f in fields if f["source"]["doc_id"] == "doc-good"), None
        )
        assert good_field is not None
        assert good_field["field_name"] == "closing_balance"


class TestEmptyDocuments:
    def test_no_documents_returns_unchanged(self):
        loan_file = _make_loan_file([])
        result = extract_fields(loan_file)
        assert result["extracted_fields"] == []

    def test_audit_log_entry_added_even_for_empty(self):
        loan_file = _make_loan_file([])
        result = extract_fields(loan_file)
        agents = [e["agent"] for e in result["audit_log"]]
        assert AGENT_NAME in agents


class TestAuditLog:
    def test_audit_entries_have_correct_shape(self):
        doc = {"doc_id": "doc-09", "file_path": "", "type": "kyc_id", "classification_confidence": 0.99}
        loan_file = _make_loan_file([doc])

        mock_resp = _model_response([
            {"field_name": "applicant_name", "value": "Test User", "confidence": 0.98, "page": 1, "bbox": None},
        ])

        with _patch_model(mock_resp):
            result = extract_fields(loan_file)

        for entry in result["audit_log"]:
            assert "agent" in entry
            assert "action" in entry
            assert "timestamp" in entry
            assert entry["agent"] == AGENT_NAME

    def test_audit_log_accumulates(self):
        doc = {"doc_id": "doc-10", "file_path": "", "type": "payslip", "classification_confidence": 0.95}
        loan_file = _make_loan_file([doc])

        mock_resp = _model_response([
            {"field_name": "employer_name", "value": "Corp", "confidence": 0.9, "page": 1, "bbox": None},
        ])

        with _patch_model(mock_resp):
            result = extract_fields(loan_file)

        # Should have: started + per-doc + completed = at least 3 entries
        assert len(result["audit_log"]) >= 3


class TestConfidenceClamping:
    """Ensure model-reported out-of-range confidence is safely clamped."""

    def test_model_over_one_is_clamped(self):
        doc = {"doc_id": "doc-11", "file_path": "", "type": "payslip", "classification_confidence": 0.9}
        loan_file = _make_loan_file([doc])

        mock_resp = _model_response([
            {"field_name": "employer_name", "value": "Corp", "confidence": 1.5, "page": 1, "bbox": None},
        ])

        with _patch_model(mock_resp):
            result = extract_fields(loan_file)

        field = result["extracted_fields"][0]
        assert field["confidence"] <= 1.0

    def test_model_negative_is_clamped(self):
        doc = {"doc_id": "doc-12", "file_path": "", "type": "payslip", "classification_confidence": 0.9}
        loan_file = _make_loan_file([doc])

        mock_resp = _model_response([
            {"field_name": "employer_name", "value": "Corp", "confidence": -0.3, "page": 1, "bbox": None},
        ])

        with _patch_model(mock_resp):
            result = extract_fields(loan_file)

        field = result["extracted_fields"][0]
        assert field["confidence"] >= 0.0
        assert field["needs_review"] is True


class TestReasoningModelOutput:
    """Ensure parsing works when model output includes reasoning thinking blocks."""

    def test_reasoning_tags_are_stripped(self):
        doc = {"doc_id": "doc-reasoning", "file_path": "", "type": "payslip", "classification_confidence": 0.9}
        loan_file = _make_loan_file([doc])

        # Mimic output with a <think> block and markdown code block
        raw_output = (
            "<think>\n"
            "I need to extract the employer name from the payslip.\n"
            "</think>\n"
            "```json\n"
            "{\n"
            '  "fields": [\n'
            '    {"field_name": "employer_name", "value": "Reasoning LLC", "confidence": 0.95, "page": 1, "bbox": null}\n'
            "  ]\n"
            "}\n"
            "```"
        )

        mock_choice = MagicMock()
        mock_choice.message.content = raw_output
        mock_response = MagicMock()
        mock_response.choices = [mock_choice]

        with _patch_model(mock_response):
            result = extract_fields(loan_file)

        fields = result["extracted_fields"]
        assert len(fields) == 1
        assert fields[0]["field_name"] == "employer_name"
        assert fields[0]["value"] == "Reasoning LLC"
        assert fields[0]["confidence"] == pytest.approx(0.95)
        assert fields[0]["needs_review"] is False
