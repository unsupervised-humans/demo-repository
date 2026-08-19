"""Feature extraction and engineering for loan risk assessment.

Extracts numerical features matching the Kaggle Loan Approval Prediction Dataset
from loan_file dictionaries, defaulting unextracted fields with documented medians
and ensuring protected demographic attributes are strictly excluded.

Pre-validation Gate
-------------------
``validate_mandatory_features()`` checks whether the minimum required data is
present before calling the XGBoost model.  If income and loan amount are both
zero (indicating extraction failure), the model MUST NOT be called, because:

  - Default asset imputation (~28.5M INR total) with 0 income and 0 loan amount
    causes the XGBoost model to output approval_probability = 1.0.
  - This would be a dangerously misleading result when data extraction failed.

When mandatory features are missing, the risk scoring agent returns
{"status": "INSUFFICIENT_DATA", "approval_probability": None, ...} and the
decision agent escalates to human review.
"""

from __future__ import annotations

from typing import Any, Dict, List, Set, Tuple

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
    # Asset values default to 0 (not the training median) so the model
    # does not auto-approve applicants whose assets were never extracted.
    # Using the training medians (₹5.6M residential, ₹14.6M luxury, etc.)
    # caused the model to output ~100% approval for every application.
    "residential_assets_value": 0.0,
    "commercial_assets_value": 0.0,
    "luxury_assets_value": 0.0,
    "bank_asset_value": 0.0,
}

# Total default asset value (used to detect all-default imputation state)
_TOTAL_DEFAULT_ASSETS = (
    DEFAULT_FEATURE_VALUES["residential_assets_value"]
    + DEFAULT_FEATURE_VALUES["commercial_assets_value"]
    + DEFAULT_FEATURE_VALUES["luxury_assets_value"]
    + DEFAULT_FEATURE_VALUES["bank_asset_value"]
)


def _clean_numeric(val: Any) -> float | None:
    """Robustly parse a numeric value from float, int, or string representations."""
    if isinstance(val, (int, float)):
        return float(val)
    if isinstance(val, str):
        # Keep only digits, periods, and minus sign to handle currency formatting and commas
        cleaned = "".join(c for c in val if c.isdigit() or c in (".", "-"))
        try:
            return float(cleaned)
        except ValueError:
            return None
    return None


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
    declared_income = _clean_numeric(applicant.get("declared_income")) or 0.0
    loan_amount = _clean_numeric(applicant.get("loan_amount_requested")) or 0.0

    # In loanIQ, monthly incomes are standard; convert to annual if monthly (< 1,000,000)
    income_annum = declared_income * 12.0 if 0 < declared_income < 1000000 else declared_income

    extracted_fields = loan_file.get("extracted_fields") or []
    extracted_map: Dict[str, Any] = {}

    for field in extracted_fields:
        name = (field.get("field_name") or "").strip().lower()
        val = field.get("value")
        confidence = 0.0
        try:
            confidence = float(field.get("confidence") or 0.0)
        except (TypeError, ValueError):
            confidence = 0.0

        # Skip extraction failure sentinels and very-low-confidence fields
        if name.startswith("extraction_failure_"):
            continue

        # Only use fields with meaningful confidence
        if confidence > 0.0 and val is not None:
            extracted_map[name] = val

        if name == "gross_monthly_income" and confidence > 0.0:
            parsed_income = _clean_numeric(val)
            if parsed_income is not None:
                income_annum = parsed_income * 12.0
        elif name == "annual_income" and confidence > 0.0:
            parsed_income = _clean_numeric(val)
            if parsed_income is not None:
                income_annum = parsed_income
        elif name == "loan_amount" and confidence > 0.0:
            parsed_amt = _clean_numeric(val)
            if parsed_amt is not None:
                loan_amount = parsed_amt
        elif name == "loan_amount_requested" and confidence > 0.0:
            parsed_amt = _clean_numeric(val)
            if parsed_amt is not None and loan_amount == 0.0:
                loan_amount = parsed_amt

    # Track fields that were defaulted
    defaulted_fields: List[str] = []

    # 1. no_of_dependents
    if "no_of_dependents" in extracted_map and _clean_numeric(extracted_map["no_of_dependents"]) is not None:
        no_of_dependents = float(_clean_numeric(extracted_map["no_of_dependents"]))
    elif "dependents" in extracted_map and _clean_numeric(extracted_map["dependents"]) is not None:
        no_of_dependents = float(_clean_numeric(extracted_map["dependents"]))
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
    if "loan_term" in extracted_map and _clean_numeric(extracted_map["loan_term"]) is not None:
        loan_term = float(_clean_numeric(extracted_map["loan_term"]))
    elif "tenure_years" in extracted_map and _clean_numeric(extracted_map["tenure_years"]) is not None:
        loan_term = float(_clean_numeric(extracted_map["tenure_years"]))
    else:
        loan_term = DEFAULT_FEATURE_VALUES["loan_term"]
        defaulted_fields.append("loan_term")

    # 5. cibil_score — extracted from application document CIBIL section
    if "cibil_score" in extracted_map and _clean_numeric(extracted_map["cibil_score"]) is not None:
        raw_cibil = float(_clean_numeric(extracted_map["cibil_score"]))
        cibil_score = max(300.0, min(900.0, raw_cibil))  # clamp to valid range
    elif "credit_score" in extracted_map and _clean_numeric(extracted_map["credit_score"]) is not None:
        raw_cibil = float(_clean_numeric(extracted_map["credit_score"]))
        cibil_score = max(300.0, min(900.0, raw_cibil))  # clamp to valid range
    else:
        cibil_score = DEFAULT_FEATURE_VALUES["cibil_score"]
        defaulted_fields.append("cibil_score")

    # 6. bank_asset_value (pull from avg_monthly_deposit if available)
    if "avg_monthly_deposit" in extracted_map and _clean_numeric(extracted_map["avg_monthly_deposit"]) is not None:
        bank_asset_value = float(_clean_numeric(extracted_map["avg_monthly_deposit"])) * 12.0
    elif "bank_asset_value" in extracted_map and _clean_numeric(extracted_map["bank_asset_value"]) is not None:
        bank_asset_value = float(_clean_numeric(extracted_map["bank_asset_value"]))
    else:
        bank_asset_value = DEFAULT_FEATURE_VALUES["bank_asset_value"]
        defaulted_fields.append("bank_asset_value")

    # 7. Asset values
    if "residential_assets_value" in extracted_map and _clean_numeric(extracted_map["residential_assets_value"]) is not None:
        residential_assets = float(_clean_numeric(extracted_map["residential_assets_value"]))
    else:
        residential_assets = DEFAULT_FEATURE_VALUES["residential_assets_value"]
        defaulted_fields.append("residential_assets_value")

    if "commercial_assets_value" in extracted_map and _clean_numeric(extracted_map["commercial_assets_value"]) is not None:
        commercial_assets = float(_clean_numeric(extracted_map["commercial_assets_value"]))
    else:
        commercial_assets = DEFAULT_FEATURE_VALUES["commercial_assets_value"]
        defaulted_fields.append("commercial_assets_value")

    if "luxury_assets_value" in extracted_map and _clean_numeric(extracted_map["luxury_assets_value"]) is not None:
        luxury_assets = float(_clean_numeric(extracted_map["luxury_assets_value"]))
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
        "_defaulted_fields": defaulted_fields,
        "cibil_tier": get_cibil_tier(cibil_score),
    }


