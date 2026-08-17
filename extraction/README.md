# extraction — Person 2

Owns: field extraction agent (multimodal OCR + LLM).

Reads `loan_file.documents[]`, writes `loan_file.extracted_fields[]`.

## Checklist
- [ ] Extract fields per document type (employer_name, gross_monthly_income, account_balance, applicant_name, id_expiry_date, etc.)
- [ ] Attach a `confidence` score (0-1) to every field
- [ ] Attach a `source` (`doc_id`, `page`, and `bbox` if available) to every field — this is the explainability backbone, don't skip it
- [ ] Set `needs_review: true` below your team's agreed confidence threshold (suggest starting at 0.7)
- [ ] Handle scanned/handwritten docs gracefully — fall back rather than fail silently
- [ ] Write an entry to `audit_log` when extraction runs

## Test against
`/schema/loan_file.example.json` — your output should match the shape of its `extracted_fields[]` array. Ask `/ingestion` for sample synthetic docs to test on if theirs isn't ready yet — mock `documents[]` yourself in the meantime.
