"""
Data models for Harris's ingestion pipeline.

Harris owns: Files -> documents[]
Austin owns: documents[] -> extracted_fields[]

Keep this model aligned with /schema/loan_file.schema.json. Do not add
new fields here without discussing with the integration owner (Austin).
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass, field
from enum import Enum
from typing import List, Optional


class DocumentType(str, Enum):
    PAYSLIP = "payslip"
    BANK_STATEMENT = "bank_statement"
    TAX_RETURN = "tax_return"
    IDENTITY_DOCUMENT = "identity_document"
    ADDRESS_PROOF = "address_proof"
    EMPLOYMENT_PROOF = "employment_proof"
    APPLICATION_FORM = "application_form"
    # A single uploaded file that contains multiple logical sections
    # (e.g. applicant form + payslip + bank statement + KYC all in one PDF)
    COMBINED_LOAN_PACKAGE = "combined_loan_package"
    UNKNOWN = "unknown"


class IngestionStatus(str, Enum):
    OK = "ok"
    CORRUPTED = "corrupted"
    UNSUPPORTED_FORMAT = "unsupported_format"
    TOO_LARGE = "too_large"
    EMPTY = "empty"


def generate_doc_id() -> str:
    """Generate a unique doc_id, e.g. DOC-3F9A1C2B."""
    return f"DOC-{uuid.uuid4().hex[:8].upper()}"


@dataclass
class RawFile:
    """A file as it arrives from the applicant upload step, before
    any validation or normalization has happened."""

    file_name: str
    file_bytes: bytes
    mime_type: Optional[str] = None  # may be unknown until validated
    # Full absolute path on disk — populated when ingesting from folder
    file_path: Optional[str] = None


@dataclass
class NormalizedDocument:
    """Output of the Normalizer. No LLM involved at this stage."""

    doc_id: str
    file_name: str
    mime_type: str
    page_count: int
    file_size_bytes: int
    status: IngestionStatus
    # Local/temp path or in-memory handle used internally by later
    # pipeline stages (classification). Not part of the public schema
    # output handed to Austin.
    content_ref: Optional[bytes] = None
    error: Optional[str] = None
    # Full absolute path to the file on disk (if available)
    file_path: Optional[str] = None


@dataclass
class ClassificationResult:
    """Output of the Document Classification Agent (Grok multimodal)."""

    document_type: DocumentType
    confidence: float
    low_confidence: bool = field(default=False)
    # For combined_loan_package: list of detected section types inside the file
    detected_sections: List[str] = field(default_factory=list)


@dataclass
class LoanDocument:
    """
    Final record appended to loan_file.documents[].

    This is the contract handed to Austin. Fields here must match
    /schema/loan_file.schema.json. Do NOT add extracted financial
    fields (gross_monthly_income, account_balance, employer_name,
    etc.) here -- those belong to Austin's extracted_fields[].
    """

    doc_id: str
    file_name: str
    document_type: DocumentType
    mime_type: str
    page_count: int
    confidence: float
    status: IngestionStatus = IngestionStatus.OK
    error: Optional[str] = None
    # Full absolute path on disk — used by the extraction node to read file content
    file_path: Optional[str] = None
    # For combined_loan_package: which section types were detected inside
    detected_sections: List[str] = field(default_factory=list)

    def to_schema_dict(self) -> dict:
        """Serialize to the shared loan_file.documents[] shape."""
        payload = {
            "doc_id": self.doc_id,
            "file_name": self.file_name,
            "file_path": self.file_path or self.file_name,
            "document_type": self.document_type.value,
            "type": self.document_type.value,  # alias used by extraction node
            "mime_type": self.mime_type,
            "page_count": self.page_count,
            "confidence": self.confidence,
            "classification_confidence": self.confidence,
            "status": self.status.value,
        }
        if self.error:
            payload["error"] = self.error
        if self.detected_sections:
            payload["detected_sections"] = self.detected_sections
        return payload
