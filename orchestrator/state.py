"""Workflow state management for the orchestrator.

Provides:
- ``WorkflowStatus`` — internal pipeline states.
- ``initialize_loan_file`` — creates a fresh schema-compliant loan_file.
- ``set_status`` — updates loan_file status with schema-valid values.
- ``requires_human_review`` — evaluates review triggers across the full file.
"""

from __future__ import annotations

from datetime import datetime, timezone
from enum import Enum
from typing import Any


class WorkflowStatus(str, Enum):
    """Internal orchestrator states — more granular than the schema enum."""

    RECEIVED = "received"
    CLASSIFYING = "classifying"
    EXTRACTING = "extracting"
    VALIDATING = "validating"
    FRAUD_CHECK = "fraud_check"
    RISK_ASSESSMENT = "risk_assessment"
    COMPLIANCE = "compliance"
    DECIDING = "deciding"
    SUMMARIZING = "summarizing"
    REVIEW_REQUIRED = "review_required"
    COMPLETED = "completed"
    FAILED = "failed"


# Map internal states → schema-valid status values.
_STATUS_TO_SCHEMA: dict[WorkflowStatus, str] = {
    WorkflowStatus.RECEIVED: "ingested",
    WorkflowStatus.CLASSIFYING: "classifying",
    WorkflowStatus.EXTRACTING: "extracting",
    WorkflowStatus.VALIDATING: "validating",
    WorkflowStatus.FRAUD_CHECK: "validating",
    WorkflowStatus.RISK_ASSESSMENT: "scoring",
    WorkflowStatus.COMPLIANCE: "scoring",
    WorkflowStatus.DECIDING: "scoring",
    WorkflowStatus.SUMMARIZING: "scoring",
    WorkflowStatus.REVIEW_REQUIRED: "ready_for_review",
    WorkflowStatus.COMPLETED: "approved",  # overridden by decision agent
    WorkflowStatus.FAILED: "rejected",     # overridden by decision agent
}


def initialize_loan_file(
    application_id: str | None = None,
) -> dict[str, Any]:
    """Create a fresh, schema-compliant loan_file dict.

    Parameters
    ----------
    application_id : str, optional
        Unique application identifier.  Auto-generated if omitted.

    Returns
    -------
    dict
        A minimal loan_file ready for the pipeline.
    """
    if application_id is None:
        import uuid
        application_id = f"APP-{datetime.now(timezone.utc).strftime('%Y')}-{uuid.uuid4().hex[:6].upper()}"

    return {
        "application_id": application_id,
        "created_at": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "status": "ingested",
        "applicant": {},
        "documents": [],
        "extracted_fields": [],
        "validation_findings": [],
        "missing_documents": [],
        "fraud_flags": [],
        "risk_score": None,
        "compliance": None,
        "summary_report": None,
        "reviewer_decision": None,
        "audit_log": [],
    }


def set_status(
    loan_file: dict[str, Any],
    workflow_status: WorkflowStatus,
) -> None:
    """Update loan_file['status'] with the schema-valid equivalent.

    Parameters
    ----------
    loan_file : dict
        The shared state object.
    workflow_status : WorkflowStatus
        The internal pipeline state.
    """
    loan_file["status"] = _STATUS_TO_SCHEMA.get(workflow_status, "ingested")


def requires_human_review(
    loan_file: dict[str, Any],
) -> tuple[bool, list[str]]:
    """Evaluate whether the loan_file needs human review.

    Returns
    -------
    (needs_review, reasons) : tuple[bool, list[str]]
        ``needs_review`` is True if any trigger fires.
        ``reasons`` lists every triggered condition.
    """
    reasons: list[str] = []

    # 1. Low-confidence extraction — only flag fields that HAVE a value
    #    but extracted it with low confidence. Missing/null fields are
    #    expected (not all docs contain all fields) and should NOT flood
    #    the review panel.
    low_conf_fields = [
        ef.get('field_name', '?')
        for ef in (loan_file.get("extracted_fields") or [])
        if ef.get("needs_review")
        and ef.get("value") is not None  # skip absent/null fields
        and not str(ef.get('field_name', '')).startswith('extraction_failure_')
    ]
    if low_conf_fields:
        # Group into a single reason instead of one per field
        reasons.append(
            f"Low-confidence extraction on {len(low_conf_fields)} field(s): "
            + ", ".join(low_conf_fields[:5])
            + (f" (+{len(low_conf_fields)-5} more)" if len(low_conf_fields) > 5 else "")
        )

    # Extraction failure sentinels (model returned no content for a doc)
    failure_fields = [
        ef.get('field_name', '?')
        for ef in (loan_file.get("extracted_fields") or [])
        if str(ef.get('field_name', '')).startswith('extraction_failure_')
    ]
    if failure_fields:
        reasons.append(f"Extraction failed for document(s): {', '.join(failure_fields)}")

    # 2. Missing documents
    missing = loan_file.get("missing_documents") or []
    if missing:
        types = [m.get("document_type", "?") for m in missing]
        reasons.append(f"Missing documents: {', '.join(types)}")

    # 3. Fraud flags (any severity)
    fraud = loan_file.get("fraud_flags") or []
    for flag in fraud:
        reasons.append(
            f"Fraud flag [{flag.get('severity', '?')}]: {flag.get('description', '?')}"
        )

    # 4. Critical validation findings only (not warnings)
    for finding in loan_file.get("validation_findings") or []:
        if finding.get("severity") == "critical":
            reasons.append(
                f"Critical validation finding: {finding.get('description', '?')}"
            )

    # 5. Risk score below auto-approve
    risk = loan_file.get("risk_score")
    if risk and isinstance(risk, dict):
        prob = risk.get("approval_probability")
        if prob is None:
            reasons.append("Risk score: Insufficient data for automated scoring")
        elif prob < 0.80:
            reasons.append(
                f"Risk score below auto-approve threshold: {prob:.0%}"
            )

    # 6. Compliance failure
    compliance = loan_file.get("compliance")
    if compliance and isinstance(compliance, dict):
        if not compliance.get("bias_check_passed", True):
            reasons.append("Compliance: bias check failed")

    return bool(reasons), reasons
