"""
Document Classification Agent.

Uses the shared Grok multimodal API client to determine document type
for a normalized document. This is Harris's only LLM-touching component.

Does NOT extract financial fields -- classification only.
"""

from __future__ import annotations

import logging
from typing import Optional

from shared.llm_client import GrokClient, LLMClientError, get_default_client
from shared.prompts import DOCUMENT_CLASSIFICATION_PROMPT

from .models.document import ClassificationResult, DocumentType, NormalizedDocument

logger = logging.getLogger(__name__)

LOW_CONFIDENCE_THRESHOLD = 0.55

VALID_TYPES = {t.value for t in DocumentType}


class DocumentClassifier:
    """Classifies a normalized document into one of the supported types."""

    def __init__(
        self,
        client: Optional[GrokClient] = None,
        low_confidence_threshold: float = LOW_CONFIDENCE_THRESHOLD,
    ) -> None:
        self._client = client
        self.low_confidence_threshold = low_confidence_threshold

    @property
    def client(self) -> GrokClient:
        # Lazily resolve so unit tests can construct a DocumentClassifier
        # without XAI_API_KEY being set, as long as they inject a client.
        if self._client is None:
            self._client = get_default_client()
        return self._client

    def classify(self, doc: NormalizedDocument) -> ClassificationResult:
        """Classify a single normalized document.

        Falls back to `unknown` with confidence 0.0 if the LLM call fails,
        rather than raising -- a classification failure should not crash
        the ingestion pipeline for the rest of the batch.
        """
        if doc.content_ref is None:
            logger.warning("No content to classify for %s", doc.doc_id)
            return ClassificationResult(
                document_type=DocumentType.UNKNOWN, confidence=0.0, low_confidence=True
            )

        try:
            result = self.client.classify_document(
                image_bytes=doc.content_ref,
                mime_type=doc.mime_type,
                prompt=DOCUMENT_CLASSIFICATION_PROMPT,
            )
        except LLMClientError as exc:
            logger.error("Classification failed for %s: %s", doc.doc_id, exc)
            return ClassificationResult(
                document_type=DocumentType.UNKNOWN, confidence=0.0, low_confidence=True
            )

        return self._parse_result(result)

    def _parse_result(self, result: dict) -> ClassificationResult:
        raw_type = result.get("document_type", "unknown")
        confidence = result.get("confidence", 0.0)

        try:
            confidence = float(confidence)
        except (TypeError, ValueError):
            confidence = 0.0

        if raw_type not in VALID_TYPES:
            logger.warning("Grok returned unrecognized document_type: %r", raw_type)
            raw_type = DocumentType.UNKNOWN.value
            confidence = min(confidence, 0.0)

        doc_type = DocumentType(raw_type)
        low_confidence = confidence < self.low_confidence_threshold

        if low_confidence and doc_type != DocumentType.UNKNOWN:
            logger.info(
                "Low-confidence classification (%.2f) for type %s", confidence, doc_type
            )

        return ClassificationResult(
            document_type=doc_type,
            confidence=confidence,
            low_confidence=low_confidence,
        )
