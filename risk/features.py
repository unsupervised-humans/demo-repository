"""Feature extraction and engineering for loan risk assessment.

Extracts numerical and categorical features from a loan_file dictionary
and ensures protected attributes are strictly excluded from the feature space.
"""

from __future__ import annotations

from typing import Any, Dict, List, Set

# Protected demographic attributes that MUST NEVER be used in credit scoring or feature sets
PROTECTED_ATTRIBUTES: Set[str] = {
    "gender",
    "sex",
    "religion",
    "caste",
    "race",
    "ethnicity",
    "age",
    "date_of_birth",
    "dob",
    "marital_status",
    "nationality",
    "citizenship",
    "sexual_orientation",
    "disability",
}

# Standard feature names in exact model order
NUMERIC_FEATURE_NAMES: List[str] = [
    "declared_income",
    "loan_amount_requested",
    "income_to_loan_ratio",
    "gross_monthly_income",
    "avg_monthly_deposit",
    "deposit_to_income_ratio",
    "deposit_consistency",
    "min_extraction_confidence",
    "avg_extraction_confidence",
    "low_confidence_fields_count",
    "critical_findings_count",
    "warning_findings_count",
    "total_findings_count",
    "fraud_flags_count",
    "documents_count",
]


def extract_features_from_loan_file(loan_file: Dict[str, Any]) -> Dict[str, float]:
    """Extract engineered numerical features from a validated loan file.

    Args:
        loan_file: Dictionary following loan_file.schema.json

    Returns:
        Dictionary mapping feature name to float value.
    """
    applicant = loan_file.get("applicant") or {}
    declared_income = float(applicant.get("declared_income") or 0.0)
    loan_amount = float(applicant.get("loan_amount_requested") or 0.0)

    # Calculate basic income-to-loan ratio
    income_to_loan_ratio = declared_income / max(loan_amount, 1.0)

    # Parse extracted fields
    extracted_fields = loan_file.get("extracted_fields") or []
    gross_monthly_income = declared_income
    avg_monthly_deposit = declared_income

    confidences: List[float] = []
    low_conf_count = 0

    for field in extracted_fields:
        name = field.get("field_name", "")
        conf = float(field.get("confidence", 1.0))
        confidences.append(conf)

        if field.get("needs_review") or conf < 0.8:
            low_conf_count += 1

        val = field.get("value")
        if name == "gross_monthly_income" and isinstance(val, (int, float)):
            gross_monthly_income = float(val)
        elif name == "avg_monthly_deposit" and isinstance(val, (int, float)):
            avg_monthly_deposit = float(val)

    # Deposit vs income consistency
    deposit_to_income_ratio = (
        avg_monthly_deposit / max(gross_monthly_income, 1.0)
        if gross_monthly_income > 0
        else 1.0
    )
    denom = max(gross_monthly_income, avg_monthly_deposit, 1.0)
    deposit_consistency = max(0.0, 1.0 - (abs(gross_monthly_income - avg_monthly_deposit) / denom))

    min_conf = min(confidences) if confidences else 1.0
    avg_conf = (sum(confidences) / len(confidences)) if confidences else 1.0

    # Parse validation findings and fraud flags
    validation_findings = loan_file.get("validation_findings") or []
    critical_count = sum(1 for vf in validation_findings if vf.get("severity") == "critical")
    warning_count = sum(1 for vf in validation_findings if vf.get("severity") == "warning")
    total_findings = len(validation_findings)

    fraud_flags = loan_file.get("fraud_flags") or []
    fraud_count = len(fraud_flags)

    documents = loan_file.get("documents") or []
    doc_count = len(documents)

    return {
        "declared_income": declared_income,
        "loan_amount_requested": loan_amount,
        "income_to_loan_ratio": round(income_to_loan_ratio, 4),
        "gross_monthly_income": gross_monthly_income,
        "avg_monthly_deposit": avg_monthly_deposit,
        "deposit_to_income_ratio": round(deposit_to_income_ratio, 4),
        "deposit_consistency": round(deposit_consistency, 4),
        "min_extraction_confidence": round(min_conf, 4),
        "avg_extraction_confidence": round(avg_conf, 4),
        "low_confidence_fields_count": float(low_conf_count),
        "critical_findings_count": float(critical_count),
        "warning_findings_count": float(warning_count),
        "total_findings_count": float(total_findings),
        "fraud_flags_count": float(fraud_count),
        "documents_count": float(doc_count),
    }


def validate_feature_safety(feature_names: List[str]) -> List[str]:
    """Check whether any protected demographic attributes exist in the feature set.

    Returns:
        List of violating feature names (empty if completely clean).
    """
    violations = []
    for feat in feature_names:
        normalized = feat.strip().lower()
        for protected in PROTECTED_ATTRIBUTES:
            if protected == normalized or f"_{protected}" in normalized or f"{protected}_" in normalized:
                violations.append(feat)
                break
    return violations
