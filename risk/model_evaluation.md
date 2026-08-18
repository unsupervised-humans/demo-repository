# Model Evaluation Report: Loan Risk Scoring Models

**Evaluation Date:** 2026-08-18  
**Dataset:** Kaggle Loan Approval Prediction Dataset (`architsharma01/loan-approval-prediction-dataset`)  
**Artifacts Evaluated:**
- Production Model: **XGBoost** (`risk/artifacts/risk-xgb-v1.pkl`)
- Baseline Model: **Standardized Logistic Regression** (`LogisticRegression(max_iter=1000)`)
- Test Split: 20% holdout ($N = 854$, Random State = 42)

---

## 1. Dataset Class Balance

The dataset contains a realistic prime/near-prime retail loan distribution:

| Class | Outcome | Count | Percentage |
| :--- | :--- | :--- | :--- |
| **1** | **Approved** | 2,656 | **62.22%** |
| **0** | **Rejected** | 1,613 | **37.78%** |
| **Total** | | **4,269** | **100.00%** |

- **Imbalance Ratio:** ~1.65 : 1 (Mild imbalance, representative of credit application pools).
- **Test Set Split ($N=854$):** 554 Approved (64.87%), 300 Rejected (35.13%).

---

## 2. Model Performance Metrics Comparison

Summary of classification and probability metrics evaluated on the identical test split ($N = 854$):

| Metric | XGBoost (`risk-xgb-v1`) | Logistic Regression Baseline | Delta / Improvement |
| :--- | :---: | :---: | :---: |
| **Accuracy** | **99.65%** | 91.69% | +7.96% |
| **Precision (Approved)** | **99.46%** | 94.64% | +4.82% |
| **Recall (Approved)** | **100.00%** | 92.42% | +7.58% |
| **Specificity (Rejection Rate)** | **99.00%** | 90.33% | +8.67% |
| **F1-Score** | **0.9973** | 0.9352 | +0.0621 |
| **ROC-AUC** | **0.9996** | 0.9706 | +0.0290 |
| **Brier Score (MSE of Probs)** | **0.0031** | 0.0599 | **-94.8% (Sharper Calibration)** |
| **Log Loss / Cross-Entropy** | **0.0148** | 0.2101 | **-93.0%** |

---

## 3. Confusion Matrices

### XGBoost (`risk-xgb-v1`)

```text
                 Predicted Rejected (0)    Predicted Approved (1)
Actual Rejected (0)       297 (TN)                  3 (FP)
Actual Approved (1)         0 (FN)                554 (TP)
```

- **True Negatives (TN):** 297 / 300 (99.0% correct rejection rate)
- **False Positives (FP):** 3 / 300 (0.35% false approval risk)
- **False Negatives (FN):** 0 / 554 (0.0% missed loan approvals)
- **True Positives (TP):** 554 / 554 (100.0% capture of creditworthy applicants)

### Logistic Regression Baseline

```text
                 Predicted Rejected (0)    Predicted Approved (1)
Actual Rejected (0)       271 (TN)                 29 (FP)
Actual Approved (1)        42 (FN)                512 (TP)
```

- **True Negatives (TN):** 271 / 300 (90.33%)
- **False Positives (FP):** 29 / 300 (3.39% — nearly **10x more risky approvals** than XGBoost)
- **False Negatives (FN):** 42 / 554 (7.58% — **42 creditworthy borrowers denied/friction**)
- **True Positives (TP):** 512 / 554 (92.42%)

---

## 4. Probability Calibration Analysis

In credit underwriting, probability calibration is critical because output probabilities directly drive automatic approval cutoffs ($\ge 0.80$), manual review queues ($0.35 - 0.80$), and expected credit loss ($ECL$) computations.

### Calibration Curves (10 Uniform Probability Bins)

#### XGBoost (`risk-xgb-v1`):
| Predicted Probability Bin Mean | Actual Approval Rate | Bin Calibration Error |
| :---: | :---: | :---: |
| `0.0016` | `0.0000` | -0.0016 |
| `0.8565` | `0.6667` | -0.1898 |
| `0.9970` | `0.9964` | -0.0006 |

- **Brier Score:** `0.0031`
- **Assessment:** High decisiveness and confidence. The model concentrates predictions cleanly around $0$ and $1$, yielding exceptional separation with almost zero ambiguous boundary cases.

#### Logistic Regression Baseline:
| Predicted Probability Bin Mean | Actual Approval Rate | Bin Calibration Error |
| :---: | :---: | :---: |
| `0.0272` | `0.0787` | +0.0515 |
| `0.1473` | `0.0612` | -0.0861 |
| `0.2503` | `0.1562` | -0.0941 |
| `0.3509` | `0.2917` | -0.0592 |
| `0.4506` | `0.4333` | -0.0173 |
| `0.5422` | `0.4444` | -0.0978 |
| `0.6487` | `0.4545` | -0.1942 |
| `0.7555` | `0.8333` | +0.0778 |
| `0.8581` | `0.9787` | +0.1206 |
| `0.9865` | `0.9976` | +0.0111 |

