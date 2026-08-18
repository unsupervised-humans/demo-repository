"""Tests for classifier.py. The Grok/OpenAI client is mocked -- these tests
never make real network calls."""

import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", ".."))

from unittest.mock import MagicMock

from ingestion.classifier import DocumentClassifier
from ingestion.models.document import DocumentType, IngestionStatus, NormalizedDocument
from shared.llm_client import LLMClientError


def _normalized_doc(content=b"fake-image-bytes") -> NormalizedDocument:
    return NormalizedDocument(
        doc_id="DOC-TEST0001",
        file_name="test.png",
        mime_type="image/png",
        page_count=1,
        file_size_bytes=len(content),
        status=IngestionStatus.OK,
        content_ref=content,
    )


class TestDocumentClassifier:
    def test_classifies_known_type(self):
        mock_client = MagicMock()
        mock_choice = MagicMock()
        mock_choice.message.content = '{"document_type": "payslip", "confidence": 0.96}'
        mock_client.chat.completions.create.return_value.choices = [mock_choice]
        classifier = DocumentClassifier(client=mock_client)

        result = classifier.classify(_normalized_doc())

        assert result.document_type == DocumentType.PAYSLIP
        assert result.confidence == 0.96
        assert result.low_confidence is False

    def test_low_confidence_flagged(self):
        mock_client = MagicMock()
        mock_choice = MagicMock()
        mock_choice.message.content = '{"document_type": "bank_statement", "confidence": 0.3}'
        mock_client.chat.completions.create.return_value.choices = [mock_choice]
        classifier = DocumentClassifier(client=mock_client)

        result = classifier.classify(_normalized_doc())

        assert result.document_type == DocumentType.BANK_STATEMENT
        assert result.low_confidence is True

    def test_unrecognized_type_falls_back_to_unknown(self):
        mock_client = MagicMock()
        mock_choice = MagicMock()
        mock_choice.message.content = '{"document_type": "utility_bill_from_mars", "confidence": 0.8}'
        mock_client.chat.completions.create.return_value.choices = [mock_choice]
        classifier = DocumentClassifier(client=mock_client)

        result = classifier.classify(_normalized_doc())

        assert result.document_type == DocumentType.UNKNOWN

    def test_llm_failure_falls_back_gracefully(self):
        mock_client = MagicMock()
        mock_client.chat.completions.create.side_effect = LLMClientError("network error")
        classifier = DocumentClassifier(client=mock_client)

        result = classifier.classify(_normalized_doc())

        assert result.document_type == DocumentType.UNKNOWN
        assert result.confidence == 0.0
        assert result.low_confidence is True

    def test_no_content_returns_unknown_without_calling_llm(self):
        mock_client = MagicMock()
        classifier = DocumentClassifier(client=mock_client)
        doc = _normalized_doc()
        doc.content_ref = None

        result = classifier.classify(doc)

        assert result.document_type == DocumentType.UNKNOWN
        mock_client.chat.completions.create.assert_not_called()

    def test_missing_confidence_defaults_to_zero(self):
        mock_client = MagicMock()
        mock_choice = MagicMock()
        mock_choice.message.content = '{"document_type": "payslip"}'
        mock_client.chat.completions.create.return_value.choices = [mock_choice]
        classifier = DocumentClassifier(client=mock_client)

        result = classifier.classify(_normalized_doc())

        assert result.confidence == 0.0
