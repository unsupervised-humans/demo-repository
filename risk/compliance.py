"""Compliance and fairness audit agent for loan risk assessment.

Ensures no protected demographic attributes (gender, religion, caste, age, etc.)
feed into the scoring model and generates compliance reports matching schema.
"""

from __future__ import annotations

from typing import Any, Dict, List, Optional
from risk.features import PROTECTED_ATTRIBUTES, validate_feature_safety

STANDARD_EXCLUDED_ATTRIBUTES: List[str] = ["gender", "religion", "caste", "age"]


class ComplianceAgent:
    """Agent responsible for fair lending compliance and anti-bias verification."""

    def __init__(self, protected_attributes: Optional[List[str]] = None):
        self.protected_attributes = protected_attributes or STANDARD_EXCLUDED_ATTRIBUTES

    def check_features(self, feature_names: List[str]) -> Dict[str, Any]:
        """Verify that no protected attributes are included in the feature set."""
        violations = validate_feature_safety(feature_names)
        bias_check_passed = len(violations) == 0

        if bias_check_passed:
            notes = (
                "Decision factors are all financial/document-based; "
                "no protected attributes used in scoring."
            )
        else:
            notes = f"Compliance violation: protected attributes detected in feature set: {violations}"

        return {
            "bias_check_passed": bias_check_passed,
            "protected_attributes_excluded": list(self.protected_attributes),
            "notes": notes,
        }

    def evaluate_loan_file(
        self, loan_file: Dict[str, Any], feature_names: Optional[List[str]] = None
    ) -> Dict[str, Any]:
        """Run complete compliance check for a loan file and return compliance report."""
        if feature_names is None:
            # Check extracted fields for prohibited usage
            extracted_fields = loan_file.get("extracted_fields") or []
            field_names = [f.get("field_name", "") for f in extracted_fields]
            feature_names = field_names

        return self.check_features(feature_names)


def run_compliance_check(
    loan_file: Dict[str, Any], feature_names: Optional[List[str]] = None
) -> Dict[str, Any]:
    """Convenience helper to run compliance checks."""
    agent = ComplianceAgent()
    return agent.evaluate_loan_file(loan_file, feature_names=feature_names)
