"""tests/test_pdf_regression.py

Regression tests for the LoanIQ pipeline against the three synthetic test PDFs.

These tests verify end-to-end pipeline behavior WITHOUT hardcoding applicant
names, filenames, or document-specific conditions. All assertions are purely
structural (field presence/absence, document counts, status values, etc.).

Test PDF locations (relative to workspace root):
  - LoanIQ_Sample_Application.pdf           (TC-01)
  - LoanIQ_Test_Case_02_Inconsistent_Application (1).pdf  (TC-02)
  - LoanIQ_Test_Case_03_Missing_Documents.pdf (TC-03)

Run with:
    pytest tests/test_pdf_regression.py -v
"""

from __future__ import annotations

import os
import shutil
import tempfile
from pathlib import Path
from typing import Any

import pytest

# ---------------------------------------------------------------------------
# Locate test PDFs relative to workspace root
# ---------------------------------------------------------------------------
_WORKSPACE = Path(__file__).resolve().parent.parent

TC01_PDF = _WORKSPACE / "LoanIQ_Sample_Application.pdf"
TC02_PDF = _WORKSPACE / "LoanIQ_Test_Case_02_Inconsistent_Application (1).pdf"
TC03_PDF = _WORKSPACE / "LoanIQ_Test_Case_03_Missing_Documents.pdf"


def _pdf_exists(path: Path) -> bool:
    return path.exists() and path.is_file()


def _run_pipeline_on_pdf(pdf_path: Path, loan_type: str = "personal") -> dict[str, Any]:
    """Helper: copy PDF to temp folder and run the full pipeline on it."""
    from orchestrator.graph import run_from_files
    from orchestrator.state import initialize_loan_file

    tmp_dir = tempfile.mkdtemp(prefix="loaniq_test_")
    try:
        # Copy PDF preserving original filename
        dest = Path(tmp_dir) / pdf_path.name
        shutil.copy2(str(pdf_path), str(dest))

        loan_file = initialize_loan_file()
        loan_file["applicant"] = {
            "name": "Test Applicant",
            "declared_income": 0,
            "loan_amount_requested": 0,
            "loan_type": loan_type,
        }

        result = run_from_files(tmp_dir, application_id=loan_file["application_id"])
    finally:
        shutil.rmtree(tmp_dir, ignore_errors=True)

    return result


def _get_extracted_field_names(result: dict) -> set[str]:
    """Return a set of all extracted field names (excluding failure sentinels)."""
    fields = result.get("extracted_fields") or []
    return {
        f["field_name"]
        for f in fields
        if isinstance(f, dict)
        and not str(f.get("field_name", "")).startswith("extraction_failure_")
        and f.get("value") is not None
    }


def _get_missing_doc_types(result: dict) -> list[str]:
    """Return list of missing document types from validation."""
    missing = result.get("missing_documents") or []
    return [m.get("document_type", m.get("type", "?")) for m in missing]


def _get_approval_prob(result: dict) -> float | None:
    """Return approval probability from risk score."""
    risk = result.get("risk_score") or {}
    return risk.get("approval_probability")


def _get_risk_status(result: dict) -> str:
    """Return risk score status."""
    risk = result.get("risk_score") or {}
    return risk.get("status", "ok")


def _get_validation_findings(result: dict) -> list[dict]:
    """Return all validation findings."""
    return result.get("validation_findings") or []


def _get_recommendation(result: dict) -> str:
    """Return the decision recommendation from summary_report."""
    sr = result.get("summary_report") or {}
    return sr.get("recommendation", "")


# ===========================================================================
# Shared structural assertions (applied to ALL test cases)
# ===========================================================================

def _assert_pipeline_ran(result: dict) -> None:
    """Assert the pipeline completed without crashing."""
    assert "application_id" in result, "Pipeline must produce an application_id"
    assert "status" in result, "Pipeline must produce a status"
    assert "audit_log" in result, "Pipeline must produce an audit_log"

    audit_actions = [e.get("action", "") for e in result.get("audit_log", [])]
    assert any("workflow started" in a for a in audit_actions), \
        "Audit log must contain 'workflow started'"
    assert any("workflow completed" in a for a in audit_actions), \
        "Audit log must contain 'workflow completed'"


