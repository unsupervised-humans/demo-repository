"""Risk scoring prediction agent and pipeline integration.

Consumes loan_file extracted_fields and validation findings, executes the trained
risk scoring model, generates factor breakdowns, and appends audit log entries.

Pre-Validation Gate
-------------------
Before calling the XGBoost model, ``score_loan_file()`` calls
``validate_mandatory_features()``.  If income and loan amount are both zero
(a reliable sign of extraction failure), the model is NOT called and instead
``{"status": "INSUFFICIENT_DATA", "approval_probability": None, ...}`` is
returned.  The decision agent escalates this to human review.
"""

from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, Optional

from risk.compliance import ComplianceAgent
from risk.explain import compute_factor_breakdown
from risk.features import extract_features_from_loan_file, validate_mandatory_features
from risk.model import RiskModel


class RiskScoringAgent:
    """Agent that extracts features, scores risk, and computes factor breakdowns."""

    def __init__(self, model_path: Optional[str | Path] = None, model: Optional[RiskModel] = None):
        if model is not None:
            self.model = model
        else:
            self.model = RiskModel.load(model_path)

    def score_loan_file(self, loan_file: Dict[str, Any]) -> Dict[str, Any]:
        """Score a loan file and return a risk_score dict matching the schema.

        Pre-validation gate: if mandatory features (income_annum, loan_amount)
        are missing or zero (indicating extraction failure), the XGBoost model
        is NOT called.  Instead, returns INSUFFICIENT_DATA status.

        Args:
            loan_file: Loan file dictionary conformant to loan_file.schema.json

        Returns:
            risk_score dictionary:
            {
                "approval_probability": float | None,
                "model_version": str,
                "factors": [{...}, ...],
                "status": "ok" | "INSUFFICIENT_DATA",
                "data_completeness_note": str,
            }
        """
        features = extract_features_from_loan_file(loan_file)

        # --- Pre-Validation Gate ---
        is_sufficient, missing_mandatory = validate_mandatory_features(features)

        if not is_sufficient:
            reason = (
                "Risk model not evaluated: mandatory features missing or zero. "
                f"Issues: {'; '.join(missing_mandatory)}. "
                f"Data note: {features.get('data_completeness_note', '')}"
            )
            return {
                "approval_probability": None,
                "model_version": self.model.model_version,
                "factors": [],
                "status": "INSUFFICIENT_DATA",
                "reason": reason,
                "data_completeness_note": features.get("data_completeness_note", ""),
            }

        # --- Normal scoring path ---
        approval_prob = self.model.predict_approval_probability(features)
        factors = compute_factor_breakdown(
            model=self.model,
            feature_dict=features,
            feature_names=self.model.feature_names,
        )

        return {
            "approval_probability": round(approval_prob, 2),
            "model_version": self.model.model_version,
            "factors": factors,
            "status": "ok",
            "data_completeness_note": features.get("data_completeness_note", ""),
        }


def process_risk_assessment(
    loan_file: Dict[str, Any],
    model_path: Optional[str | Path] = None,
) -> Dict[str, Any]:
    """Execute risk scoring and compliance agent checks on a loan file.

    Updates:
        - loan_file["risk_score"]
        - loan_file["compliance"]
        - loan_file["audit_log"] (appends scoring and compliance actions)

    Returns:
        Updated loan_file dictionary.
    """
    now = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")

    # 1. Risk Scoring Agent
    scoring_agent = RiskScoringAgent(model_path=model_path)
    risk_score = scoring_agent.score_loan_file(loan_file)
    loan_file["risk_score"] = risk_score

    # 2. Compliance Agent
    compliance_agent = ComplianceAgent()
    features = extract_features_from_loan_file(loan_file)
    compliance_report = compliance_agent.check_features(list(features.keys()))
    loan_file["compliance"] = compliance_report

    # 3. Append to Audit Log
    loan_file.setdefault("audit_log", [])

    status = risk_score.get("status", "ok")
    prob = risk_score.get("approval_probability")
    if status == "INSUFFICIENT_DATA":
        prob_str = "N/A (INSUFFICIENT_DATA)"
    else:
        prob_str = f"{prob:.2f}" if prob is not None else "None"

    loan_file["audit_log"].append(
        {
            "agent": "risk_scoring",
            "action": f"computed approval probability: {prob_str} (status={status})",
            "timestamp": now,
        }
    )
    loan_file["audit_log"].append(
        {
            "agent": "compliance",
            "action": "ran fairness check",
            "timestamp": now,
        }
    )

    return loan_file
