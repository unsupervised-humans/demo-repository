"""Feature extraction and engineering for loan risk assessment.

Extracts numerical features matching the Kaggle Loan Approval Prediction Dataset
from loan_file dictionaries, defaulting unextracted fields with documented medians
and ensuring protected demographic attributes are strictly excluded.
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

# Standard feature names in exact model order (matching Kaggle Loan Approval dataset)
NUMERIC_FEATURE_NAMES: List[str] = [
    "no_of_dependents",
    "education",
    "self_employed",
    "income_annum",
    "loan_amount",
    "loan_term",
    "cibil_score",
    "residential_assets_value",
    "commercial_assets_value",
    "luxury_assets_value",
    "bank_asset_value",
    "loan_to_income_ratio",
]

# Documented default/median values from training data for fields without live pipeline equivalents
DEFAULT_FEATURE_VALUES: Dict[str, float] = {
    "no_of_dependents": 2.0,
    "education": 1.0,  # 1 = Graduate, 0 = Not Graduate
    "self_employed": 0.0,  # 1 = Yes, 0 = No
    "loan_term": 10.0,  # Median loan term in years
    "cibil_score": 600.0,  # Median CIBIL credit score
    "residential_assets_value": 5600000.0,  # Median residential asset value
    "commercial_assets_value": 3700000.0,  # Median commercial asset value
    "luxury_assets_value": 14600000.0,  # Median luxury asset value
    "bank_asset_value": 4600000.0,  # Median bank asset value
}


def extract_features_from_loan_file(loan_file: Dict[str, Any]) -> Dict[str, Any]:
    """Extract model features from a validated loan file.

    For fields with live pipeline equivalents (income_annum, loan_amount, bank_asset_value),
    values are extracted from applicant metadata and extracted_fields.
    For fields with no live pipeline equivalent (cibil_score, asset values, loan_term),
    documented training medians are used and recorded in 'data_completeness_note'.

    Args:
        loan_file: Dictionary following loan_file.schema.json

    Returns:
        Dictionary containing all numerical features plus 'data_completeness_note'.
    """
    applicant = loan_file.get("applicant") or {}
    declared_income = float(applicant.get("declared_income") or 0.0)
    loan_amount = float(applicant.get("loan_amount_requested") or 0.0)

    # In loanIQ, monthly incomes are standard; convert to annual if monthly (< 1,000,000)
    income_annum = declared_income * 12.0 if 0 < declared_income < 1000000 else declared_income

    extracted_fields = loan_file.get("extracted_fields") or []
    extracted_map: Dict[str, Any] = {}

    for field in extracted_fields:
        name = field.get("field_name", "").strip().lower()
        val = field.get("value")
        extracted_map[name] = val

        if name == "gross_monthly_income" and isinstance(val, (int, float)):
            income_annum = float(val) * 12.0
        elif name == "annual_income" and isinstance(val, (int, float)):
            income_annum = float(val)
        elif name == "loan_amount" and isinstance(val, (int, float)):
            loan_amount = float(val)

    # Track fields that were defaulted
    defaulted_fields: List[str] = []

    # 1. no_of_dependents
    if "no_of_dependents" in extracted_map and isinstance(extracted_map["no_of_dependents"], (int, float)):
        no_of_dependents = float(extracted_map["no_of_dependents"])
    elif "dependents" in extracted_map and isinstance(extracted_map["dependents"], (int, float)):
        no_of_dependents = float(extracted_map["dependents"])
    else:
        no_of_dependents = DEFAULT_FEATURE_VALUES["no_of_dependents"]
        defaulted_fields.append("no_of_dependents")

    # 2. education (1: Graduate, 0: Not Graduate)
    if "education" in extracted_map:
        edu_str = str(extracted_map["education"]).strip().lower()
        education = 1.0 if "grad" in edu_str else 0.0
    else:
        education = DEFAULT_FEATURE_VALUES["education"]
        defaulted_fields.append("education")

    # 3. self_employed (1: Yes, 0: No)
    if "self_employed" in extracted_map:
        se_str = str(extracted_map["self_employed"]).strip().lower()
        self_employed = 1.0 if se_str in ("yes", "true", "1") else 0.0
    elif "employment_type" in extracted_map:
        emp_type = str(extracted_map["employment_type"]).strip().lower()
        self_employed = 1.0 if "self" in emp_type or "business" in emp_type else 0.0
    else:
        self_employed = DEFAULT_FEATURE_VALUES["self_employed"]
        defaulted_fields.append("self_employed")

    # 4. loan_term
    if "loan_term" in extracted_map and isinstance(extracted_map["loan_term"], (int, float)):
        loan_term = float(extracted_map["loan_term"])
    elif "tenure_years" in extracted_map and isinstance(extracted_map["tenure_years"], (int, float)):
        loan_term = float(extracted_map["tenure_years"])
    else:
        loan_term = DEFAULT_FEATURE_VALUES["loan_term"]
        defaulted_fields.append("loan_term")

    # 5. cibil_score
    if "cibil_score" in extracted_map and isinstance(extracted_map["cibil_score"], (int, float)):
        cibil_score = float(extracted_map["cibil_score"])
    elif "credit_score" in extracted_map and isinstance(extracted_map["credit_score"], (int, float)):
        cibil_score = float(extracted_map["credit_score"])
    else:
        cibil_score = DEFAULT_FEATURE_VALUES["cibil_score"]
        defaulted_fields.append("cibil_score")

    # 6. bank_asset_value (pull from avg_monthly_deposit if available)
    if "avg_monthly_deposit" in extracted_map and isinstance(extracted_map["avg_monthly_deposit"], (int, float)):
        bank_asset_value = float(extracted_map["avg_monthly_deposit"]) * 12.0
    elif "bank_asset_value" in extracted_map and isinstance(extracted_map["bank_asset_value"], (int, float)):
        bank_asset_value = float(extracted_map["bank_asset_value"])
    else:
        bank_asset_value = DEFAULT_FEATURE_VALUES["bank_asset_value"]
        defaulted_fields.append("bank_asset_value")

    # 7. Asset values
    if "residential_assets_value" in extracted_map and isinstance(extracted_map["residential_assets_value"], (int, float)):
        residential_assets = float(extracted_map["residential_assets_value"])
    else:
        residential_assets = DEFAULT_FEATURE_VALUES["residential_assets_value"]
        defaulted_fields.append("residential_assets_value")

    if "commercial_assets_value" in extracted_map and isinstance(extracted_map["commercial_assets_value"], (int, float)):
        commercial_assets = float(extracted_map["commercial_assets_value"])
    else:
        commercial_assets = DEFAULT_FEATURE_VALUES["commercial_assets_value"]
        defaulted_fields.append("commercial_assets_value")

    if "luxury_assets_value" in extracted_map and isinstance(extracted_map["luxury_assets_value"], (int, float)):
        luxury_assets = float(extracted_map["luxury_assets_value"])
    else:
        luxury_assets = DEFAULT_FEATURE_VALUES["luxury_assets_value"]
        defaulted_fields.append("luxury_assets_value")

    # Derived feature: loan_to_income_ratio
    loan_to_income_ratio = loan_amount / max(income_annum, 1.0)

    # Completeness note
    if defaulted_fields:
        data_completeness_note = (
            f"Features defaulted from training dataset medians: {', '.join(defaulted_fields)}"
        )
    else:
        data_completeness_note = "All features extracted from live pipeline data."

    return {
        "no_of_dependents": float(no_of_dependents),
        "education": float(education),
        "self_employed": float(self_employed),
        "income_annum": float(income_annum),
        "loan_amount": float(loan_amount),
        "loan_term": float(loan_term),
        "cibil_score": float(cibil_score),
        "residential_assets_value": float(residential_assets),
        "commercial_assets_value": float(commercial_assets),
        "luxury_assets_value": float(luxury_assets),
        "bank_asset_value": float(bank_asset_value),
        "loan_to_income_ratio": round(float(loan_to_income_ratio), 4),
        "data_completeness_note": data_completeness_note,
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
