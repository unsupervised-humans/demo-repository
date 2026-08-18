"""
Synthetic Document Generator.

Produces dummy PDFs for the whole team to test against:
  - normal documents (payslip, bank statement, KYC/ID, tax return, address proof)
  - fraud/tampered documents (name mismatch, income tampering, date tampering,
    duplicate/reused doc, modified balance)

These are later consumed by Alina's validation/fraud detection work, and by
Harris's own classifier tests. No real personal data is used -- all names,
numbers, and addresses below are fabricated placeholders.
"""

from __future__ import annotations

import os
from dataclasses import dataclass
from datetime import date, timedelta
from typing import Optional

from reportlab.lib.pagesizes import letter
from reportlab.pdfgen import canvas


@dataclass
class SyntheticDoc:
    """A generated test document plus metadata about what it's testing."""

    name: str  # e.g. "normal_payslip", "tampered_income_payslip"
    file_name: str
    category: str  # "normal" or "fraud"
    document_type: str
    file_bytes: bytes
    notes: str = ""


class SyntheticDocumentGenerator:
    """Generates normal and fraud/tampered synthetic loan documents."""

    def __init__(self, output_dir: Optional[str] = None) -> None:
        self.output_dir = output_dir

    # --- public API --------------------------------------------------

    def generate_all(self) -> list[SyntheticDoc]:
        docs = []
        docs += self.generate_normal_set()
        docs += self.generate_fraud_set()
        if self.output_dir:
            self._write_all(docs)
        return docs

    def generate_normal_set(self) -> list[SyntheticDoc]:
        return [
            self.normal_payslip(),
            self.normal_bank_statement(),
            self.normal_kyc_id(),
            self.normal_tax_return(),
            self.normal_address_proof(),
        ]

    def generate_fraud_set(self) -> list[SyntheticDoc]:
        return [
            self.mismatched_name_payslip(),
            self.tampered_income_payslip(),
            self.tampered_date_payslip(),
            self.duplicate_payslip(),
            self.modified_balance_bank(),
            self.different_name_bank(),
        ]

    # --- normal documents ---------------------------------------------

    def normal_payslip(self) -> SyntheticDoc:
        lines = [
            "ACME CORP — PAYSLIP",
            "Employee: Jordan Rivera",
            "Employee ID: EMP-10234",
            "Pay Period: 2026-07-01 to 2026-07-31",
            "Gross Pay: $6,200.00",
            "Net Pay: $4,810.00",
            "Employer: Acme Corp",
        ]
        pdf = self._render_pdf(lines)
        return SyntheticDoc(
            name="normal_payslip",
            file_name="normal_payslip.pdf",
            category="normal",
            document_type="payslip",
            file_bytes=pdf,
        )

    def normal_bank_statement(self) -> SyntheticDoc:
        lines = [
            "FIRST NATIONAL BANK — STATEMENT",
            "Account Holder: Jordan Rivera",
            "Account Number: XXXX-XXXX-4471",
            "Statement Period: 2026-07-01 to 2026-07-31",
            "Opening Balance: $2,340.18",
            "Closing Balance: $3,102.55",
        ]
        pdf = self._render_pdf(lines)
        return SyntheticDoc(
            name="normal_bank",
            file_name="normal_bank_statement.pdf",
            category="normal",
            document_type="bank_statement",
            file_bytes=pdf,
        )

    def normal_kyc_id(self) -> SyntheticDoc:
        lines = [
            "STATE IDENTIFICATION CARD",
            "Name: Jordan Rivera",
            "DOB: 1990-04-12",
            "ID Number: ID-88213456",
            "Issued: 2022-03-01",
            "Expires: 2030-03-01",
        ]
        pdf = self._render_pdf(lines)
        return SyntheticDoc(
            name="normal_kyc",
            file_name="normal_identity_document.pdf",
            category="normal",
            document_type="identity_document",
            file_bytes=pdf,
        )

    def normal_tax_return(self) -> SyntheticDoc:
        lines = [
            "FORM 1040 — INDIVIDUAL TAX RETURN (SAMPLE)",
            "Name: Jordan Rivera",
            "Tax Year: 2025",
            "Total Income: $74,400.00",
            "Total Tax Paid: $11,200.00",
        ]
        pdf = self._render_pdf(lines)
        return SyntheticDoc(
            name="normal_tax_return",
            file_name="normal_tax_return.pdf",
            category="normal",
            document_type="tax_return",
            file_bytes=pdf,
        )

    def normal_address_proof(self) -> SyntheticDoc:
        lines = [
            "METRO UTILITIES — ACCOUNT STATEMENT",
            "Name: Jordan Rivera",
            "Service Address: 482 Willow Creek Rd, Springfield",
            "Billing Date: 2026-07-15",
            "Amount Due: $88.42",
        ]
        pdf = self._render_pdf(lines)
        return SyntheticDoc(
            name="normal_address_proof",
            file_name="normal_address_proof.pdf",
            category="normal",
            document_type="address_proof",
            file_bytes=pdf,
        )

    # --- fraud / tampered documents -------------------------------

    def mismatched_name_payslip(self) -> SyntheticDoc:
        lines = [
            "ACME CORP — PAYSLIP",
            "Employee: Alex Chen",  # doesn't match applicant name elsewhere
            "Employee ID: EMP-10234",
            "Pay Period: 2026-07-01 to 2026-07-31",
            "Gross Pay: $6,200.00",
            "Net Pay: $4,810.00",
        ]
        pdf = self._render_pdf(lines)
        return SyntheticDoc(
            name="mismatched_name_payslip",
            file_name="fraud_mismatched_name_payslip.pdf",
            category="fraud",
            document_type="payslip",
            file_bytes=pdf,
            notes="Employee name does not match applicant identity on file.",
        )

    def tampered_income_payslip(self) -> SyntheticDoc:
        lines = [
            "ACME CORP — PAYSLIP",
            "Employee: Jordan Rivera",
            "Employee ID: EMP-10234",
            "Pay Period: 2026-07-01 to 2026-07-31",
            "Gross Pay: $16,200.00",  # inflated vs normal ($6,200)
            "Net Pay: $12,810.00",
        ]
        pdf = self._render_pdf(lines)
        return SyntheticDoc(
            name="tampered_income_payslip",
            file_name="fraud_tampered_income_payslip.pdf",
            category="fraud",
            document_type="payslip",
            file_bytes=pdf,
            notes="Income figures inflated relative to baseline synthetic payslip.",
        )

    def tampered_date_payslip(self) -> SyntheticDoc:
        future_date = (date.today() + timedelta(days=400)).isoformat()
        lines = [
            "ACME CORP — PAYSLIP",
            "Employee: Jordan Rivera",
            "Employee ID: EMP-10234",
            f"Pay Period: 2026-07-01 to {future_date}",  # implausible date
            "Gross Pay: $6,200.00",
            "Net Pay: $4,810.00",
        ]
        pdf = self._render_pdf(lines)
        return SyntheticDoc(
            name="tampered_date_payslip",
            file_name="fraud_tampered_date_payslip.pdf",
            category="fraud",
            document_type="payslip",
            file_bytes=pdf,
            notes="Pay period end date is implausible/future-dated.",
        )

    def duplicate_payslip(self) -> SyntheticDoc:
        """Byte-identical to normal_payslip -- tests reused/duplicate-doc
        detection, which compares content hashes across a loan file or
        across applicants."""
        original = self.normal_payslip()
        return SyntheticDoc(
            name="duplicate_payslip",
            file_name="fraud_duplicate_payslip.pdf",
            category="fraud",
            document_type="payslip",
            file_bytes=original.file_bytes,
            notes="Identical bytes to normal_payslip; tests duplicate/reuse detection.",
        )

    def modified_balance_bank(self) -> SyntheticDoc:
        lines = [
            "FIRST NATIONAL BANK — STATEMENT",
            "Account Holder: Jordan Rivera",
            "Account Number: XXXX-XXXX-4471",
            "Statement Period: 2026-07-01 to 2026-07-31",
            "Opening Balance: $2,340.18",
            "Closing Balance: $31,102.55",  # implausible jump
        ]
        pdf = self._render_pdf(lines)
        return SyntheticDoc(
            name="modified_balance_bank",
            file_name="fraud_modified_balance_bank.pdf",
            category="fraud",
            document_type="bank_statement",
            file_bytes=pdf,
            notes="Closing balance inconsistent with opening balance/transaction history.",
        )

    def different_name_bank(self) -> SyntheticDoc:
        lines = [
            "FIRST NATIONAL BANK — STATEMENT",
            "Account Holder: Morgan Lee",  # doesn't match applicant
            "Account Number: XXXX-XXXX-9902",
            "Statement Period: 2026-07-01 to 2026-07-31",
            "Opening Balance: $500.00",
            "Closing Balance: $612.30",
        ]
        pdf = self._render_pdf(lines)
        return SyntheticDoc(
            name="different_name_bank",
            file_name="fraud_different_name_bank.pdf",
            category="fraud",
            document_type="bank_statement",
            file_bytes=pdf,
            notes="Account holder name does not match applicant identity on file.",
        )

    # --- rendering helpers ------------------------------------------

    def _render_pdf(self, lines: list[str]) -> bytes:
        """Render a simple single-page PDF with one line of text per row."""
        import io

        buf = io.BytesIO()
        c = canvas.Canvas(buf, pagesize=letter)
        width, height = letter

        y = height - 72
        c.setFont("Helvetica-Bold", 14)
        c.drawString(72, y, lines[0])
        y -= 28

        c.setFont("Helvetica", 11)
        for line in lines[1:]:
            c.drawString(72, y, line)
            y -= 20

        c.showPage()
        c.save()
        return buf.getvalue()

    def _write_all(self, docs: list[SyntheticDoc]) -> None:
        os.makedirs(self.output_dir, exist_ok=True)
        for doc in docs:
            path = os.path.join(self.output_dir, doc.file_name)
            with open(path, "wb") as f:
                f.write(doc.file_bytes)


if __name__ == "__main__":
    # Quick manual run: generate all synthetic docs into ingestion/samples/
    out_dir = os.path.join(os.path.dirname(__file__), "samples")
    gen = SyntheticDocumentGenerator(output_dir=out_dir)
    generated = gen.generate_all()
    print(f"Generated {len(generated)} synthetic documents in {out_dir}")
    for d in generated:
        print(f"  [{d.category}] {d.file_name} -> {d.document_type}")
