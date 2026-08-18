# Risk Scoring & Compliance Module (`risk/`) — Rohit

Owns the **Risk Scoring Agent** and **Compliance & Fairness Agent** for the LoanIQ pipeline.

---

## 1. Overview

The `risk/` module sits between upstream document analysis and downstream orchestrator summarization in the loan decision lifecycle:

- **Pipeline Position:**
  - **Inputs:** Consumes extracted document fields (`loan_file.extracted_fields[]`), applicant metadata (`loan_file.applicant`), cross-document validation findings (`loan_file.validation_findings[]`), fraud flags (`loan_file.fraud_flags[]`), and missing documents (`loan_file.missing_documents[]`).
  - **Outputs:** Populates `loan_file.risk_score` (approval probability + SHAP factor breakdown) and `loan_file.compliance` (bias check audit), and appends to `loan_file.audit_log[]` per [`schema/loan_file.schema.json`](../schema/loan_file.schema.json).

---

## 2. Dataset

Trained on the Kaggle [Loan Approval Prediction Dataset](https://www.kaggle.com/datasets/architsharma01/loan-approval-prediction-dataset) (`architsharma01/loan-approval-prediction-dataset`):
- **Provenance & License:** Public Kaggle dataset (CC0: Public Domain).
- **Dimensions:** 4,269 records $\times$ 13 features.
- **Class Balance:** 2,656 Approved (62.22%) / 1,613 Rejected (37.78%).
- **Local Storage:** Cached at [`risk/data/raw/loan_approval_dataset.csv`](data/raw/loan_approval_dataset.csv).

---

## 3. Feature Engineering

The production feature matrix uses 12 numerical features defined in [`NUMERIC_FEATURE_NAMES`](features.py):

| Feature Name | Description | Source in Live Pipeline |
| :--- | :--- | :--- |
| `income_annum` | Annualized declared/extracted income | Live (`gross_monthly_income * 12` / `declared_income`) |
| `loan_amount` | Requested principal loan amount | Live (`loan_amount_requested`) |
| `bank_asset_value` | Bank deposits & liquid cash | Live (`avg_monthly_deposit * 12`) or default (₹46L) |
| `loan_to_income_ratio` | Derived: `loan_amount / income_annum` | Derived live |
| `education` | Binary (1.0 = Graduate, 0.0 = Non-Grad) | Extracted if present, default (1.0) |
| `self_employed` | Binary (1.0 = Yes, 0.0 = No) | Extracted if present, default (0.0) |
| `no_of_dependents` | Number of financial dependents | Extracted if present, default (2.0) |
| `loan_term` | Tenure in years | Extracted if present, default (10.0 yrs) |
| `cibil_score` | Credit bureau score | Defaulted to training median (600.0) — *see limitation* |
| `residential_assets_value` | Property valuation | Defaulted to training median (₹56L) |
| `commercial_assets_value` | Commercial assets | Defaulted to training median (₹37L) |
| `luxury_assets_value` | Vehicles, jewelry, etc. | Defaulted to training median (₹1.46Cr) |

*For unextracted fields, documented training medians are applied, and tracked in `data_completeness_note`. See [Known Limitation: CIBIL Score Dominance](model_evaluation.md#6-known-limitation-cibil-score-dominance).*

---

## 4. Model Architecture & Selection

We evaluated a Standardized Logistic Regression baseline against an XGBoost classifier:
- **Baseline:** Logistic Regression ($91.69\%$ accuracy, $0.9706$ ROC-AUC, $29$ False Positives).
- **Production Model:** **XGBoost** ($99.65\%$ accuracy, $0.9996$ ROC-AUC, $3$ False Positives, Brier score $0.0031$).

> **Model Decision Rationale:** Per the project principle (*"Do not select a model based only on accuracy"*), **XGBoost (`risk-xgb-v1.pkl`)** was selected because it reduces high-cost False Positive credit default risk by $\sim 90\%$ (3 vs 29), captures $100\%$ of creditworthy applicants (0 false rejections), and handles non-linear asset/credit thresholds natively.
> 
> *Full evaluation metrics, confusion matrices, and calibration curves are documented in [`risk/model_evaluation.md`](model_evaluation.md).*

---

## 5. Explainability (SHAP)

[`risk/explain.py`](explain.py) integrates `shap.TreeExplainer` to calculate exact instance-level Shapley values:
- Populates `risk_score.factors[]` sorted by descending absolute influence.
- Positive values push toward approval; negative values push away from approval.
- Generates adverse action notice drivers compliant with FCRA/ECOA guidelines.
- Sample outputs are demonstrated in [`risk/samples/mock_loan_file_scored.json`](samples/mock_loan_file_scored.json).

---

## 6. Compliance & Fairness

[`risk/compliance.py`](compliance.py) audits features and pipeline inputs:
- **Anti-Bias Guarantee:** Strictly verifies that protected demographic attributes (`gender`, `religion`, `caste`, `age`, `marital_status`, `nationality`) are excluded from model features.
- **Fairness Report:** Populates `compliance.bias_check_passed` (`true`) and lists `protected_attributes_excluded`.
- **Policy on Missing Documents:** In accordance with project policy, missing documents trigger underwriter review or information requests (`more_docs_requested`), **not** automatic fraud rejection or score zeroing.

---

## 7. Project Structure

```text
risk/
├── README.md                  # Module documentation (this file)
├── model_evaluation.md        # Detailed evaluation metrics, calibration & limitations
├── requirements.txt           # Pinned module dependencies
├── __init__.py                # Public interface exports
├── dataset.py                 # Kaggle loader & synthetic testing data generator
├── features.py                # Feature engineering, defaults & safety checks
├── model.py                   # XGBoost / sklearn model wrapper & serialization
├── train.py                   # Model training and artifact generation script
├── predict.py                 # RiskScoringAgent & pipeline orchestrator integration
├── explain.py                 # SHAP TreeExplainer factor attribution
├── compliance.py              # ComplianceAgent & fairness verification
├── policy.py                  # Underwriting thresholds and risk tier rules
├── artifacts/
│   ├── .gitkeep
│   └── risk-xgb-v1.pkl       # Serialized production XGBoost model
├── data/
│   └── raw/
│       └── loan_approval_dataset.csv  # Kaggle training dataset
├── samples/
│   └── mock_loan_file_scored.json     # Schema-validated end-to-end sample
└── tests/
    ├── test_compliance.py     # Anti-bias audit unit tests
    ├── test_dataset.py        # Dataset loading & split tests
    ├── test_explainability.py # SHAP factor attribution tests
    ├── test_features.py       # Feature extraction & safety tests
    ├── test_model.py          # Model training, inference & persistence tests
    └── test_prediction.py     # End-to-end schema compliance tests
```

---

## 8. How to Run

### Install Dependencies
```bash
pip install -r risk/requirements.txt
```

### Train Baseline & Production Models
```bash
python -m risk.train
```

### Run Test Suite
```bash
pytest risk/tests -v
```

### Run a Sample Prediction
```python
from risk.predict import process_risk_assessment
from shared.schema_loader import validate_loan_file

loan_file = { ... }  # Valid loan_file dictionary
scored_file = process_risk_assessment(loan_file)
validate_loan_file(scored_file)
print("Approval Probability:", scored_file["risk_score"]["approval_probability"])
print("Top Factors:", scored_file["risk_score"]["factors"])
```

---

## 9. Known Limitations & Open Items

1. **CIBIL Score Dominance:** As documented in [`risk/model_evaluation.md#6-known-limitation-cibil-score-dominance`](model_evaluation.md#6-known-limitation-cibil-score-dominance), `cibil_score` is the dominant feature in training data (contributing 3-10x more than other features), but is currently defaulted in live production because document extraction does not source bureau scores. Live probabilities should be treated as relative risk rankings until live bureau integration is added.
2. **Protected Attributes List Alignment (Open Item):** Standard schema output explicitly reports `["gender", "religion", "caste", "age"]` in `compliance.protected_attributes_excluded`, while internal safety filter `PROTECTED_ATTRIBUTES` in `features.py` enforces a broader list (including `race`, `nationality`, `marital_status`, `disability`). Full synchronization across all agent contracts is tracked for the next schema iteration.