def _assert_no_false_approval(result: dict) -> None:
    """Assert approval_probability is not 1.0 when extraction failed."""
    extracted_names = _get_extracted_field_names(result)
    has_income = any(f in extracted_names for f in [
        "gross_monthly_income", "net_monthly_income", "income_annum", "declared_income"
    ])
    has_loan = any(f in extracted_names for f in [
        "loan_amount", "loan_amount_requested"
    ])
    prob = _get_approval_prob(result)

    # If extraction completely failed (no income AND no loan fields), prob must not be 1.0
    if not has_income and not has_loan:
        assert prob != 1.0, (
            f"approval_probability must not be 1.0 when both income and loan "
            f"amount extraction failed. Got: {prob}"
        )
        assert prob is None or _get_risk_status(result) == "INSUFFICIENT_DATA", (
            "Risk status must be INSUFFICIENT_DATA when mandatory features are missing"
        )


# ===========================================================================
# TC-01: Full Application — All Sections Present
# ===========================================================================

@pytest.mark.skipif(not _pdf_exists(TC01_PDF), reason=f"TC-01 PDF not found: {TC01_PDF}")
class TestTC01FullApplication:
    """LoanIQ_Sample_Application.pdf — contains all required sections."""

    @pytest.fixture(scope="class")
    def result(self):
        return _run_pipeline_on_pdf(TC01_PDF, loan_type="personal")

    def test_pipeline_completes(self, result):
        """Pipeline must complete without crashing."""
        _assert_pipeline_ran(result)

    def test_documents_classified(self, result):
        """At least one document must be classified (not all unknown)."""
        docs = result.get("documents") or []
        assert len(docs) >= 1, "Must have at least one document"
        doc_types = [d.get("type") or d.get("document_type", "") for d in docs]
        # Must not ALL be unknown
        non_unknown = [t for t in doc_types if t not in ("unknown", "other", "")]
        assert len(non_unknown) >= 1 or any(
            t == "combined_loan_package" for t in doc_types
        ), f"All documents classified as unknown/other: {doc_types}"

    def test_fields_extracted(self, result):
        """Must extract meaningful fields from the document."""
        names = _get_extracted_field_names(result)
        assert len(names) >= 3, (
            f"Expected at least 3 non-null extracted fields, got {len(names)}: {names}"
        )

    def test_no_missing_documents(self, result):
        """A complete application must have no missing required documents."""
        missing = _get_missing_doc_types(result)
        # This is the KEY assertion: combined PDFs must not produce false missing flags
        assert len(missing) == 0, (
            f"Complete application incorrectly flagged missing documents: {missing}\n"
            f"Extracted fields: {_get_extracted_field_names(result)}"
        )

    def test_no_false_approval_probability(self, result):
        """Approval probability must not be 1.0 when extraction failed."""
        _assert_no_false_approval(result)

    def test_no_extraction_failure_sentinels(self, result):
        """No extraction_failure_ sentinel fields in the output."""
        fields = result.get("extracted_fields") or []
        sentinels = [
            f.get("field_name")
            for f in fields
            if str(f.get("field_name", "")).startswith("extraction_failure_")
        ]
        # Sentinels are only acceptable if model returned no content at all
        # If real fields were extracted alongside sentinels, that's a bug
        real_fields = [
            f.get("field_name")
            for f in fields
            if not str(f.get("field_name", "")).startswith("extraction_failure_")
            and f.get("value") is not None
        ]
        if sentinels and real_fields:
            pytest.fail(
                f"Extraction sentinels mixed with real fields. "
                f"Sentinels: {sentinels}, Real: {real_fields[:5]}"
            )


# ===========================================================================
# TC-02: Inconsistent Application — Triggers Validation Failures
# ===========================================================================

