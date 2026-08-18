"""Tests for normalizer.py and document_ingestion.py."""

import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", ".."))

from unittest.mock import MagicMock

import pytest

from ingestion.classifier import DocumentClassifier
from ingestion.document_ingestion import IngestionPipeline
from ingestion.models.document import (
    ClassificationResult,
    DocumentType,
    IngestionStatus,
    RawFile,
)
from ingestion.normalizer import Normalizer
from ingestion.synthetic_generator import SyntheticDocumentGenerator


@pytest.fixture(scope="module")
def synthetic_docs():
    return SyntheticDocumentGenerator().generate_all()


class TestNormalizer:
    def test_clean_pdf(self, synthetic_docs):
        norm = Normalizer()
        payslip = next(d for d in synthetic_docs if d.name == "normal_payslip")
        raw = RawFile(file_name=payslip.file_name, file_bytes=payslip.file_bytes)

        result = norm.normalize(raw)

        assert result.status == IngestionStatus.OK
        assert result.mime_type == "application/pdf"
        assert result.page_count == 1
        assert result.doc_id.startswith("DOC-")

    def test_image_file(self):
        # minimal valid PNG header + IEND chunk
        png_bytes = (
            b"\x89PNG\r\n\x1a\n"
            b"\x00\x00\x00\rIHDR\x00\x00\x00\x01\x00\x00\x00\x01\x08\x02\x00\x00\x00\x90wS\xde"
            b"\x00\x00\x00\nIDATx\x9cc\xf8\x0f\x00\x00\x01\x01\x00\x01\xa5\xf6E\xed"
            b"\x00\x00\x00\x00IEND\xaeB`\x82"
        )
        norm = Normalizer()
        raw = RawFile(file_name="scan.png", file_bytes=png_bytes)

        result = norm.normalize(raw)

        assert result.status == IngestionStatus.OK
        assert result.mime_type == "image/png"
        assert result.page_count == 1

    def test_unknown_extension_rejected(self):
        norm = Normalizer()
        raw = RawFile(file_name="notes.docx", file_bytes=b"whatever")

        result = norm.normalize(raw)

        assert result.status == IngestionStatus.UNSUPPORTED_FORMAT

    def test_corrupted_pdf(self):
        norm = Normalizer()
        raw = RawFile(file_name="broken.pdf", file_bytes=b"this is not a real pdf")

        result = norm.normalize(raw)

        assert result.status == IngestionStatus.CORRUPTED
        assert result.error is not None

    def test_empty_file(self):
        norm = Normalizer()
        raw = RawFile(file_name="empty.pdf", file_bytes=b"")

        result = norm.normalize(raw)

        assert result.status == IngestionStatus.EMPTY

    def test_scanned_pdf(self):
        """A 'scanned' PDF has no real text layer -- it's just an image
        embedded on a page. Normalization only cares about file structure
        (valid PDF, page count), not content, so this must pass exactly
        like a text-based PDF."""
        import io

        from PIL import Image, ImageDraw
        from reportlab.lib.pagesizes import letter
        from reportlab.lib.utils import ImageReader
        from reportlab.pdfgen import canvas

        img = Image.new("RGB", (600, 800), color="white")
        draw = ImageDraw.Draw(img)
        draw.rectangle([50, 50, 550, 750], outline="black", width=2)
        img_buf = io.BytesIO()
        img.save(img_buf, format="PNG")
        img_buf.seek(0)

        pdf_buf = io.BytesIO()
        c = canvas.Canvas(pdf_buf, pagesize=letter)
        c.drawImage(ImageReader(img_buf), 50, 50, width=500, height=650)
        c.showPage()
        c.save()
        scanned_pdf_bytes = pdf_buf.getvalue()

        norm = Normalizer()
        raw = RawFile(file_name="scanned_id.pdf", file_bytes=scanned_pdf_bytes)

        result = norm.normalize(raw)

        assert result.status == IngestionStatus.OK
        assert result.mime_type == "application/pdf"
        assert result.page_count == 1

    def test_oversized_file_rejected(self):
        norm = Normalizer(max_file_size_bytes=10)
        raw = RawFile(file_name="big.pdf", file_bytes=b"%PDF-1.4" + b"x" * 100)

        result = norm.normalize(raw)

        assert result.status == IngestionStatus.TOO_LARGE

    def test_doc_ids_are_unique(self, synthetic_docs):
        norm = Normalizer()
        ids = set()
        for d in synthetic_docs:
            raw = RawFile(file_name=d.file_name, file_bytes=d.file_bytes)
            result = norm.normalize(raw)
            ids.add(result.doc_id)
        assert len(ids) == len(synthetic_docs)


