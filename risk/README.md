# risk — Rohit

Owns: risk scoring model, compliance & fairness agent.

Reads `loan_file.extracted_fields[]` + `loan_file.validation_findings[]`, writes `loan_file.risk_score` and `loan_file.compliance`.

## Checklist
- [ ] Train a classical model (XGBoost / logistic regression) on the Kaggle loan-approval-prediction dataset
- [ ] Wrap it as an agent: input engineered features, output `approval_probability`
- [ ] Add a SHAP-style (or similar) factor breakdown — populate `risk_score.factors[]`, most influential first
- [ ] Compliance agent: confirm no protected attributes (gender, religion, caste, age) feed the score
- [ ] Populate `compliance.bias_check_passed` and `compliance.protected_attributes_excluded`
- [ ] Write an entry to `audit_log` when scoring and compliance checks run

## Test against
`/schema/loan_file.example.json` — its `risk_score` and `compliance` blocks show the exact expected shape.
