"""Validation node — calls Alina's process_loan_file().

Alina's pipeline runs validation, missing-document detection, and fraud
detection in sequence, populating:
- ``validation_findings[]``
- ``missing_documents[]``
- ``fraud_flags[]``
- ``audit_log[]``
"""

from __future__ import annotations

import logging
from typing import Any

from orchestrator.audit import append_audit

logger = logging.getLogger(__name__)


def run_validation(loan_file: dict[str, Any]) -> dict[str, Any]:
    """Run Alina's full validation pipeline.

    Parameters
    ----------
    loan_file : dict
        Must contain ``documents[]`` and ``extracted_fields[]``.

    Returns
    -------
    dict
        Updated loan_file with validation results.
    """
    from validation import process_loan_file

    append_audit(loan_file, "validation started")

    loan_file = process_loan_file(loan_file)

    findings_count = len(loan_file.get("validation_findings") or [])
    missing_count = len(loan_file.get("missing_documents") or [])
    fraud_count = len(loan_file.get("fraud_flags") or [])

    critical_count = sum(
        1 for f in (loan_file.get("validation_findings") or [])
        if f.get("severity") == "critical"
    )

    append_audit(
        loan_file,
        f"validation completed: {findings_count} findings "
        f"({critical_count} critical), {missing_count} missing docs, "
        f"{fraud_count} fraud flags",
    )

    if fraud_count > 0:
        logger.warning("%d fraud flag(s) detected", fraud_count)
    if missing_count > 0:
        logger.info("%d missing document(s) detected", missing_count)

    return loan_file
