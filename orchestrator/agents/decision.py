"""Decision / Policy Agent (#8) — Christy's holistic decision logic.

Unlike Rohit's ``RiskPolicy`` (which evaluates thresholds on the risk score
alone), this agent takes the **full loan_file** into account:

- Risk probability + SHAP factors
- Validation findings (critical vs warning)
- Fraud flags (any severity)
- Missing documents
- Extraction confidence (needs_review fields)
- Compliance bias check

It produces the final ``summary_report.recommendation`` and a list of
human-readable reasons.
"""

from __future__ import annotations

import logging
from typing import Any

logger = logging.getLogger(__name__)

# ── Thresholds ────────────────────────────────────────────────────────────────
AUTO_APPROVE_THRESHOLD = 0.80
AUTO_REJECT_THRESHOLD = 0.35
HIGH_FRAUD_SEVERITIES = {"high"}


def evaluate_decision(
    loan_file: dict[str, Any],
) -> dict[str, Any]:
    """Evaluate the full loan_file and produce a decision.

    Returns
    -------
    dict
        ``{"recommendation": str, "reasons": list[str], "needs_review": bool}``

        Where ``recommendation`` is one of:
        - ``"approve"``
        - ``"reject"``
        - ``"request_more_info"``
    """
    reasons: list[str] = []
    force_review = False

    # ── 1. Fraud flags ────────────────────────────────────────────────────────
    fraud_flags = loan_file.get("fraud_flags") or []
    high_fraud = [f for f in fraud_flags if f.get("severity") in HIGH_FRAUD_SEVERITIES]
    if high_fraud:
        reasons.append(
            f"High-severity fraud flag(s) detected ({len(high_fraud)}): "
            + "; ".join(f.get("description", "?") for f in high_fraud)
        )
        force_review = True

    if fraud_flags and not high_fraud:
        reasons.append(
            f"{len(fraud_flags)} fraud flag(s) at lower severity — flagged for review"
        )
        force_review = True

    # ── 2. Missing documents ──────────────────────────────────────────────────
    missing = loan_file.get("missing_documents") or []
    if missing:
        types = [m.get("document_type", "?") for m in missing]
        reasons.append(f"Missing required documents: {', '.join(types)}")
        # Missing docs → request more info, not reject
        return {
            "recommendation": "request_more_info",
            "reasons": reasons,
            "needs_review": True,
        }

    # ── 3. Compliance failure ─────────────────────────────────────────────────
    compliance = loan_file.get("compliance") or {}
    if isinstance(compliance, dict) and not compliance.get("bias_check_passed", True):
        reasons.append(
            f"Compliance bias check failed: {compliance.get('notes', 'no details')}"
        )
        force_review = True

    # ── 4. Critical validation findings ───────────────────────────────────────
    critical_findings = [
        f for f in (loan_file.get("validation_findings") or [])
        if f.get("severity") == "critical"
    ]
    if critical_findings:
        reasons.append(
            f"{len(critical_findings)} critical validation finding(s): "
            + "; ".join(f.get("description", "?") for f in critical_findings)
        )
        force_review = True

    # ── 5. Low-confidence extractions (only fields that HAVE a value) ──────────
    review_fields = [
        f for f in (loan_file.get("extracted_fields") or [])
        if f.get("needs_review")
        and f.get("value") is not None  # skip absent/null fields
        and not str(f.get("field_name", "")).startswith("extraction_failure_")
    ]
    if review_fields:
        names = [f.get("field_name", "?") for f in review_fields]
        # Group into a single reason
        summary = ", ".join(names[:4]) + (f" (+{len(names)-4} more)" if len(names) > 4 else "")
        reasons.append(f"Low-confidence extracted values: {summary}")
        force_review = True

    # -- 6. Risk probability ---------------------------------------------------
    risk = loan_file.get("risk_score")
    approval_prob = 0.5  # default if no risk score

    # Check for INSUFFICIENT_DATA status first
    if risk and isinstance(risk, dict):
        risk_status = risk.get("status", "ok")
        if risk_status == "INSUFFICIENT_DATA":
            reason_msg = risk.get("reason", "Risk model could not be evaluated.")
            reasons.append(f"Risk score unavailable: {reason_msg}")
            return {
                "recommendation": "request_more_info",
                "reasons": reasons,
                "needs_review": True,
            }
        approval_prob = risk.get("approval_probability", 0.5)
        if approval_prob is None:
            approval_prob = 0.5

    if approval_prob >= AUTO_APPROVE_THRESHOLD and not force_review:
        if not reasons:
            reasons.append(
                f"Approval probability ({approval_prob:.2f}) meets auto-approval threshold"
            )
        return {
            "recommendation": "approve",
            "reasons": reasons,
            "needs_review": False,
        }

    if approval_prob < AUTO_REJECT_THRESHOLD and not force_review:
        reasons.append(
            f"Approval probability ({approval_prob:.2f}) below minimum cutoff"
        )
        return {
            "recommendation": "reject",
            "reasons": reasons,
            "needs_review": True,  # even rejections should be reviewed
        }

    # ── In the review band or force_review is True ────────────────────────────
    if approval_prob < AUTO_APPROVE_THRESHOLD:
        reasons.append(
            f"Approval probability ({approval_prob:.2f}) in review band "
            f"({AUTO_REJECT_THRESHOLD:.2f}–{AUTO_APPROVE_THRESHOLD:.2f})"
        )

    return {
        "recommendation": "approve" if not force_review else "request_more_info",
        "reasons": reasons,
        "needs_review": True,
    }
