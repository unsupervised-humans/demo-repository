"""extraction/tests/test_schema_validation.py
Schema validation tests for Austin's extraction output.

Tests:
1. The existing loan_file.example.json validates against loan_file.schema.json
   (regression — if the example breaks, something else changed).
2. A synthetic loan_file with extraction output validates successfully.
3. A loan_file with a bad extractedField fails validation (negative test).
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

try:
    import jsonschema
    HAS_JSONSCHEMA = True
except ImportError:
    HAS_JSONSCHEMA = False

pytestmark = pytest.mark.skipif(
    not HAS_JSONSCHEMA, reason="jsonschema not installed"
)

REPO_ROOT = Path(__file__).resolve().parent.parent.parent
SCHEMA_PATH = REPO_ROOT / "schema" / "loan_file.schema.json"
EXAMPLE_PATH = REPO_ROOT / "schema" / "loan_file.example.json"


def _load_schema() -> dict:
    with open(SCHEMA_PATH, encoding="utf-8") as f:
        return json.load(f)


def _validate(instance: dict) -> None:
    schema = _load_schema()
    jsonschema.validate(instance=instance, schema=schema)


# ── Test 1: existing example passes ──────────────────────────────────────────

def test_example_json_validates():
    """loan_file.example.json must always validate against the schema."""
    with open(EXAMPLE_PATH, encoding="utf-8") as f:
        example = json.load(f)
    _validate(example)  # raises jsonschema.ValidationError on failure


# ── Test 2: synthetic extraction output validates ─────────────────────────────

def test_synthetic_extracted_fields_validate():
    """A loan_file produced by extraction must satisfy the schema."""
    synthetic = {
        "application_id": "APP-SYNTH-001",
        "created_at": "2026-08-17T10:00:00Z",
        "status": "extracting",
        "documents": [
            {
                "doc_id": "doc-01",
                "file_path": "uploads/doc-01.pdf",
                "type": "payslip",
                "classification_confidence": 0.95,
            }
        ],
        "extracted_fields": [
            {
                "field_name": "employer_name",
                "value": "Synthetic Corp",
                "confidence": 0.92,
                "source": {"doc_id": "doc-01", "page": 1, "bbox": [0.1, 0.2, 0.3, 0.04]},
                "needs_review": False,
            },
            {
                "field_name": "gross_monthly_income",
                "value": 72000,
                "confidence": 0.90,
                "source": {"doc_id": "doc-01", "page": 1},
                "needs_review": False,
            },
            {
                "field_name": "id_expiry_date",
                "value": "2029-06-30",
                "confidence": 0.65,
                "source": {"doc_id": "doc-01", "page": 1},
                "needs_review": True,
            },
        ],
        "audit_log": [
            {
                "agent": "extraction",
                "action": "extracted 3 fields from doc-01 (type=payslip)",
                "timestamp": "2026-08-17T10:00:05Z",
            }
        ],
    }
    _validate(synthetic)


# ── Test 3: invalid extractedField fails validation ───────────────────────────

def test_invalid_extracted_field_fails():
    """A field missing required 'source' should fail schema validation."""
    bad = {
        "application_id": "APP-BAD-001",
        "created_at": "2026-08-17T10:00:00Z",
        "status": "extracting",
        "documents": [
            {
                "doc_id": "doc-01",
                "file_path": "uploads/doc-01.pdf",
                "type": "payslip",
                "classification_confidence": 0.95,
            }
        ],
        "extracted_fields": [
            {
                "field_name": "employer_name",
                "value": "Corp",
                "confidence": 0.9,
                # 'source' is MISSING — schema requires it
            }
        ],
        "audit_log": [],
    }
    with pytest.raises(jsonschema.ValidationError):
        _validate(bad)


def test_invalid_confidence_out_of_range_fails():
    """Confidence > 1.0 should fail schema validation."""
    bad = {
        "application_id": "APP-BAD-002",
        "created_at": "2026-08-17T10:00:00Z",
        "status": "extracting",
        "documents": [
            {
                "doc_id": "doc-01",
                "file_path": "uploads/doc-01.pdf",
                "type": "payslip",
                "classification_confidence": 0.95,
            }
        ],
        "extracted_fields": [
            {
                "field_name": "employer_name",
                "value": "Corp",
                "confidence": 1.5,       # out of range
                "source": {"doc_id": "doc-01", "page": 1},
            }
        ],
        "audit_log": [],
    }
    with pytest.raises(jsonschema.ValidationError):
        _validate(bad)


def test_valid_audit_entry_shape():
    """An auditEntry without all required keys must fail."""
    bad = {
        "application_id": "APP-BAD-003",
        "created_at": "2026-08-17T10:00:00Z",
        "status": "extracting",
        "documents": [
            {
                "doc_id": "doc-01",
                "file_path": "uploads/doc-01.pdf",
                "type": "payslip",
                "classification_confidence": 0.95,
            }
        ],
        "audit_log": [
            {
                "agent": "extraction",
                # 'action' and 'timestamp' are missing
            }
        ],
    }
    with pytest.raises(jsonschema.ValidationError):
        _validate(bad)
