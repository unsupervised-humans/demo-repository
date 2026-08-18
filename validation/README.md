# validation — Alina

Owns: cross-document validation, missing-document detection, and fraud/anomaly detection.

Reads Austin's `loan_file.extracted_fields[]` (and Harris's `loan_file.documents[]`).
Writes `loan_file.validation_findings[]`, `loan_file.missing_documents[]`,
`loan_file.fraud_flags[]`, and an `audit_log[]` entry.

## What this module does

- Compare extracted facts across documents (name, income, address, dates, employer).
- Detect required documents that are missing for a given `loan_type`.
- Raise explainable **potential fraud indicators** (never an unqualified accusation).
- Build a NetworkX consistency graph (JSON-serialized for the dashboard).

## What this module does NOT do

| Area | Owner |
|---|---|
| File upload, document classification, synthetic document generator | Harris (`ingestion/`) |
| OCR / field extraction, extraction confidence, bounding boxes | Austin (`extraction/`) |
| XGBoost / SHAP credit-risk model | Rohit (`risk/`) |
| LangGraph orchestration, dashboard UI | Christy (`orchestrator/`) |

Do not put real PDF/image fixtures in `validation/samples/` — Harris owns document files.

## Input contract

- `loan_file.documents[]` — `doc_id`, `file_path`, `type` (`payslip` / `bank_statement` / `tax_return` / `kyc_id` / `other`), optional `sha256`/`file_hash` for reuse checks.
- `loan_file.extracted_fields[]` — Austin's shape:

```json
{
  "field_name": "gross_monthly_income",
  "value": 65000,
  "confidence": 0.96,
  "source": { "doc_id": "doc-01", "page": 1 },
  "needs_review": false
}
```

Name fields used: `applicant_name`, `employee_name`, `account_holder_name`.
Income: `gross_monthly_income` vs `avg_monthly_deposit`.

## Output contract

Must validate against `/schema/loan_file.schema.json`:

- `validation_findings[]` — `finding_id`, `severity` (`info`/`warning`/`critical`), `description`, `related_fields`, `doc_ids`
- `missing_documents[]` — `document_type`, `reason`, `request_drafted`, `request_message`
- `fraud_flags[]` — `flag_id`, `severity` (`low`/`medium`/`high`), `description`, `evidence`, `doc_ids`
- `audit_log[]` — append-only `{agent, action, timestamp}`

Internal detectors use LOW/MEDIUM/HIGH/CRITICAL and map onto those schema enums on dump.
Fraud flags always go through `make_fraud_flag()` and include the phrase "potential fraud indicator".

## How to run tests

```bash
pip install -r requirements.txt
pip install -r validation/requirements.txt
python -m pytest validation/tests -v
```

## Demo

```bash
python -m validation.run_demo
```

## Pipeline entrypoint (for the orchestrator)

```python
from validation import process_loan_file

updated = process_loan_file(loan_file)
```
