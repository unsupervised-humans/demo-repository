"""
Top-level ingestion pipeline.

    file -> validate -> generate doc_id -> normalize -> classify -> documents[]

This is Harris's public entry point. Austin (or the orchestrator) calls
`ingest_batch()` with a folder or list of raw files and gets back a
schema-compatible loan_file.documents[] list.
"""

from __future__ import annotations

import logging
import os
from typing import Iterable

from .classifier import DocumentClassifier
from .models.document import DocumentType, IngestionStatus, LoanDocument, RawFile
from .normalizer import Normalizer

logger = logging.getLogger(__name__)


class IngestionPipeline:
    def __init__(
        self,
        normalizer: Normalizer | None = None,
        classifier: DocumentClassifier | None = None,
    ) -> None:
        self.normalizer = normalizer or Normalizer()
        self.classifier = classifier or DocumentClassifier()

    def ingest_one(self, raw: RawFile) -> LoanDocument:
        """Run a single file through validate -> normalize -> classify."""
        normalized = self.normalizer.normalize(raw)

        if normalized.status != IngestionStatus.OK:
            # Corrupted/unsupported/too-large/empty files still produce a
            # documents[] entry, so Austin knows this doc_id exists and
            # why it has no usable content, rather than silently vanishing.
            return LoanDocument(
                doc_id=normalized.doc_id,
                file_name=normalized.file_name,
                document_type=DocumentType.UNKNOWN,
                mime_type=normalized.mime_type,
                page_count=normalized.page_count,
                confidence=0.0,
                status=normalized.status,
                error=normalized.error,
            )

        classification = self.classifier.classify(normalized)

        return LoanDocument(
            doc_id=normalized.doc_id,
            file_name=normalized.file_name,
            document_type=classification.document_type,
            mime_type=normalized.mime_type,
            page_count=normalized.page_count,
            confidence=classification.confidence,
            status=IngestionStatus.OK,
        )

    def ingest_batch(self, raw_files: Iterable[RawFile]) -> list[LoanDocument]:
        """Ingest multiple files, isolating failures per-file."""
        results: list[LoanDocument] = []
        for raw in raw_files:
            try:
                results.append(self.ingest_one(raw))
            except Exception as exc:  # noqa: BLE001
                # A single bad file must never take down the whole batch.
                logger.exception("Unexpected failure ingesting %s", raw.file_name)
                results.append(
                    LoanDocument(
                        doc_id="DOC-ERROR",
                        file_name=raw.file_name,
                        document_type=DocumentType.UNKNOWN,
                        mime_type=raw.mime_type or "application/octet-stream",
                        page_count=0,
                        confidence=0.0,
                        status=IngestionStatus.CORRUPTED,
                        error=str(exc),
                    )
                )
        return results

    def ingest_folder(self, folder_path: str) -> list[LoanDocument]:
        """Convenience: ingest every file in a folder."""
        raw_files = []
        for name in sorted(os.listdir(folder_path)):
            full_path = os.path.join(folder_path, name)
            if not os.path.isfile(full_path):
                continue
            with open(full_path, "rb") as f:
                raw_files.append(RawFile(file_name=name, file_bytes=f.read()))
        return self.ingest_batch(raw_files)

    def to_loan_file_documents(self, documents: list[LoanDocument]) -> dict:
        """Wrap results in the loan_file.documents[] schema shape."""
        return {"documents": [d.to_schema_dict() for d in documents]}