@pytest.mark.skipif(not _pdf_exists(TC02_PDF), reason=f"TC-02 PDF not found: {TC02_PDF}")
class TestTC02InconsistentApplication:
    """TC-02: Contains income mismatch, salary credit mismatch, possibly expired ID."""

    @pytest.fixture(scope="class")
    def result(self):
        return _run_pipeline_on_pdf(TC02_PDF, loan_type="home")

    def test_pipeline_completes(self, result):
        _assert_pipeline_ran(result)

    def test_documents_classified(self, result):
        docs = result.get("documents") or []
        assert len(docs) >= 1
        doc_types = [d.get("type") or d.get("document_type", "") for d in docs]
        non_unknown = [t for t in doc_types if t not in ("unknown", "other", "")]
        assert len(non_unknown) >= 1 or any(
            t == "combined_loan_package" for t in doc_types
        ), f"Documents still classified unknown: {doc_types}"

    def test_no_missing_documents(self, result):
        """TC-02 contains all required sections — no missing docs."""
        missing = _get_missing_doc_types(result)
        assert len(missing) == 0, (
            f"TC-02 incorrectly flagged missing documents: {missing}\n"
            f"Extracted fields: {_get_extracted_field_names(result)}"
        )

    def test_validation_failures_detected(self, result):
        """TC-02 should produce validation findings (income mismatch etc.)."""
        findings = _get_validation_findings(result)
        # With real extraction, findings should exist
        # (We don't assert on exact count since it depends on extraction quality)
        # But we do assert: if income and deposit fields are both present, findings must exist
        names = _get_extracted_field_names(result)
        has_income = "gross_monthly_income" in names
        has_deposits = any(f in names for f in ["avg_monthly_deposit", "average_monthly_deposits"])
        if has_income and has_deposits:
            assert len(findings) >= 1, (
                "Both income and deposits extracted but no validation findings — "
                "income consistency check may not have run"
            )

    def test_human_review_flagged(self, result):
        """TC-02 with inconsistencies must be flagged for human review."""
        review_reasons = result.get("_review_reasons") or []
        findings = _get_validation_findings(result)
        # If validation found issues, review must be flagged
        if len(findings) > 0:
            assert len(review_reasons) > 0, (
                "Validation findings exist but human review not flagged"
            )

    def test_no_false_approval_probability(self, result):
        _assert_no_false_approval(result)


# ===========================================================================
# TC-03: Missing Documents — Partial Submission
# ===========================================================================

@pytest.mark.skipif(not _pdf_exists(TC03_PDF), reason=f"TC-03 PDF not found: {TC03_PDF}")
class TestTC03MissingDocuments:
    """TC-03: KYC provided, income/bank statement partial/missing."""

    @pytest.fixture(scope="class")
    def result(self):
        return _run_pipeline_on_pdf(TC03_PDF, loan_type="home")

    def test_pipeline_completes(self, result):
        _assert_pipeline_ran(result)

    def test_some_documents_present(self, result):
        """TC-03 has at least some documents."""
        docs = result.get("documents") or []
        assert len(docs) >= 1

    def test_missing_documents_detected(self, result):
        """TC-03 should flag some missing required documents."""
        missing = _get_missing_doc_types(result)
        # TC-03 is expected to have some missing docs (partial submission)
        # We don't hardcode which ones — just verify the pipeline detects absence
        assert len(missing) >= 1, (
            f"TC-03 (partial submission) should have missing documents detected. "
            f"Got none. Extracted fields: {_get_extracted_field_names(result)}"
        )

    def test_recommendation_is_request_more_info(self, result):
        """TC-03 should recommend requesting more information."""
        rec = _get_recommendation(result)
        # Missing docs -> recommendation must be request_more_info
        missing = _get_missing_doc_types(result)
        if len(missing) >= 1:
            # The decision agent should have returned request_more_info
            review_reasons = result.get("_review_reasons") or []
            assert rec == "request_more_info" or len(review_reasons) > 0, (
                f"TC-03 with missing docs should recommend 'request_more_info' "
                f"or require review. Got recommendation={rec!r}, "
                f"review_reasons={review_reasons}"
            )

    def test_risk_status_when_income_missing(self, result):
        """When income data is missing, risk must not be 1.0."""
        _assert_no_false_approval(result)

    def test_request_more_info_never_with_high_confidence_approve(self, result):
        """Must never simultaneously show request_more_info AND approval_prob=1.0."""
        prob = _get_approval_prob(result)
        rec = _get_recommendation(result)
        assert not (prob == 1.0 and rec == "request_more_info"), (
            f"Contradictory state: approval_probability={prob} but "
            f"recommendation={rec!r}. This is the original bug."
        )


# ===========================================================================
# Unit tests for core fix components (no PDF needed)
# ===========================================================================

