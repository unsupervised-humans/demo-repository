"""Cross-document validation tests."""

from __future__ import annotations

from validation.findings import Severity
from validation.tests.conftest import load_sample
from validation.validator import validate


def test_all_consistent_application_zero_findings():
    sample = load_sample("sample_clean_application.json")
    findings = validate(sample["extracted_fields"], application_date="2026-08-17")
    assert findings == []


def test_name_mismatch_john_vs_robert():
    sample = load_sample("sample_name_mismatch.json")
    findings = validate(sample["extracted_fields"])
    name_findings = [f for f in findings if f.finding_type == "name_mismatch"]
    assert len(name_findings) == 1
    finding = name_findings[0]
    assert finding.severity in {Severity.MEDIUM, Severity.HIGH}
    assert "John Abraham" in finding.message
    assert "Robert Abraham" in finding.message
    assert "DOC-001" in finding.message
    assert "DOC-003" in finding.message
    assert finding.status == "mismatch"
    assert "fraud" not in finding.status.lower()


def test_income_mismatch_high_severity_percent_diff():
    sample = load_sample("sample_income_mismatch.json")
    findings = validate(sample["extracted_fields"])
    income_findings = [f for f in findings if f.finding_type == "income_mismatch"]
    assert len(income_findings) == 1
    finding = income_findings[0]
    assert finding.severity is Severity.HIGH
    rel = finding.values["relative_difference"]
    expected = abs(80000 - 25000) / 80000
    assert abs(rel - expected) < 1e-9
    assert "68.75" in finding.message
    assert "80000" in finding.message.replace(",", "") or "80,000" in finding.message
    assert "25000" in finding.message.replace(",", "") or "25,000" in finding.message
    assert finding.sources[0].doc_id in {"DOC-001", "DOC-002"}
    assert finding.sources[1].doc_id in {"DOC-001", "DOC-002"}


def test_employer_mismatch():
    sample = load_sample("sample_employer_mismatch.json")
    findings = validate(sample["extracted_fields"])
    employer_findings = [f for f in findings if f.finding_type == "employer_mismatch"]
    assert len(employer_findings) == 1
    assert "ABC Technologies" in employer_findings[0].message
    assert "XYZ Solutions" in employer_findings[0].message


def test_formatting_only_address_never_mismatch():
    sample = load_sample("sample_formatting_difference_only.json")
    findings = validate(sample["extracted_fields"])
    address_findings = [f for f in findings if f.finding_type.startswith("address_")]
    for finding in address_findings:
        assert finding.status in {"minor_variation", "pass"}
        assert finding.status != "mismatch"
        assert finding.finding_type != "address_mismatch"


def test_missing_field_for_one_check_no_crash_no_fabricated_finding():
    fields = [
        {
            "field_name": "applicant_name",
            "value": "Neha Gupta",
            "confidence": 0.99,
            "source": {"doc_id": "DOC-001", "page": 1},
        },
        {
            "field_name": "employee_name",
            "value": "Neha Gupta",
            "confidence": 0.97,
            "source": {"doc_id": "DOC-002", "page": 1},
        },
        # gross_monthly_income present, avg_monthly_deposit absent → skip income check
        {
            "field_name": "gross_monthly_income",
            "value": 61000,
            "confidence": 0.95,
            "source": {"doc_id": "DOC-002", "page": 1},
        },
    ]
    findings = validate(fields)
    assert all(f.finding_type != "income_mismatch" for f in findings)
    assert all(f.finding_type != "employer_mismatch" for f in findings)


def test_low_confidence_extraction_does_not_crash():
    sample = load_sample("sample_low_confidence_extraction.json")
    findings = validate(sample["extracted_fields"], application_date="2026-08-17")
    assert isinstance(findings, list)
