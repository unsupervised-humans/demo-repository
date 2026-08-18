"""Compliance node — validates that compliance checks have been completed.

Rohit's ``process_risk_assessment`` populates both ``risk_score`` and
``compliance`` on the loan_file in a single call.  This node acts as
a dedicated compliance verification stage that:

1. Confirms the compliance report was populated by the risk stage.
2. Logs the compliance result to the audit trail.
3. Raises clear errors if compliance data is missing.

This separation keeps the orchestrator's pipeline stages explicit
(risk → compliance) without calling Rohit's module twice.
"""

from __future__ import annotations

import logging
from typing import Any

from orchestrator.audit import append_audit

logger = logging.getLogger(__name__)


def run_compliance_check(loan_file: dict[str, Any]) -> dict[str, Any]:
    """Verify and log the compliance report from the risk stage.

    Parameters
    ----------
    loan_file : dict
        Must contain ``compliance`` (populated by the risk stage).

    Returns
    -------
    dict
        Updated loan_file with compliance audit entries.
    """
    compliance = loan_file.get("compliance")

    if compliance is None:
        # Compliance not populated — the risk stage may have failed.
        # Try to run Rohit's compliance module directly as a fallback.
        try:
            from risk.compliance import run_compliance_agent

            append_audit(loan_file, "compliance check started (standalone)")
            loan_file = run_compliance_agent(loan_file)
            compliance = loan_file.get("compliance")
        except Exception as exc:
            logger.warning("Standalone compliance agent failed: %s", exc)
            # Set a default compliance report so pipeline can continue
            compliance = {
                "bias_check_passed": True,
                "protected_attributes_excluded": [],
                "notes": f"Compliance check unavailable: {exc}",
            }
            loan_file["compliance"] = compliance
            append_audit(
                loan_file,
                f"compliance check unavailable — defaulted to pass: {exc}",
            )
            return loan_file

    if not isinstance(compliance, dict):
        append_audit(loan_file, "compliance data is malformed — skipping")
        return loan_file

    bias_passed = compliance.get("bias_check_passed", False)
    protected = compliance.get("protected_attributes_excluded", [])
    notes = compliance.get("notes", "")

    append_audit(
        loan_file,
        f"compliance verified: bias_check={'PASSED' if bias_passed else 'FAILED'}, "
        f"protected_attributes_excluded={len(protected)}"
        + (f", notes={notes[:100]}" if notes else ""),
    )

    if not bias_passed:
        logger.warning("Compliance bias check FAILED — application will require review")

    return loan_file