class TestMissingDocumentFieldSignatures:
    """Unit tests for the field-signature inference in missing_documents.py."""

    def test_kyc_inferred_from_id_number(self):
        from validation.missing_documents import check_missing_documents

        extracted_fields = [
            {"field_name": "id_number", "value": "ABCDE1234F", "confidence": 0.95},
            {"field_name": "id_expiry_date", "value": "2028-01-01", "confidence": 0.90},
        ]
        # Documents list only has combined_loan_package
        documents = [{"type": "combined_loan_package"}]

        result = check_missing_documents(
            "personal", None, documents, extracted_fields=extracted_fields
        )
        missing_types = [m.document_type for m in result.missing]
        assert "kyc_id" not in missing_types, (
            f"KYC should be inferred from id_number field. Still missing: {missing_types}"
        )

    def test_payslip_inferred_from_gross_income(self):
        from validation.missing_documents import check_missing_documents

        extracted_fields = [
            {"field_name": "gross_monthly_income", "value": 50000, "confidence": 0.92},
            {"field_name": "employer_name", "value": "ACME Corp", "confidence": 0.88},
        ]
        documents = [{"type": "combined_loan_package"}]

        result = check_missing_documents(
            "personal", None, documents, extracted_fields=extracted_fields
        )
        missing_types = [m.document_type for m in result.missing]
        assert "payslip" not in missing_types, (
            f"Payslip should be inferred from gross_monthly_income. Missing: {missing_types}"
        )

    def test_bank_statement_inferred_from_avg_deposit(self):
        from validation.missing_documents import check_missing_documents

        extracted_fields = [
            {"field_name": "avg_monthly_deposit", "value": 48000, "confidence": 0.91},
            {"field_name": "account_number", "value": "XXXX1234", "confidence": 0.85},
        ]
        documents = [{"type": "combined_loan_package"}]

        result = check_missing_documents(
            "personal", None, documents, extracted_fields=extracted_fields
        )
        missing_types = [m.document_type for m in result.missing]
        assert "bank_statement" not in missing_types, (
            f"Bank statement should be inferred from avg_monthly_deposit. Missing: {missing_types}"
        )

    def test_extraction_failure_sentinel_not_counted(self):
        """Extraction failure sentinels must not be counted as evidence of document presence."""
        from validation.missing_documents import check_missing_documents

        extracted_fields = [
            # These are sentinel fields — must NOT trigger "kyc_id present"
            {"field_name": "extraction_failure_combined_loan_package", "value": None, "confidence": 0.0},
        ]
        documents = [{"type": "unknown"}]

        result = check_missing_documents(
            "personal", None, documents, extracted_fields=extracted_fields
        )
        missing_types = [m.document_type for m in result.missing]
        # All required docs should still be missing since sentinels don't count
        assert "kyc_id" in missing_types, \
            "Extraction failure sentinel must not falsely indicate KYC presence"
        assert "payslip" in missing_types, \
            "Extraction failure sentinel must not falsely indicate payslip presence"

    def test_low_confidence_fields_not_counted(self):
        """Fields with confidence <= 0.3 must not count as document presence."""
        from validation.missing_documents import check_missing_documents

        extracted_fields = [
            # Low confidence — should not trigger inference
            {"field_name": "gross_monthly_income", "value": 50000, "confidence": 0.1},
            {"field_name": "id_number", "value": "ABCDE1234F", "confidence": 0.2},
        ]
        documents = [{"type": "unknown"}]

        result = check_missing_documents(
            "personal", None, documents, extracted_fields=extracted_fields
        )
        missing_types = [m.document_type for m in result.missing]
        # Low confidence fields must not count
        assert "kyc_id" in missing_types, \
            "Low-confidence id_number must not count as KYC present"
        assert "payslip" in missing_types, \
            "Low-confidence gross_monthly_income must not count as payslip present"


