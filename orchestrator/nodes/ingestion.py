"""Ingestion node — adapter for Harris's IngestionPipeline.

Harris's ``LoanDocument.to_schema_dict()`` uses field names that differ
slightly from the schema (``file_name`` vs ``file_path``, ``document_type``
vs ``type``, ``confidence`` vs ``classification_confidence``).  This adapter
bridges the gap without modifying Harris's code.

File Path Fix
-------------
The ``file_path`` field in the adapted document must be the **full absolute
disk path** to the uploaded file — not just the filename.  The extraction
node uses ``file_path`` to read the file bytes for OCR and LLM extraction.
When ``run_from_files()`` saves uploads to a temp folder, Harris's
``ingest_folder()`` already stores the full path in ``LoanDocument.file_path``
(via ``to_schema_dict()``), so this adapter must not overwrite it with the
bare filename.
"""

from __future__ import annotations

import logging
from typing import Any

from orchestrator.audit import append_audit
from orchestrator.error_handling import NoCriticalDataError

logger = logging.getLogger(__name__)


def _adapt_document(doc: dict[str, Any]) -> dict[str, Any]:
    """Map Harris's to_schema_dict() output → loan_file.schema.json shape.

    Harris outputs (via the updated to_schema_dict()):
        doc_id, file_name, file_path, document_type, type, mime_type,
        page_count, confidence, classification_confidence, status,
        detected_sections (optional)

    Schema expects:
        doc_id, file_path, type, classification_confidence, page_count, is_synthetic

    Priority for file_path:
        1. ``file_path`` (full absolute path from Harris's pipeline)
        2. ``file_name`` (bare name, only as last resort — extraction will fail)
    """
    # Use the full file_path if present, otherwise fall back to file_name
    file_path = doc.get("file_path") or doc.get("file_name", "")

    adapted: dict[str, Any] = {
        "doc_id": doc.get("doc_id", "unknown"),
        "file_path": file_path,
        "file_name": doc.get("file_name", ""),
        "type": doc.get("type") or doc.get("document_type", "other"),
        "document_type": doc.get("document_type") or doc.get("type", "other"),
        "classification_confidence": (
            doc.get("classification_confidence") or doc.get("confidence", 0.0)
        ),
        "page_count": doc.get("page_count", 1),
        "is_synthetic": doc.get("is_synthetic", False),
    }
    # Preserve detected_sections for combined_loan_package documents
    if doc.get("detected_sections"):
        adapted["detected_sections"] = doc["detected_sections"]
    return adapted


def run_ingestion_from_folder(
    loan_file: dict[str, Any],
    folder_path: str,
) -> dict[str, Any]:
    """Ingest documents from *folder_path* using Harris's pipeline.

    Parameters
    ----------
    loan_file : dict
        The shared loan_file state (will be mutated).
    folder_path : str
        Path to the folder containing raw applicant documents.

    Returns
    -------
    dict
        Updated loan_file with ``documents[]`` populated.

    Raises
    ------
    NoCriticalDataError
        If zero valid documents are produced.
    """
    from ingestion.document_ingestion import IngestionPipeline

    append_audit(loan_file, "ingestion started", agent="classifier")

    pipeline = IngestionPipeline()
    raw_docs = pipeline.ingest_folder(folder_path)

    if not raw_docs:
        append_audit(loan_file, "ingestion produced zero documents", agent="classifier")
        raise NoCriticalDataError(
            "No documents found in the upload folder.",
            stage="ingestion",
        )

    # Convert Harris's dataclass output to schema-compliant dicts.
    schema_docs = []
    for doc in raw_docs:
        raw_dict = doc.to_schema_dict()
        schema_docs.append(_adapt_document(raw_dict))

    loan_file["documents"] = schema_docs
    append_audit(
        loan_file,
        f"classified {len(schema_docs)} documents",
        agent="classifier",
    )

    return loan_file


def run_ingestion_passthrough(
    loan_file: dict[str, Any],
) -> dict[str, Any]:
    """Validate that pre-ingested documents exist in *loan_file*.

    Used when documents are already present (e.g. from the example fixture
    or an upstream system).

    Raises
    ------
    NoCriticalDataError
        If ``loan_file['documents']`` is empty.
    """
    documents = loan_file.get("documents") or []

    if not documents:
        append_audit(loan_file, "no documents present — pipeline cannot proceed")
        raise NoCriticalDataError(
            "loan_file has no documents — nothing to process.",
            stage="ingestion",
        )

    # Ensure each doc has the schema-required fields.
    adapted = [_adapt_document(d) for d in documents]
    loan_file["documents"] = adapted

    append_audit(
        loan_file,
        f"passthrough ingestion: {len(adapted)} documents verified",
        agent="classifier",
    )
    return loan_file
