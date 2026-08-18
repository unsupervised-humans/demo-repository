"""Risk scoring prediction agent and pipeline integration.

Consumes loan_file extracted_fields and validation findings, executes the trained
risk scoring model, generates factor breakdowns, and appends audit log entries.
"""

from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, Optional

from risk.compliance import ComplianceAgent
from risk.explain import compute_factor_breakdown
from risk.features import extract_features_from_loan_file
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

        Args:
            loan_file: Loan file dictionary conformant to loan_file.schema.json

        Returns:
            risk_score dictionary:
            {
                "approval_probability": float,
                "model_version": str,
                "factors": [{"feature": str, "contribution": float}, ...]
            }
        """
        features = extract_features_from_loan_file(loan_file)
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
    loan_file["audit_log"].append(
        {
            "agent": "risk_scoring",
            "action": "computed approval probability",
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