def get_cibil_tier(score: float) -> dict:
    """Classify a CIBIL score into the standard Indian credit rating tiers.

    Tiers (per TransUnion CIBIL / Indian lending standards):
        Poor      300 – 619
        Fair      620 – 659
        Good      660 – 719
        Great     720 – 749
        Excellent 750 – 900

    Returns
    -------
    dict with keys: label, color, min_score, max_score, description
    """
    s = float(score)
    if s >= 750:
        return {"label": "Excellent", "color": "#1a7a2e", "min_score": 750, "max_score": 900,
                "description": "Very high creditworthiness. Best loan terms available."}
    if s >= 720:
        return {"label": "Great", "color": "#5a9e1a", "min_score": 720, "max_score": 749,
                "description": "Strong credit profile. Favourable loan terms likely."}
    if s >= 660:
        return {"label": "Good", "color": "#c8b200", "min_score": 660, "max_score": 719,
                "description": "Acceptable creditworthiness. Standard terms apply."}
    if s >= 620:
        return {"label": "Fair", "color": "#e07b00", "min_score": 620, "max_score": 659,
                "description": "Marginal credit profile. May require higher interest."}
    return {"label": "Poor", "color": "#cc2200", "min_score": 300, "max_score": 619,
            "description": "High credit risk. Loan approval unlikely without collateral."}


def validate_mandatory_features(features: Dict[str, Any]) -> Tuple[bool, List[str]]:
    """Check whether minimum mandatory features are present for risk scoring.

    A risk score is meaningful when at least ONE of these is non-zero:
    - income_annum > 0 (income was extracted from documents)
    - loan_amount > 0 (loan amount was provided or extracted)

    With asset defaults now set to 0 (not large training medians), the
    previous risk of a misleading 1.0 score from all-default assets is
    eliminated. The model can now score safely whenever any core financial
    data is present.

    Returns
    -------
    (is_sufficient, missing_mandatory_list)
        is_sufficient: True if the model can be called safely.
        missing_mandatory_list: Human-readable list of what's missing.
    """
    income = float(features.get("income_annum") or 0.0)
    loan = float(features.get("loan_amount") or 0.0)

    missing: List[str] = []

    if income == 0.0:
        missing.append("income_annum (zero - likely extraction failure)")

    if loan == 0.0:
        missing.append("loan_amount (zero - not extracted or provided)")

    # Sufficient if either income or loan amount is known
    is_sufficient = income > 0.0 or loan > 0.0

    return is_sufficient, missing



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