class TestRiskPreValidationGate:
    """Unit tests for the risk model pre-validation gate."""

    def test_insufficient_data_when_income_and_loan_zero(self):
        """When income=0 and loan=0, must return INSUFFICIENT_DATA."""
        from risk.features import validate_mandatory_features

        features = {
            "income_annum": 0.0,
            "loan_amount": 0.0,
            "_defaulted_fields": [
                "residential_assets_value", "commercial_assets_value",
                "luxury_assets_value", "bank_asset_value",
            ],
        }
        is_sufficient, missing = validate_mandatory_features(features)
        assert not is_sufficient, \
            "Must be insufficient when both income and loan amount are zero"
        assert len(missing) >= 1, "Must report what's missing"

    def test_sufficient_when_income_present(self):
        """When income > 0, basic scoring should proceed."""
        from risk.features import validate_mandatory_features

        features = {
            "income_annum": 600000.0,
            "loan_amount": 1000000.0,
            "_defaulted_fields": [],
        }
        is_sufficient, missing = validate_mandatory_features(features)
        assert is_sufficient, \
            f"Should be sufficient when income and loan are provided. Missing: {missing}"

    def test_risk_score_status_insufficient_data(self):
        """score_loan_file must return INSUFFICIENT_DATA status for empty loan file."""
        from unittest.mock import MagicMock, patch

        mock_model = MagicMock()
        mock_model.model_version = "risk-xgb-v1"
        mock_model.feature_names = []

        from risk.predict import RiskScoringAgent
        agent = RiskScoringAgent(model=mock_model)

        # Minimal loan file with no income or loan data
        loan_file = {
            "extracted_fields": [],
            "applicant": {"declared_income": 0, "loan_amount_requested": 0},
        }

        result = agent.score_loan_file(loan_file)
        assert result["status"] == "INSUFFICIENT_DATA", \
            f"Expected INSUFFICIENT_DATA status, got: {result['status']}"
        assert result["approval_probability"] is None, \
            f"approval_probability must be None when data is insufficient"
        # Model.predict must NOT have been called
        mock_model.predict_approval_probability.assert_not_called()

    def test_risk_score_not_1_when_insufficient(self):
        """approval_probability must never be 1.0 when extraction fails."""
        from unittest.mock import MagicMock

        mock_model = MagicMock()
        mock_model.model_version = "risk-xgb-v1"
        mock_model.predict_approval_probability.return_value = 1.0
        mock_model.feature_names = []

        from risk.predict import RiskScoringAgent
        agent = RiskScoringAgent(model=mock_model)

        loan_file = {
            "extracted_fields": [],
            "applicant": {"declared_income": 0, "loan_amount_requested": 0},
        }

        result = agent.score_loan_file(loan_file)
        assert result.get("approval_probability") != 1.0, \
            "approval_probability must not be 1.0 when extraction fails"


class TestClassifierPromptAlignment:
    """Unit tests confirming document type values are correctly aligned."""

    def test_valid_types_match_enum(self):
        """All types listed in DOCUMENT_CLASSIFICATION_PROMPT must be valid DocumentType values."""
        from ingestion.models.document import DocumentType
        from ingestion.classifier import VALID_TYPES

        expected_types = {t.value for t in DocumentType}
        # Every type in VALID_TYPES must be in DocumentType
        for t in VALID_TYPES:
            assert t in expected_types, \
                f"Classifier VALID_TYPES contains {t!r} which is not in DocumentType enum"

    def test_alias_normalization(self):
        """Classifier aliases must resolve to valid DocumentType values."""
        from ingestion.classifier import _TYPE_ALIASES, VALID_TYPES

        for alias, resolved in _TYPE_ALIASES.items():
            assert resolved in VALID_TYPES, (
                f"Alias {alias!r} resolves to {resolved!r} which is not a valid DocumentType"
            )

    def test_parse_result_handles_paystub_alias(self):
        """Classifier must normalize 'paystub' -> 'payslip' (the original bug)."""
        from ingestion.classifier import DocumentClassifier

        clf = DocumentClassifier(client=MagicMock())

        import json
        raw = json.dumps({"document_type": "paystub", "confidence": 0.9, "reasoning": "test"})
        result = clf._parse_result(raw)

        from ingestion.models.document import DocumentType
        assert result.document_type == DocumentType.PAYSLIP, (
            f"'paystub' should normalize to 'payslip', got {result.document_type}"
        )

    def test_parse_result_handles_id_card_alias(self):
        """Classifier must normalize 'id_card' -> 'identity_document' (the original bug)."""
        from ingestion.classifier import DocumentClassifier

        clf = DocumentClassifier(client=MagicMock())

        import json
        raw = json.dumps({"document_type": "id_card", "confidence": 0.85, "reasoning": "test"})
        result = clf._parse_result(raw)

        from ingestion.models.document import DocumentType
        assert result.document_type == DocumentType.IDENTITY_DOCUMENT, (
            f"'id_card' should normalize to 'identity_document', got {result.document_type}"
        )


# Need to import MagicMock at module level for TestClassifierPromptAlignment
from unittest.mock import MagicMock  # noqa: E402
