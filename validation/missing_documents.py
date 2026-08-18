"""Missing-document agent.

Config shape
------------
``required_documents_config`` is a mapping of loan_type → list of document_type
strings. Document types MUST be values from the shared schema enum
(``payslip``, ``bank_statement``, ``tax_return``, ``kyc_id``).

Loan types follow ``applicant.loan_type`` in the schema (``personal``, ``home``,
``auto``, ``education``, ``business``). Aliases such as ``personal_loan`` and
``identity_document`` are accepted and normalized.

Example::

    {
      "personal": ["kyc_id", "payslip", "bank_statement"],
      "home": ["kyc_id", "payslip", "bank_statement", "tax_return"],
      "business": ["kyc_id", "bank_statement", "tax_return"]
    }

Applicant-facing messages come from ``REQUEST_TEMPLATES`` — never ad-hoc
string concatenation at call time.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Iterable, Mapping, Sequence

from validation.findings import MissingDocumentFinding

SCHEMA_DOCUMENT_TYPES = frozenset({"payslip", "bank_statement", "tax_return", "kyc_id", "other"})

DOCUMENT_TYPE_ALIASES: dict[str, str] = {
    "identity_document": "kyc_id",
    "identity": "kyc_id",
    "kyc": "kyc_id",
    "id": "kyc_id",
    "salary_slip": "payslip",
    "pay_slip": "payslip",
    "bank": "bank_statement",
    "itr": "tax_return",
    "tax": "tax_return",
}

LOAN_TYPE_ALIASES: dict[str, str] = {
    "personal_loan": "personal",
    "home_loan": "home",
    "housing_loan": "home",
    "business_loan": "business",
    "auto_loan": "auto",
    "car_loan": "auto",
    "education_loan": "education",
}

DEFAULT_REQUIRED_DOCUMENTS: dict[str, list[str]] = {
    "personal": ["kyc_id", "payslip", "bank_statement"],
    "home": ["kyc_id", "payslip", "bank_statement", "tax_return"],
    "business": ["kyc_id", "bank_statement", "tax_return"],
    "auto": ["kyc_id", "bank_statement"],
    "education": ["kyc_id", "payslip", "bank_statement"],
}

REQUEST_TEMPLATES: dict[str, str] = {
    "kyc_id": "Please provide a valid government-issued identity document (KYC) to continue processing your application.",
    "payslip": "Please provide your latest payslip to continue processing your application.",
    "bank_statement": "Please provide your latest bank statement to continue processing your application.",
    "tax_return": "Please provide your latest tax return to continue processing your application.",
}

DEFAULT_REQUEST_TEMPLATE = "Please provide your {document_label} to continue processing your application."

DOCUMENT_LABELS: dict[str, str] = {
    "kyc_id": "government-issued identity document (KYC)",
    "payslip": "latest payslip",
    "bank_statement": "latest bank statement",
    "tax_return": "latest tax return",
}


@dataclass
class MissingCheckResult:
    """Missing findings plus the required documents that *are* present."""

    missing: list[MissingDocumentFinding] = field(default_factory=list)
    present: list[str] = field(default_factory=list)

    def __len__(self) -> int:
        return len(self.missing)

    def __iter__(self):
        return iter(self.missing)


def _normalize_doc_type(raw: str) -> str:
    key = str(raw).strip().lower().replace(" ", "_")
    return DOCUMENT_TYPE_ALIASES.get(key, key)


def _normalize_loan_type(raw: str) -> str:
    key = str(raw).strip().lower().replace(" ", "_")
    return LOAN_TYPE_ALIASES.get(key, key)


def _present_types(documents_present: Iterable[Any]) -> list[str]:
    types: list[str] = []
    for item in documents_present:
        if isinstance(item, dict):
            raw = item.get("type") or item.get("document_type")
        else:
            raw = item
        if not raw:
            continue
        types.append(_normalize_doc_type(str(raw)))
    return types


def check_missing_documents(
    loan_type: str,
    required_documents_config: Mapping[str, Sequence[str]] | None,
    documents_present: Iterable[Any],
) -> MissingCheckResult:
    """Return missing-document findings for ``loan_type``.

    Parameters
    ----------
    loan_type:
        Schema loan type or alias (e.g. ``personal`` / ``personal_loan``).
    required_documents_config:
        Optional override of ``DEFAULT_REQUIRED_DOCUMENTS``. ``None`` uses the default.
    documents_present:
        Iterable of type strings or document dicts (Harris ``documents[]`` entries).
    """
    normalized_loan = _normalize_loan_type(loan_type)
    config = dict(required_documents_config or DEFAULT_REQUIRED_DOCUMENTS)
    required_raw = config.get(normalized_loan) or config.get(loan_type)
    if required_raw is None:
        required = list(DEFAULT_REQUIRED_DOCUMENTS.get(normalized_loan, []))
    else:
        required = [_normalize_doc_type(t) for t in required_raw]

    present = _present_types(documents_present)
    present_set = set(present)
    present_required = [doc_type for doc_type in required if doc_type in present_set]

    missing: list[MissingDocumentFinding] = []
    for doc_type in required:
        if doc_type in present_set:
            continue
        template = REQUEST_TEMPLATES.get(doc_type)
        if template is None:
            label = DOCUMENT_LABELS.get(doc_type, doc_type.replace("_", " "))
            message = DEFAULT_REQUEST_TEMPLATE.format(document_label=label)
        else:
            message = template
        missing.append(
            MissingDocumentFinding(
                document_type=doc_type,
                reason=f"Required for {normalized_loan} loan applications.",
                request_drafted=True,
                request_message=message,
                status="missing",
            )
        )

    return MissingCheckResult(missing=missing, present=present_required)
