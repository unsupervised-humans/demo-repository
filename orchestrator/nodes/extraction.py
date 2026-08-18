"""Extraction node — calls Austin's extract_fields().

Austin's module mutates loan_file in place, appending to
``extracted_fields[]`` and ``audit_log[]``.
"""

from __future__ import annotations

import logging
from typing import Any

from orchestrator.audit import append_audit

logger = logging.getLogger(__name__)


def run_extraction(loan_file: dict[str, Any]) -> dict[str, Any]:
    """Run Austin's field extraction over all documents.

    Parameters
    ----------
    loan_file : dict
        Must contain ``documents[]``.  Will be mutated with
        ``extracted_fields[]`` and ``audit_log[]`` entries.

    Returns
    -------
    dict
        Updated loan_file.
    """
    from extraction import extract_fields

    append_audit(loan_file, "extraction started")

    loan_file = extract_fields(loan_file)

    field_count = len(loan_file.get("extracted_fields") or [])
    review_count = sum(
        1 for f in (loan_file.get("extracted_fields") or [])
        if f.get("needs_review")
    )

    append_audit(
        loan_file,
        f"extraction completed: {field_count} fields extracted, "
        f"{review_count} flagged for review",
    )

    if review_count > 0:
        logger.info(
            "%d extracted field(s) flagged for review", review_count
        )

    return loan_file
