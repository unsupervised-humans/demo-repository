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
from typing import Optional


class DocumentType(str, Enum):
    PAYSLIP = "payslip"
    BANK_STATEMENT = "bank_statement"
    TAX_RETURN = "tax_return"
    IDENTITY_DOCUMENT = "identity_document"
    ADDRESS_PROOF = "address_proof"
    EMPLOYMENT_PROOF = "employment_proof"
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


@dataclass
class ClassificationResult:
    """Output of the Document Classification Agent (Grok multimodal)."""

    document_type: DocumentType
    confidence: float
    low_confidence: bool = field(default=False)


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

    def to_schema_dict(self) -> dict:
        """Serialize to the shared loan_file.documents[] shape."""
        payload = {
            "doc_id": self.doc_id,
            "file_name": self.file_name,
            "document_type": self.document_type.value,
            "mime_type": self.mime_type,
            "page_count": self.page_count,
            "confidence": self.confidence,
            "status": self.status.value,
        }
        if self.error:
            payload["error"] = self.error
        return payload
