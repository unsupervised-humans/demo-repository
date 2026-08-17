# ingestion — Person 1

Owns: document classifier agent, synthetic document generator.

Writes to `loan_file.documents[]`. See `/schema/loan_file.schema.json` for the exact shape.

## Checklist
- [ ] Accept uploaded PDFs/images, normalize to a common format
- [ ] Classifier agent: tag each file as `payslip` / `bank_statement` / `tax_return` / `kyc_id` / `other`, with a `classification_confidence`
- [ ] Handle mixed, unordered, unlabeled batches — don't assume the user sorts anything
- [ ] Synthetic document generator: produce realistic dummy payslips, bank statements, tax returns
- [ ] Add a fraud-injection toggle to the generator (mismatched names, altered numbers) for testing `/validation`
- [ ] Populate `is_synthetic: true` on generated docs
- [ ] Write a startup entry to `audit_log` when classification runs

## Test against
`/schema/loan_file.example.json` — your output should match the shape of its `documents[]` array.
