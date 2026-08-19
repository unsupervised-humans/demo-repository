"""Decision / Policy Agent (#8) — Christy's holistic decision logic.

Unlike Rohit's ``RiskPolicy`` (which evaluates thresholds on the risk score
alone), this agent takes the **full loan_file** into account:

- Risk probability + SHAP factors
- Validation findings (critical vs warning)
- Fraud flags (any severity)
- Missing documents
- Extraction confidence (needs_review fields) — soft warning only
- Compliance bias check

It produces the final ``summary_report.recommendation`` and a list of
human-readable reasons.

Decision tiers
--------------
* **approve**            prob >= AUTO_APPROVE_THRESHOLD AND no hard blockers
* **reject**             prob <  AUTO_REJECT_THRESHOLD  AND no hard blockers
* **request_more_info**  everything else (review band OR hard blockers present)

Hard blockers (always force review regardless of probability):
  - Fraud flags (any severity)
  - Missing required documents
  - Compliance bias check failure
  - Critical validation findings

Soft warnings (noted in reasons but do NOT block approval):
  - Low-confidence extracted field values
"""

from __future__ import annotations

import logging
from typing import Any

logger = logging.getLogger(__name__)

# ── Thresholds ────────────────────────────────────────────────────────────────
AUTO_APPROVE_THRESHOLD = 0.80   # >= this → approve (if no hard blockers)
AUTO_REJECT_THRESHOLD  = 0.35   # <  this → reject  (if no hard blockers)
HIGH_FRAUD_SEVERITIES  = {"high"}
# Low-confidence threshold: only flag for review if confidence is very low
LOW_CONFIDENCE_FLOOR   = 0.35   # fields below this AND needs_review are noted


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
    hard_block = False   # serious issues that must always force human review
    soft_notes: list[str] = []  # informational warnings that don't block approval

    # ── 1. Fraud flags — HARD BLOCKER ─────────────────────────────────────────
    fraud_flags = loan_file.get("fraud_flags") or []
    high_fraud = [f for f in fraud_flags if f.get("severity") in HIGH_FRAUD_SEVERITIES]
    if high_fraud:
        reasons.append(
            f"High-severity fraud flag(s) detected ({len(high_fraud)}): "
            + "; ".join(f.get("description", "?") for f in high_fraud)
        )
        hard_block = True

    if fraud_flags and not high_fraud:
        reasons.append(
            f"{len(fraud_flags)} fraud flag(s) at lower severity — flagged for review"
        )
        hard_block = True

    # ── 2. Missing documents — HARD BLOCKER ───────────────────────────────────
    missing = loan_file.get("missing_documents") or []
    if missing:
        types = [m.get("document_type", "?") for m in missing]
        reasons.append(f"Missing required documents: {', '.join(types)}")
        return {
            "recommendation": "request_more_info",
            "reasons": reasons,
            "needs_review": True,
        }

    # ── 3. Compliance failure — HARD BLOCKER ──────────────────────────────────
    compliance = loan_file.get("compliance") or {}
    if isinstance(compliance, dict) and not compliance.get("bias_check_passed", True):
        reasons.append(
            f"Compliance bias check failed: {compliance.get('notes', 'no details')}"
        )
        hard_block = True

    # ── 4. Critical validation findings — HARD BLOCKER ────────────────────────
    critical_findings = [
        f for f in (loan_file.get("validation_findings") or [])
        if f.get("severity") == "critical"
    ]
    if critical_findings:
        reasons.append(
            f"{len(critical_findings)} critical validation finding(s): "
            + "; ".join(f.get("description", "?") for f in critical_findings)
        )
        hard_block = True

    # ── 5. Low-confidence extractions — SOFT WARNING only ─────────────────────
    # These are informational: they do NOT block approval on their own.
    # Only truly very-low-confidence fields (< LOW_CONFIDENCE_FLOOR) are noted.
    review_fields = [
        f for f in (loan_file.get("extracted_fields") or [])
        if f.get("needs_review")
        and f.get("value") is not None
        and not str(f.get("field_name", "")).startswith("extraction_failure_")
        and float(f.get("confidence") or 0) < LOW_CONFIDENCE_FLOOR
    ]
    if review_fields:
        names = [f.get("field_name", "?") for f in review_fields]
        summary = ", ".join(names[:4]) + (f" (+{len(names)-4} more)" if len(names) > 4 else "")
        soft_notes.append(f"Very low-confidence extracted values (< {LOW_CONFIDENCE_FLOOR:.0%}): {summary}")

    # ── 6. Risk probability ────────────────────────────────────────────────────
    risk = loan_file.get("risk_score")
    approval_prob = 0.5  # default if no risk score

    if risk and isinstance(risk, dict):
        risk_status = risk.get("status", "ok")
        if risk_status == "INSUFFICIENT_DATA":
            reason_msg = risk.get("reason", "Risk model could not be evaluated.")
            reasons.append(f"Risk score unavailable: {reason_msg}")
            reasons.extend(soft_notes)
            return {
                "recommendation": "request_more_info",
                "reasons": reasons,
                "needs_review": True,
            }
        approval_prob = risk.get("approval_probability", 0.5)
        if approval_prob is None:
            approval_prob = 0.5

    # ── Decision ───────────────────────────────────────────────────────────────
    # AUTO-APPROVE: high probability AND no hard blockers
    if approval_prob >= AUTO_APPROVE_THRESHOLD and not hard_block:
        if not reasons:
            reasons.append(
                f"Approval probability ({approval_prob:.0%}) meets auto-approval threshold"
            )
        reasons.extend(soft_notes)   # include soft notes as informational
        return {
            "recommendation": "approve",
            "reasons": reasons,
            "needs_review": False,
        }

    # AUTO-REJECT: low probability AND no hard blockers
    if approval_prob < AUTO_REJECT_THRESHOLD and not hard_block:
        reasons.append(
            f"Approval probability ({approval_prob:.0%}) is below the minimum cutoff ({AUTO_REJECT_THRESHOLD:.0%})"
        )
        reasons.extend(soft_notes)
        return {
            "recommendation": "reject",
            "reasons": reasons,
            "needs_review": True,
        }

    # REVIEW BAND: probability between thresholds, OR hard blockers present
    if approval_prob < AUTO_APPROVE_THRESHOLD:
        reasons.append(
            f"Approval probability ({approval_prob:.0%}) is in the manual review band "
            f"({AUTO_REJECT_THRESHOLD:.0%}–{AUTO_APPROVE_THRESHOLD:.0%})"
        )
    reasons.extend(soft_notes)

    return {
        "recommendation": "approve" if not hard_block and approval_prob >= AUTO_APPROVE_THRESHOLD else "request_more_info",
        "reasons": reasons,
        "needs_review": True,
    }
