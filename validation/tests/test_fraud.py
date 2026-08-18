"""Fraud / anomaly detection tests."""

from __future__ import annotations

from validation.audit import clear_audit_lines, get_audit_lines, log_validation_run
from validation.findings import Severity, make_fraud_flag
from validation.fraud_detector import GrokVisualClient, detect_fraud, maybe_run_visual_check
from validation.tests.conftest import load_sample
from validation.validator import validate


def test_clean_application_zero_fraud_flags():
    sample = load_sample("sample_clean_application.json")
    findings = validate(sample["extracted_fields"], application_date="2026-08-17")
    flags = detect_fraud(sample["extracted_fields"], sample["documents"], findings)
    assert flags == []


def test_name_mismatch_fraud_flag_names_both_docs():
    sample = load_sample("sample_name_mismatch.json")
    findings = validate(sample["extracted_fields"])
    flags = detect_fraud(sample["extracted_fields"], sample["documents"], findings)
    name_flags = [f for f in flags if f.flag_type == "name_mismatch"]
    assert len(name_flags) == 1
    flag = name_flags[0]
    assert flag.severity in {Severity.MEDIUM, Severity.HIGH}
    assert "potential fraud indicator" in flag.description.lower()
    assert "DOC-001" in flag.doc_ids
    assert "DOC-003" in flag.doc_ids
    assert "John Abraham" in flag.description or "John Abraham" in flag.evidence
    assert "Robert Abraham" in flag.description or "Robert Abraham" in flag.evidence


def test_income_mismatch_fraud_flag_high():
    sample = load_sample("sample_income_mismatch.json")
    findings = validate(sample["extracted_fields"])
    flags = detect_fraud(sample["extracted_fields"], sample["documents"], findings)
    income_flags = [f for f in flags if f.flag_type == "income_mismatch"]
    assert len(income_flags) == 1
    assert income_flags[0].severity is Severity.HIGH
    assert "potential fraud indicator" in income_flags[0].description.lower()
    assert "50%" in income_flags[0].description or "0.50" in income_flags[0].description


def test_duplicate_document_hash_possible_reuse():
    sample = load_sample("sample_duplicate_document.json")
    findings = validate(sample["extracted_fields"])
    flags = detect_fraud(sample["extracted_fields"], sample["documents"], findings)
    reuse = [f for f in flags if f.flag_type == "POSSIBLE_DOCUMENT_REUSE"]
    assert len(reuse) == 1
    assert "DOC-001" in reuse[0].doc_ids
    assert "DOC-019" in reuse[0].doc_ids
    assert "POSSIBLE_DOCUMENT_REUSE" in reuse[0].description


def test_metadata_only_anomaly_low_or_medium_with_caveat():
    documents = [
        {
            "doc_id": "DOC-001",
            "file_path": "uploads/doc-001.pdf",
            "type": "kyc_id",
            "classification_confidence": 0.9,
            "metadata": {
                "created_at": "2026-08-10",
                "modified_at": "2026-08-01",
                "software": "unknown",
            },
        }
    ]
    fields = [
        {
            "field_name": "applicant_name",
            "value": "Anita Joseph",
            "confidence": 0.99,
            "source": {"doc_id": "DOC-001", "page": 1},
        }
    ]
    flags = detect_fraud(fields, documents, [])
    meta = [f for f in flags if f.flag_type == "metadata_anomaly"]
    assert len(meta) == 1
    assert meta[0].severity in {Severity.LOW, Severity.MEDIUM}
    assert "not proof of fraud" in meta[0].description.lower()
    assert meta[0].weak_signal is True


def test_one_weak_signal_alone_never_escalates_to_critical():
    flag = make_fraud_flag(
        flag_type="metadata_anomaly",
        severity=Severity.CRITICAL,
        evidence="created after modified",
        doc_ids=["DOC-001"],
        detail="Metadata anomaly alone is not proof of fraud.",
        weak_signal=True,
    )
    assert flag.severity is not Severity.CRITICAL
    assert flag.severity in {Severity.LOW, Severity.MEDIUM}

    documents = [
        {
            "doc_id": "DOC-001",
            "type": "kyc_id",
            "file_path": "uploads/x.pdf",
            "classification_confidence": 0.9,
            "metadata": {"created_at": "2026-08-10", "modified_at": "2026-08-01"},
        }
    ]
    fields = [
        {
            "field_name": "applicant_name",
            "value": "Anita Joseph",
            "confidence": 0.99,
            "source": {"doc_id": "DOC-001", "page": 1},
        }
    ]
    flags = detect_fraud(fields, documents, [])
    assert flags
    assert all(f.severity is not Severity.CRITICAL for f in flags)
    if len(flags) == 1:
        assert flags[0].severity in {Severity.LOW, Severity.MEDIUM}


def test_visual_check_not_called_without_prior_flag(monkeypatch):
    called = {"n": 0}

    class RecordingClient(GrokVisualClient):
        def check(self, document, trigger_reason):
            called["n"] += 1
            return {"detail": "should not run", "severity": "HIGH"}

    sample = load_sample("sample_clean_application.json")
    findings = validate(sample["extracted_fields"], application_date="2026-08-17")
    flags = detect_fraud(
        sample["extracted_fields"],
        sample["documents"],
        findings,
        visual_client=RecordingClient(),
    )
    assert flags == []
    assert called["n"] == 0


def test_maybe_run_visual_check_uses_env_and_is_mockable(monkeypatch):
    monkeypatch.setenv("XAI_API_KEY", "secret-test-key-xyz")

    class FakeClient(GrokVisualClient):
        def check(self, document, trigger_reason):
            return {
                "detail": "font inconsistency on suspected page",
                "evidence": "visual stub",
                "severity": "MEDIUM",
                "doc_id": document["doc_id"],
            }

    flag = maybe_run_visual_check(
        {"doc_id": "DOC-001"},
        trigger_reason="name mismatch already flagged",
        client=FakeClient(),
    )
    assert flag is not None
    assert "potential fraud indicator" in flag.description.lower()
    assert flag.doc_ids == ["DOC-001"]


def test_audit_output_never_contains_api_key(monkeypatch):
    monkeypatch.setenv("XAI_API_KEY", "secret-test-key-xyz")
    clear_audit_lines()
    log_validation_run("success", 1, 0, 0)
    blob = "\n".join(get_audit_lines())
    assert "XAI_API_KEY" not in blob
    assert "secret-test-key-xyz" not in blob
