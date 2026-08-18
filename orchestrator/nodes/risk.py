"""Risk scoring node — calls Rohit's process_risk_assessment().

Rohit's module runs:
1. RiskScoringAgent — XGBoost model → ``risk_score`` with SHAP factors.
2. ComplianceAgent — bias/fairness check → ``compliance`` report.
Both results plus ``audit_log[]`` entries are written to loan_file.
"""

from __future__ import annotations

import logging
from typing import Any

from orchestrator.audit import append_audit

logger = logging.getLogger(__name__)


def run_risk_assessment(loan_file: dict[str, Any]) -> dict[str, Any]:
    """Run Rohit's risk scoring and compliance checks.

    Parameters
    ----------
    loan_file : dict
        Must contain ``extracted_fields[]`` and validation outputs.

    Returns
    -------
    dict
        Updated loan_file with ``risk_score`` and ``compliance``.
    """
    from risk.predict import process_risk_assessment

    append_audit(loan_file, "risk assessment started")

    loan_file = process_risk_assessment(loan_file)

    risk = loan_file.get("risk_score") or {}
    prob = risk.get("approval_probability")
    prob_str = f"{prob:.2f}" if prob is not None else "N/A"
    compliance = loan_file.get("compliance") or {}
    bias_ok = compliance.get("bias_check_passed", False)

    append_audit(
        loan_file,
        f"risk assessment completed: approval_probability={prob_str}, "
        f"bias_check={'passed' if bias_ok else 'FAILED'}",
    )

    if not bias_ok:
        logger.warning("Compliance bias check FAILED")

    return loan_file
