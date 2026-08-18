"""Consistency graph + schema-validation of combined pipeline output."""

from __future__ import annotations

from datetime import datetime, timezone

from validation.graph import build_consistency_graph, graph_to_dict
from validation.pipeline import process_loan_file
from validation.tests.conftest import load_sample
from validation.validator import validate

try:
    from shared.schema_loader import validate_loan_file

    HAS_SCHEMA = True
except ImportError:
    HAS_SCHEMA = False


def test_clean_graph_builds_without_conflict_edges():
    sample = load_sample("sample_clean_application.json")
    findings = validate(sample["extracted_fields"], application_date="2026-08-17")
    graph = build_consistency_graph(sample["extracted_fields"], findings)
    payload = graph_to_dict(graph)
    assert payload["nodes"]
    assert payload["edges"]
    conflict = [e for e in payload["edges"] if e.get("relation") == "conflict"]
    name_conflicts = [e for e in conflict if e.get("field_name") in {"applicant_name", "employee_name", "account_holder_name"}]
    assert name_conflicts == []


def test_name_mismatch_graph_has_labeled_conflict_edge():
    sample = load_sample("sample_name_mismatch.json")
    findings = validate(sample["extracted_fields"])
    graph = build_consistency_graph(sample["extracted_fields"], findings)
    payload = graph_to_dict(graph)
    conflict = [e for e in payload["edges"] if e.get("relation") == "conflict"]
    assert conflict, "expected a conflict edge for the name mismatch"
    assert any(e.get("relation") == "conflict" for e in payload["edges"])
    labels = {e.get("field_name") for e in conflict}
    assert "applicant_name" in labels or any("Abraham" in (e.get("source") or "") for e in conflict)


def _loan_file_from_sample(sample: dict, application_id: str) -> dict:
    return {
        "application_id": application_id,
        "created_at": "2026-08-17T09:00:00Z",
        "status": "validating",
        "applicant": sample.get("applicant")
        or {
            "name": "Test Applicant",
            "declared_income": 65000,
            "loan_amount_requested": 400000,
            "loan_type": sample.get("loan_type", "personal"),
        },
        "documents": sample["documents"],
        "extracted_fields": sample["extracted_fields"],
        "audit_log": [
            {
                "agent": "extraction",
                "action": "extracted fields",
                "timestamp": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
            }
        ],
    }


def test_pipeline_output_validates_against_schema_clean_and_mismatch():
    if not HAS_SCHEMA:
        import pytest

        pytest.skip("shared.schema_loader / jsonschema not available")

    for name, app_id in (
        ("sample_clean_application.json", "APP-VAL-CLEAN"),
        ("sample_name_mismatch.json", "APP-VAL-NAME"),
    ):
        sample = load_sample(name)
        loan_file = _loan_file_from_sample(sample, app_id)
        updated = process_loan_file(loan_file)
        # consistency_graph is an extra field; schema allows additional properties.
        validate_loan_file(updated)
        assert isinstance(updated["validation_findings"], list)
        assert isinstance(updated["fraud_flags"], list)
        assert isinstance(updated["missing_documents"], list)
        if name.endswith("name_mismatch.json"):
            assert updated["validation_findings"]
            assert updated["fraud_flags"]
        else:
            types = {f.get("finding_type") for f in updated["validation_findings"]}
            assert "name_mismatch" not in types
