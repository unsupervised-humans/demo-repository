"""Tests for synthetic_generator.py."""

import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", ".."))

from ingestion.synthetic_generator import SyntheticDocumentGenerator


class TestSyntheticDocumentGenerator:
    def test_generates_all_normal_types(self):
        gen = SyntheticDocumentGenerator()
        docs = gen.generate_normal_set()

        types = {d.document_type for d in docs}
        assert types == {
            "payslip",
            "bank_statement",
            "identity_document",
            "tax_return",
            "address_proof",
        }
        assert all(d.category == "normal" for d in docs)

    def test_generates_all_fraud_types(self):
        gen = SyntheticDocumentGenerator()
        docs = gen.generate_fraud_set()

        names = {d.name for d in docs}
        assert names == {
            "mismatched_name_payslip",
            "tampered_income_payslip",
            "tampered_date_payslip",
            "duplicate_payslip",
            "modified_balance_bank",
            "different_name_bank",
        }
        assert all(d.category == "fraud" for d in docs)

    def test_all_documents_are_valid_pdf_bytes(self):
        gen = SyntheticDocumentGenerator()
        docs = gen.generate_all()

        for d in docs:
            assert d.file_bytes.startswith(b"%PDF-"), f"{d.name} is not a valid PDF"
            assert b"%%EOF" in d.file_bytes, f"{d.name} missing PDF EOF marker"

    def test_duplicate_payslip_matches_normal_payslip_bytes(self):
        gen = SyntheticDocumentGenerator()
        normal = gen.normal_payslip()
        duplicate = gen.duplicate_payslip()

        assert duplicate.file_bytes == normal.file_bytes
        assert duplicate.file_name != normal.file_name

    def test_write_to_disk(self, tmp_path):
        gen = SyntheticDocumentGenerator(output_dir=str(tmp_path))
        docs = gen.generate_all()

        for d in docs:
            written_path = tmp_path / d.file_name
            assert written_path.exists()
            assert written_path.read_bytes() == d.file_bytes
