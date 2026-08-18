"""Risk policy evaluation and decision threshold management.

Determines policy outcomes and tier recommendations based on approval probability,
validation findings, and fraud indicators.
"""

from __future__ import annotations

from typing import Any, Dict


class RiskPolicy:
    """Configurable credit policy rules and threshold evaluator."""

    def __init__(
        self,
        auto_approve_threshold: float = 0.80,
        auto_reject_threshold: float = 0.35,
    ):
        self.auto_approve_threshold = auto_approve_threshold
        self.auto_reject_threshold = auto_reject_threshold

    def evaluate_decision(
        self,
        approval_probability: float,
        critical_findings_count: int = 0,
        fraud_flags_count: int = 0,
    ) -> Dict[str, Any]:
        """Apply credit policy rules to determine risk tier and recommendation.

        Args:
            approval_probability: Score from 0.0 to 1.0.
            critical_findings_count: Number of critical validation issues.
            fraud_flags_count: Number of active fraud flags.

        Returns:
            Dict containing recommendation ("approve", "reject", "review"), risk_tier, and rationale.
        """
        if fraud_flags_count > 0:
            return {
                "recommendation": "reject",
                "risk_tier": "HIGH",
                "reason": f"Active fraud flags ({fraud_flags_count}) triggered mandatory policy rejection.",
            }

        if critical_findings_count > 0:
            return {
                "recommendation": "review",
                "risk_tier": "MEDIUM_HIGH",
                "reason": f"Critical validation findings ({critical_findings_count}) require underwriter review.",
            }

        if approval_probability >= self.auto_approve_threshold:
            return {
                "recommendation": "approve",
                "risk_tier": "LOW",
                "reason": f"Approval probability ({approval_probability:.2f}) meets auto-approval threshold.",
            }
        elif approval_probability < self.auto_reject_threshold:
            return {
                "recommendation": "reject",
                "risk_tier": "HIGH",
                "reason": f"Approval probability ({approval_probability:.2f}) below minimum policy cutoff.",
            }
        else:
            return {
                "recommendation": "review",
                "risk_tier": "MEDIUM",
                "reason": f"Approval probability ({approval_probability:.2f}) in review band.",
            }
