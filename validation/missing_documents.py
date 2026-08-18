"""Missing-document agent.

Config shape
------------
``required_documents_config`` is a mapping of loan_type -> list of document_type
strings. Document types MUST be values from the shared schema enum
(``payslip``, ``bank_statement``, ``tax_return``, ``kyc_id``).

Loan types follow ``applicant.loan_type`` in the schema (``personal``, ``home``,
``auto``, ``education``, ``business``). Aliases such as ``personal_loan`` and
``identity_document`` are accepted and normalized.

Field-signature inference
--------------------------
When a combined PDF is uploaded (classified as ``combined_loan_package`` or
``unknown``), the ``documents[]`` list may only contain a single entry with
type ``combined_loan_package`` or ``unknown`` — even though all required
document sections are present inside that one file.

To avoid false "missing document" flags in this case, the agent also checks
``extracted_fields[]`` for field-level signatures that prove a document type
is present:

  - ``kyc_id`` is inferred present if any of:
      id_number, id_expiry_date, pan_number, id_document_type are extracted
      with confidence > 0.3.
  - ``payslip`` is inferred present if any of:
      gross_monthly_income, net_monthly_income, pay_period_start, employer_name
      are extracted with confidence > 0.3.
  - ``bank_statement`` is inferred present if any of:
      avg_monthly_deposit, account_number, statement_period_start,
      opening_balance are extracted with confidence > 0.3.
  - ``tax_return`` is inferred present if any of:
      assessment_year, gross_total_income, itr_form_type are extracted
      with confidence > 0.3.

This is a generalized heuristic — it never checks for specific applicant
names or filenames, only for the presence of field types.
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
    # Combined packages: count as providing all sub-types (handled via field signatures)
    "combined_loan_package": "combined_loan_package",
    "combined": "combined_loan_package",
    "application_form": "application_form",
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

# Field signatures: presence of ANY one of these fields (with confidence > 0.3
# and non-null value) proves the corresponding document type is present.
FIELD_SIGNATURES: dict[str, frozenset[str]] = {
    "kyc_id": frozenset({
        "id_number", "id_expiry_date", "pan_number", "id_document_type",
        "applicant_name",  # applicant_name from KYC is a strong signal
    }),
    "payslip": frozenset({
        "gross_monthly_income", "net_monthly_income", "pay_period_start",
        "pay_period_end", "employer_name", "employee_name", "employee_id",
        "designation",
    }),
    "bank_statement": frozenset({
        "avg_monthly_deposit", "avg_monthly_withdrawal", "account_number",
        "statement_period_start", "statement_period_end",
        "opening_balance", "closing_balance", "bank_name",
        "account_holder_name",
    }),
    "tax_return": frozenset({
        "assessment_year", "gross_total_income", "taxable_income",
        "itr_form_type", "tax_paid", "filing_date",
    }),
}

# Minimum confidence for a field to count as "present"
_FIELD_CONFIDENCE_THRESHOLD = 0.3


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


def _inferred_types_from_fields(extracted_fields: Iterable[Any]) -> set[str]:
    """Infer which document types are present based on extracted field signatures.

    Returns a set of document type strings (e.g. {'kyc_id', 'payslip'}).
    A document type is inferred as present if at least one signature field for
    that type appears in extracted_fields with:
      - confidence > _FIELD_CONFIDENCE_THRESHOLD
      - value is not None
    """
    inferred: set[str] = set()
    fields_list = list(extracted_fields)

    if not fields_list:
        return inferred

    # Build a lookup: field_name -> (max_confidence, has_non_null_value)
    field_presence: dict[str, tuple[float, bool]] = {}
    for f in fields_list:
        if not isinstance(f, dict):
            continue
        name = str(f.get("field_name") or "").strip().lower()
        if not name:
            continue
        # Skip failure sentinels
        if name.startswith("extraction_failure_"):
            continue
        confidence = 0.0
        try:
            confidence = float(f.get("confidence") or 0.0)
        except (TypeError, ValueError):
            confidence = 0.0
        value = f.get("value")
        has_value = value is not None

        if name not in field_presence:
            field_presence[name] = (confidence, has_value)
        else:
            prev_conf, prev_val = field_presence[name]
            field_presence[name] = (
                max(prev_conf, confidence),
                prev_val or has_value,
            )

    # Check each document type's signature fields
    for doc_type, signatures in FIELD_SIGNATURES.items():
        for sig_field in signatures:
            if sig_field in field_presence:
                conf, has_value = field_presence[sig_field]
                if conf > _FIELD_CONFIDENCE_THRESHOLD and has_value:
                    inferred.add(doc_type)
                    break  # Found one signature field - doc type is present

    return inferred


def check_missing_documents(
    loan_type: str,
    required_documents_config: Mapping[str, Sequence[str]] | None,
    documents_present: Iterable[Any],
    extracted_fields: Iterable[Any] | None = None,
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
    extracted_fields:
        Optional list of extracted field dicts from Austin's extraction pipeline.
        When provided, used to infer document presence via field signatures,
        which handles combined multi-section PDFs where all sections appear as
        a single document entry in ``documents[]``.
    """
    normalized_loan = _normalize_loan_type(loan_type)
    config = dict(required_documents_config or DEFAULT_REQUIRED_DOCUMENTS)
    required_raw = config.get(normalized_loan) or config.get(loan_type)
    if required_raw is None:
        required = list(DEFAULT_REQUIRED_DOCUMENTS.get(normalized_loan, []))
    else:
        required = [_normalize_doc_type(t) for t in required_raw]

    # Types present in documents[]
    doc_types = _present_types(documents_present)
    doc_type_set = set(doc_types)

    # If a combined_loan_package is present, it might contain everything.
    # We don't assume it does — we rely on field signatures to determine
    # what was actually extracted.
    has_combined = "combined_loan_package" in doc_type_set

    # Types inferred from extracted_fields signatures
    inferred_set: set[str] = set()
    if extracted_fields is not None:
        inferred_set = _inferred_types_from_fields(extracted_fields)

    # Union of all known-present types
    all_present = doc_type_set | inferred_set

    present_required = [doc_type for doc_type in required if doc_type in all_present]

    missing: list[MissingDocumentFinding] = []
    for doc_type in required:
        if doc_type in all_present:
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
