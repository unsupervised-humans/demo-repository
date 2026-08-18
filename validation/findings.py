"""Finding, fraud-flag, and missing-document models.

Serialized field names match `$defs.validationFinding`, `$defs.fraudFlag`, and
`$defs.missingDocument` in `/schema/loan_file.schema.json`. Extra explainability
fields (finding_type, sources, status, flag_type) are allowed by the schema
because `additionalProperties` is not set to false.

Internal `Severity` uses LOW/MEDIUM/HIGH/CRITICAL. Schema dump maps:
- findings → info / warning / critical
- fraud flags → low / medium / high  (CRITICAL is capped to high; schema has no critical)
"""

from __future__ import annotations

from enum import Enum
from typing import Any
from uuid import uuid4

from pydantic import BaseModel, ConfigDict, Field


class Severity(str, Enum):
    """Canonical detector severity. Never declare an applicant fraudulent from this alone."""

    LOW = "LOW"
    MEDIUM = "MEDIUM"
    HIGH = "HIGH"
    CRITICAL = "CRITICAL"


FINDING_SEVERITY_TO_SCHEMA: dict[Severity, str] = {
    Severity.LOW: "info",
    Severity.MEDIUM: "warning",
    Severity.HIGH: "critical",
    Severity.CRITICAL: "critical",
}

FRAUD_SEVERITY_TO_SCHEMA: dict[Severity, str] = {
    Severity.LOW: "low",
    Severity.MEDIUM: "medium",
    Severity.HIGH: "high",
    Severity.CRITICAL: "high",
}

_POTENTIAL_FRAUD_PHRASE = "potential fraud indicator"
_WEAK_SIGNAL_CAP = Severity.MEDIUM


class SourceRef(BaseModel):
    """Austin's source citation. Never fabricate doc_id or page."""

    model_config = ConfigDict(extra="allow")

    doc_id: str
    page: int
    bbox: list[float] | None = None


class ExtractedField(BaseModel):
    """Shape of `loan_file.extracted_fields[]` produced by Austin's extraction module."""

    model_config = ConfigDict(extra="allow")

    field_name: str
    value: Any = None
    confidence: float = 1.0
    source: SourceRef
    needs_review: bool = False


class Finding(BaseModel):
    """Cross-document validation finding. `status` must never contain the word 'fraud'."""

    model_config = ConfigDict(extra="allow")

    finding_id: str
    finding_type: str
    severity: Severity
    message: str
    fields_compared: list[str] = Field(default_factory=list)
    sources: list[SourceRef] = Field(default_factory=list)
    status: str = "mismatch"
    values: dict[str, Any] = Field(default_factory=dict)

    def to_schema_dict(self) -> dict[str, Any]:
        doc_ids: list[str] = []
        for src in self.sources:
            if src.doc_id not in doc_ids:
                doc_ids.append(src.doc_id)
        return {
            "finding_id": self.finding_id,
            "severity": FINDING_SEVERITY_TO_SCHEMA[self.severity],
            "description": self.message,
            "related_fields": list(self.fields_compared),
            "doc_ids": doc_ids,
            "finding_type": self.finding_type,
            "fields_compared": list(self.fields_compared),
            "sources": [s.model_dump(exclude_none=True) for s in self.sources],
            "status": self.status,
        }


class FraudFlag(BaseModel):
    """Potential fraud indicator. Instantiate only via `make_fraud_flag()`."""

    model_config = ConfigDict(extra="allow")

    flag_id: str
    flag_type: str
    severity: Severity
    description: str
    evidence: str
    doc_ids: list[str] = Field(default_factory=list)
    weak_signal: bool = False

    def to_schema_dict(self) -> dict[str, Any]:
        return {
            "flag_id": self.flag_id,
            "severity": FRAUD_SEVERITY_TO_SCHEMA[self.severity],
            "description": self.description,
            "evidence": self.evidence,
            "doc_ids": list(self.doc_ids),
            "flag_type": self.flag_type,
        }


class MissingDocumentFinding(BaseModel):
    """One required document that is not present on the application."""

    model_config = ConfigDict(extra="allow")

    document_type: str
    reason: str
    request_drafted: bool = True
    request_message: str
    status: str = "missing"

    @property
    def required_document_type(self) -> str:
        return self.document_type

    @property
    def draft_message(self) -> str:
        return self.request_message

    def to_schema_dict(self) -> dict[str, Any]:
        return {
            "document_type": self.document_type,
            "reason": self.reason,
            "request_drafted": self.request_drafted,
            "request_message": self.request_message,
            "status": self.status,
        }


def _new_id(prefix: str) -> str:
    return f"{prefix}-{uuid4().hex[:8]}"


def make_finding(
    *,
    finding_type: str,
    severity: Severity,
    message: str,
    fields_compared: list[str],
    sources: list[SourceRef],
    status: str,
    values: dict[str, Any] | None = None,
) -> Finding:
    """Build a validation finding. Status must not use the word 'fraud'."""
    if "fraud" in status.lower():
        raise ValueError("Finding.status must not contain 'fraud'; use 'potential_fraud_indicator' only on FraudFlag")
    return Finding(
        finding_id=_new_id("vf"),
        finding_type=finding_type,
        severity=severity,
        message=message,
        fields_compared=list(fields_compared),
        sources=list(sources),
        status=status,
        values=values or {},
    )


def make_fraud_flag(
    *,
    flag_type: str,
    severity: Severity,
    evidence: str,
    doc_ids: list[str],
    detail: str,
    weak_signal: bool = False,
) -> FraudFlag:
    """Sole constructor for fraud flags. Always frames the result as a potential indicator."""
    if weak_signal and severity in {Severity.CRITICAL, Severity.HIGH}:
        severity = _WEAK_SIGNAL_CAP
    if severity is Severity.CRITICAL and weak_signal:
        severity = _WEAK_SIGNAL_CAP

    description = (
        f"{_POTENTIAL_FRAUD_PHRASE} ({severity.value}): {detail}"
    )
    return FraudFlag(
        flag_id=_new_id("ff"),
        flag_type=flag_type,
        severity=severity,
        description=description,
        evidence=evidence,
        doc_ids=list(dict.fromkeys(doc_ids)),
        weak_signal=weak_signal,
    )


def coerce_extracted_fields(raw: list[ExtractedField | dict[str, Any]]) -> list[ExtractedField]:
    """Accept Austin's dicts or already-built models. Skip entries with no usable source."""
    out: list[ExtractedField] = []
    for item in raw:
        if isinstance(item, ExtractedField):
            out.append(item)
            continue
        if not isinstance(item, dict):
            continue
        source = item.get("source")
        if not isinstance(source, dict) or "doc_id" not in source or "page" not in source:
            continue
        try:
            out.append(ExtractedField.model_validate(item))
        except Exception:
            continue
    return out
