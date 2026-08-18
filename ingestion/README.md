# Ingestion — Harris

Owner: **Harris**
Boundary: `Files -> documents[]`. Does **not** implement `extracted_fields[]`,
validation findings, fraud decisions, or risk scoring — that's Austin's side.

## Pipeline

```
file -> validate -> generate doc_id -> normalize -> classify -> documents[]
```

| Stage | Module | Uses LLM? |
|---|---|---|
| Normalization | `normalizer.py` | No |
| Classification | `classifier.py` | Yes — shared Grok client (`shared/llm_client.py`) |
| Orchestration | `document_ingestion.py` | — |
| Test data | `synthetic_generator.py` | No |

## Usage

```python
from ingestion.document_ingestion import IngestionPipeline

pipeline = IngestionPipeline()
documents = pipeline.ingest_folder("path/to/uploaded/files")
loan_file_fragment = pipeline.to_loan_file_documents(documents)
# -> {"documents": [ {doc_id, file_name, document_type, mime_type, page_count, confidence, status}, ... ]}
```

Requires `XAI_API_KEY` in the environment (see `shared/llm_client.py`).
Never commit `.env` or hard-code the key.

## Generating synthetic test documents

```bash
python -m ingestion.synthetic_generator
```

Writes normal + fraud/tampered sample PDFs to `ingestion/samples/`. These
are also generated in-memory by the test suite (see `tests/test_synthetic_docs.py`)
so tests don't depend on files being present on disk.

## Running tests

```bash
pip install -r requirements.txt  # pytest, reportlab, pypdf, requests
pytest ingestion/tests/ -v
```

## Supported document types

`payslip`, `bank_statement`, `tax_return`, `identity_document`,
`address_proof`, `employment_proof`, `unknown`

## Notes / open items

- Page counting for PDFs prefers `pypdf`; falls back to a rough byte-scan
  if `pypdf` isn't installed. Recommend adding `pypdf` as a hard dependency.
- `LOW_CONFIDENCE_THRESHOLD` in `classifier.py` (default `0.55`) is a
  starting guess — tune once real classification data is available.
- Schema validation (`shared/schema_loader.py`) is a minimal placeholder.
  If the repo already has a schema loader, use that instead of this one.
- Do not add new fields to `LoanDocument` / `to_schema_dict()` without
  syncing with Austin and `/schema/loan_file.schema.json`.