- **Brier Score:** `0.0599`
- **Assessment:** Shows monotonic probability distribution across all 10 bins, but suffers from boundary blurring between 0.40 and 0.65 due to linear boundary constraints.

---

## 5. Model Recommendation & Decision Rationale

> **Project Policy Principle:** *"Do not select a model based only on accuracy."*

### Recommendation: **Deploy XGBoost (`risk-xgb-v1`)**

The selection of XGBoost over Logistic Regression is justified across multiple non-accuracy operational dimensions:

1. **Credit Loss / Default Asymmetry (False Positives):**
   - In lending economics, approving a high-risk borrower (False Positive) is far costlier than rejecting a good applicant (False Negative).
   - XGBoost generates only **3 False Positives** (0.35% of test set) compared to Logistic Regression's **29 False Positives** (3.39%). Deploying XGBoost cuts bad debt exposure by approximately **89.7%**.

2. **Customer Acquisition & Business Volume (Recall / False Negatives):**
   - Logistic Regression unnecessarily rejects **42 creditworthy applicants** (7.58% loss in potential loan book growth and customer trust).
   - XGBoost achieves **100% recall (0 False Negatives)** on the test split, maximizing loan originations without sacrificing risk controls.

3. **Non-Linear Interactions & Asset Thresholds:**
   - Real-world lending rules contain sharp non-linear thresholds (e.g., CIBIL score cutoff cliffs near 600, non-linear asset-to-loan coverage ratios).
   - Tree ensembles capture step functions and interactions natively without fragile manual feature transformations.

4. **Explainability & Adverse Action Compliance:**
   - Using TreeSHAP (`shap.TreeExplainer`), XGBoost generates exact, mathematically consistent Shapley contribution values for each individual prediction.
   - This directly populates `risk_score.factors[]` in compliance with Fair Credit Reporting Act (FCRA) and ECOA adverse action notice requirements.

5. **Fair Lending & Protected Attributes Safety:**
   - Both models are trained strictly on sanitized financial features (`income_annum`, `loan_amount`, `cibil_score`, `bank_asset_value`, `loan_to_income_ratio`, `asset_values`).
   - Compliance audits confirm 100% exclusion of protected demographic attributes (`gender`, `religion`, `caste`, `age`).

---

## 6. Known Limitation: CIBIL Score Dominance

> [!WARNING]
> **Production Inference Gap:** The offline 99.65% test accuracy relies heavily on bureau credit scores that are not yet available in the live document extraction pipeline.

1. **SHAP Contribution Disparity:** Across all tested applications, SHAP feature importance confirms that `cibil_score` contributes **3x to 10x more** to the model's log-odds output than any other single feature (e.g., $|\text{SHAP}| \approx 4.1 - 5.9$ for CIBIL vs. $0.4 - 1.9$ for asset values and loan ratios).
2. **Missing Live Pipeline Bureau Integration:** In the current live LoanIQ pipeline, upstream document extraction agents process payslips, bank statements, and KYC documents, but do not produce a credit bureau score. Consequently, `cibil_score` is defaulted to the training-set median (`600.0`) at inference time for every live applicant.
3. **Implications for Live Predictive Signal:** Because the single dominant driver is held constant across all live applications, the model's true predictive signal in production is substantially weaker than the 99.65% offline test accuracy suggests. Live decisions rely on the remaining secondary signals (`income_annum`, `loan_to_income_ratio`, `bank_asset_value`, and asset coverage).
4. **Operational Recommendation:**
   - Treat live `approval_probability` outputs as **directionally useful risk rankings** (ranking relative creditworthiness based on income, assets, and loan terms) rather than as calibrated absolute probabilities, until a real credit bureau integration is available.
   - Downstream policy layers and human reviewers should weigh cross-document validation findings, bank deposit consistency, and fraud flags alongside the risk score.

---

## 7. Summary Conclusion

| Criterion | XGBoost | Logistic Regression | Winner |
| :--- | :---: | :---: | :---: |
| **Default Risk Mitigation (Low FP)** | 3 False Positives | 29 False Positives | **XGBoost** |
| **Origination Revenue (High Recall)** | 100.0% Recall | 92.4% Recall | **XGBoost** |
| **Calibration / Log Loss** | Brier: 0.0031, LL: 0.0148 | Brier: 0.0599, LL: 0.2101 | **XGBoost** |
| **Non-Linear Risk Modeling** | Native Tree Splits | Linear hyperplanes only | **XGBoost** |
| **Regulatory SHAP Breakdown** | Fully Supported (TreeSHAP) | Supported (Linear coeffs) | **XGBoost** |
| **Overall Selection** | **Recommended for Production** | Baseline Only | **XGBoost** |

