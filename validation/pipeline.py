"""Combine Alina's agents into a single loan_file update.

Christy's orchestrator can call ``process_loan_file(loan_file)``.
"""

from __future__ import annotations

from typing import Any

from validation.audit import log_failure, log_validation_run
from validation.fraud_detector import detect_fraud
from validation.graph import build_consistency_graph, graph_to_dict
from validation.missing_documents import check_missing_documents
from validation.validator import validate


def process_loan_file(loan_file: dict[str, Any]) -> dict[str, Any]:
    """Run validation → missing documents → fraud → graph, appending audit_log."""
    try:
        fields = loan_file.get("extracted_fields") or []
        documents = loan_file.get("documents") or []
        applicant = loan_file.get("applicant") or {}
        loan_type = applicant.get("loan_type") or loan_file.get("loan_type") or "personal"
        application_date = loan_file.get("created_at")

        findings = validate(fields, application_date=application_date)
        # Pass extracted_fields so combined-PDF field signatures are checked
        missing_result = check_missing_documents(loan_type, None, documents, extracted_fields=fields)
        flags = detect_fraud(fields, documents, findings)
        graph = build_consistency_graph(fields, findings)

        loan_file["validation_findings"] = [f.to_schema_dict() for f in findings]
        loan_file["missing_documents"] = [m.to_schema_dict() for m in missing_result.missing]
        loan_file["fraud_flags"] = [flag.to_schema_dict() for flag in flags]
        loan_file["consistency_graph"] = graph_to_dict(graph)

        audit_entry = log_validation_run(
            status="success",
            findings_count=len(findings),
            fraud_flags_count=len(flags),
            missing_documents_count=len(missing_result.missing),
        )
        loan_file.setdefault("audit_log", [])
        loan_file["audit_log"].append(
            {
                "agent": audit_entry["agent"],
                "action": audit_entry["action"],
                "timestamp": audit_entry["timestamp"],
            }
        )
        return loan_file
    except Exception as exc:
        log_failure(stage="process_loan_file", error=type(exc).__name__)
        raise
