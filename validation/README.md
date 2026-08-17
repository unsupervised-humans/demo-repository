# validation — alina

Owns: cross-document validation agent, missing-document agent, fraud/anomaly detection agent.

Reads `loan_file.extracted_fields[]`, writes `loan_file.validation_findings[]`, `loan_file.missing_documents[]`, `loan_file.fraud_flags[]`.

## Checklist
- [ ] Validation agent: cross-check fields across documents (declared income vs. bank deposits, name/address consistency, expiry dates)
- [ ] Emit a `validation_findings` entry per check, with `severity` (`info` / `warning` / `critical`)
- [ ] Missing-document agent: check against a checklist keyed by `loan_type` + `loan_amount_requested`, populate `missing_documents[]`
- [ ] Draft the "please provide X" message for each missing doc (`request_message`)
- [ ] Fraud agent: flag tampering signals and duplicate/reused documents across applications
- [ ] Emit `fraud_flags[]` with `severity` and supporting `evidence`
- [ ] Write an entry to `audit_log` for each check that runs

## Test against
`/schema/loan_file.example.json` with `/ingestion`'s fraud-injection toggle turned on — confirm your fraud agent actually catches the tampered doc.