class TestIngestionPipeline:
    def _pipeline_with_stub_classifier(self, doc_type=DocumentType.PAYSLIP, confidence=0.9):
        stub_classifier = MagicMock(spec=DocumentClassifier)
        stub_classifier.classify.return_value = ClassificationResult(
            document_type=doc_type, confidence=confidence
        )
        return IngestionPipeline(classifier=stub_classifier)

    def test_ingest_one_happy_path(self, synthetic_docs):
        pipeline = self._pipeline_with_stub_classifier()
        payslip = next(d for d in synthetic_docs if d.name == "normal_payslip")
        raw = RawFile(file_name=payslip.file_name, file_bytes=payslip.file_bytes)

        result = pipeline.ingest_one(raw)

        assert result.status == IngestionStatus.OK
        assert result.document_type == DocumentType.PAYSLIP
        assert result.confidence == 0.9
        assert result.doc_id.startswith("DOC-")

    def test_ingest_one_corrupted_still_produces_record(self):
        pipeline = self._pipeline_with_stub_classifier()
        raw = RawFile(file_name="broken.pdf", file_bytes=b"garbage")

        result = pipeline.ingest_one(raw)

        assert result.status == IngestionStatus.CORRUPTED
        assert result.error is not None
        # classifier should never be called on unusable content
        pipeline.classifier.classify.assert_not_called()

    def test_ingest_batch_isolates_failures(self, synthetic_docs):
        pipeline = self._pipeline_with_stub_classifier()
        good = synthetic_docs[0]
        raws = [
            RawFile(file_name=good.file_name, file_bytes=good.file_bytes),
            RawFile(file_name="bad.pdf", file_bytes=b"not a pdf"),
        ]

        results = pipeline.ingest_batch(raws)

        assert len(results) == 2
        assert results[0].status == IngestionStatus.OK
        assert results[1].status == IngestionStatus.CORRUPTED

    def test_unknown_document_type(self):
        """A document the classifier can't confidently place should still
        produce a valid documents[] entry with type 'unknown', not an
        error or a dropped record."""
        pipeline = self._pipeline_with_stub_classifier(
            doc_type=DocumentType.UNKNOWN, confidence=0.2
        )
        raw = RawFile(file_name="mystery.png", file_bytes=self._minimal_png())

        result = pipeline.ingest_one(raw)

        assert result.status == IngestionStatus.OK
        assert result.document_type == DocumentType.UNKNOWN

    def test_fraud_synthetic_documents_ingest_successfully(self, synthetic_docs):
        """Fraud/tampered documents are structurally valid files -- the
        tampering is in the content (names, numbers, dates), which is
        Alina's validation/fraud layer's job to catch, not ingestion's.
        Ingestion must still classify and pass them through as normal
        documents[] entries."""
        fraud_docs = [d for d in synthetic_docs if d.category == "fraud"]
        assert len(fraud_docs) == 6  # sanity check against the spec's list

        pipeline = self._pipeline_with_stub_classifier(doc_type=DocumentType.PAYSLIP)
        raws = [RawFile(file_name=d.file_name, file_bytes=d.file_bytes) for d in fraud_docs]

        results = pipeline.ingest_batch(raws)

        assert len(results) == len(fraud_docs)
        for result in results:
            assert result.status == IngestionStatus.OK
            assert result.error is None

    def _minimal_png(self) -> bytes:
        return (
            b"\x89PNG\r\n\x1a\n"
            b"\x00\x00\x00\rIHDR\x00\x00\x00\x01\x00\x00\x00\x01\x08\x02\x00\x00\x00\x90wS\xde"
            b"\x00\x00\x00\nIDATx\x9cc\xf8\x0f\x00\x00\x01\x01\x00\x01\xa5\xf6E\xed"
            b"\x00\x00\x00\x00IEND\xaeB`\x82"
        )

    def test_to_loan_file_documents_shape(self, synthetic_docs):
        pipeline = self._pipeline_with_stub_classifier()
        good = synthetic_docs[0]
        raw = RawFile(file_name=good.file_name, file_bytes=good.file_bytes)
        results = pipeline.ingest_batch([raw])

        payload = pipeline.to_loan_file_documents(results)

        assert "documents" in payload
        assert len(payload["documents"]) == 1
        entry = payload["documents"][0]
        assert set(["doc_id", "file_name", "document_type", "mime_type", "page_count"]).issubset(
            entry.keys()
        )
