"""Cross-document validation agent.

Entrypoint
----------
    from validation.validator import validate

    findings = validate(extracted_fields)

Each check is skipped silently when a required field is absent — the missing-
document agent owns absence, not this module. Sources are copied from Austin
and never fabricated.
"""

from __future__ import annotations

from collections import defaultdict
from datetime import date
from typing import Any, Iterable

from validation.findings import (
    ExtractedField,
    Finding,
    Severity,
    SourceRef,
    coerce_extracted_fields,
    make_finding,
)
from validation.normalizers import (
    normalize_address,
    normalize_date,
    normalize_name,
    string_similarity,
)
from validation.thresholds import (
    ADDRESS_SIMILARITY_THRESHOLD,
    DATE_TOLERANCE_DAYS,
    INCOME_MISMATCH_THRESHOLD,
    NAME_SIMILARITY_THRESHOLD,
)

NAME_FIELD_NAMES = frozenset({"applicant_name", "employee_name", "account_holder_name"})
INCOME_FIELD_NAMES = frozenset({"gross_monthly_income"})
DEPOSIT_FIELD_NAMES = frozenset({"avg_monthly_deposit", "average_monthly_deposits"})
EMPLOYER_FIELD_NAMES = frozenset({"employer_name"})
ADDRESS_LINE_FIELDS = ("address_line1", "address_line2", "address_city", "address_state", "address_pincode")
FULL_ADDRESS_FIELDS = frozenset({"address", "residential_address"})
ID_EXPIRY_FIELDS = frozenset({"id_expiry_date"})
EMPLOYMENT_START_FIELDS = frozenset({"employment_start_date"})
PAY_PERIOD_START = frozenset({"pay_period_start"})
PAY_PERIOD_END = frozenset({"pay_period_end"})
STMT_PERIOD_START = frozenset({"statement_period_start"})
STMT_PERIOD_END = frozenset({"statement_period_end"})
TAX_YEAR_FIELDS = frozenset({"assessment_year", "tax_year"})
APPLICATION_DATE_FIELDS = frozenset({"application_date"})


def _usable(field: ExtractedField) -> bool:
    value = field.value
    if value is None:
        return False
    if isinstance(value, str) and not value.strip():
        return False
    return True


def _fields_named(fields: Iterable[ExtractedField], names: frozenset[str]) -> list[ExtractedField]:
    return [f for f in fields if f.field_name in names and _usable(f)]


def _fmt_sources(sources: list[SourceRef]) -> str:
    return ", ".join(f"{s.doc_id}/Page {s.page}" for s in sources)


def _relative_diff(a: float, b: float) -> float:
    denom = max(abs(a), abs(b))
    if denom == 0:
        return 0.0
    return abs(a - b) / denom


def _to_number(value: Any) -> float | None:
    if isinstance(value, bool):
        return None
    if isinstance(value, (int, float)):
        return float(value)
    if isinstance(value, str):
        cleaned = value.replace(",", "").replace("₹", "").replace("Rs", "").replace("INR", "").strip()
        try:
            return float(cleaned)
        except ValueError:
            return None
    return None


def _check_name_consistency(fields: list[ExtractedField]) -> list[Finding]:
    name_fields = _fields_named(fields, NAME_FIELD_NAMES)
    if len(name_fields) < 2:
        return []

    groups: dict[str, list[ExtractedField]] = defaultdict(list)
    for field in name_fields:
        groups[normalize_name(str(field.value))].append(field)

    keys = [k for k in groups if k]
    if len(keys) <= 1:
        return []

    # Compare every pair of distinct normalized names; flag if below threshold.
    findings: list[Finding] = []
    for i, left_key in enumerate(keys):
        for right_key in keys[i + 1 :]:
            score = string_similarity(left_key, right_key)
            if score >= NAME_SIMILARITY_THRESHOLD:
                continue
            left = groups[left_key][0]
            right = groups[right_key][0]
            sources = [left.source, right.source]
            findings.append(
                make_finding(
                    finding_type="name_mismatch",
                    severity=Severity.HIGH,
                    message=(
                        f"Applicant name differs across documents: "
                        f"{left.source.doc_id} ({left.field_name}) has {left.value!r} vs "
                        f"{right.source.doc_id} ({right.field_name}) has {right.value!r} "
                        f"(normalized similarity {score:.2f}, threshold {NAME_SIMILARITY_THRESHOLD}). "
                        f"Sources: {_fmt_sources(sources)}."
                    ),
                    fields_compared=[left.field_name, right.field_name],
                    sources=sources,
                    status="mismatch",
                    values={left.source.doc_id: left.value, right.source.doc_id: right.value},
                )
            )
    return findings


def _check_income_consistency(fields: list[ExtractedField]) -> list[Finding]:
    incomes = _fields_named(fields, INCOME_FIELD_NAMES)
    deposits = _fields_named(fields, DEPOSIT_FIELD_NAMES)
    if not incomes or not deposits:
        return []

    income_field = incomes[0]
    deposit_field = deposits[0]
    income_val = _to_number(income_field.value)
    deposit_val = _to_number(deposit_field.value)
    if income_val is None or deposit_val is None:
        return []

    rel = _relative_diff(income_val, deposit_val)
    if rel <= INCOME_MISMATCH_THRESHOLD:
        return []

    pct = rel * 100
    sources = [income_field.source, deposit_field.source]
    return [
        make_finding(
            finding_type="income_mismatch",
            severity=Severity.HIGH,
            message=(
                f"Declared income differs from observed bank deposits: "
                f"{income_field.source.doc_id} {income_field.field_name}={income_val:,.2f} vs "
                f"{deposit_field.source.doc_id} {deposit_field.field_name}={deposit_val:,.2f} "
                f"(relative difference {pct:.2f}%, threshold {INCOME_MISMATCH_THRESHOLD:.0%}). "
                f"Sources: {_fmt_sources(sources)}."
            ),
            fields_compared=[income_field.field_name, deposit_field.field_name],
            sources=sources,
            status="mismatch",
            values={
                "gross_monthly_income": income_val,
                "avg_monthly_deposit": deposit_val,
                "relative_difference": rel,
                "percent_difference": pct,
            },
        )
    ]


def _assemble_address(fields_for_doc: list[ExtractedField]) -> tuple[str, ExtractedField] | None:
    by_name = {f.field_name: f for f in fields_for_doc if _usable(f)}
    for full_name in FULL_ADDRESS_FIELDS:
        if full_name in by_name:
            return str(by_name[full_name].value), by_name[full_name]

    parts: list[str] = []
    source_field: ExtractedField | None = None
    for name in ADDRESS_LINE_FIELDS:
        field = by_name.get(name)
        if field is None:
            continue
        parts.append(str(field.value))
        source_field = field
    if not parts or source_field is None:
        return None
    return ", ".join(parts), source_field


def _check_address_consistency(fields: list[ExtractedField]) -> list[Finding]:
    by_doc: dict[str, list[ExtractedField]] = defaultdict(list)
    for field in fields:
        by_doc[field.source.doc_id].append(field)

    assembled: list[tuple[str, str, ExtractedField]] = []
    for doc_id, doc_fields in by_doc.items():
        result = _assemble_address(doc_fields)
        if result is None:
            continue
        raw, field = result
        assembled.append((doc_id, raw, field))

    if len(assembled) < 2:
        return []

    findings: list[Finding] = []
    for i, (left_doc, left_raw, left_field) in enumerate(assembled):
        for right_doc, right_raw, right_field in assembled[i + 1 :]:
            left_norm = normalize_address(left_raw)
            right_norm = normalize_address(right_raw)
            if left_norm == right_norm:
                continue
            score = string_similarity(left_norm, right_norm)
            sources = [left_field.source, right_field.source]
            if score >= ADDRESS_SIMILARITY_THRESHOLD:
                findings.append(
                    make_finding(
                        finding_type="address_minor_variation",
                        severity=Severity.LOW,
                        message=(
                            f"Address formatting variation between {left_doc} ({left_raw!r}) and "
                            f"{right_doc} ({right_raw!r}); normalized similarity {score:.2f} "
                            f"(threshold {ADDRESS_SIMILARITY_THRESHOLD}). "
                            f"Sources: {_fmt_sources(sources)}."
                        ),
                        fields_compared=["address"],
                        sources=sources,
                        status="minor_variation",
                        values={left_doc: left_raw, right_doc: right_raw},
                    )
                )
            else:
                findings.append(
                    make_finding(
                        finding_type="address_mismatch",
                        severity=Severity.MEDIUM,
                        message=(
                            f"Address mismatch between {left_doc} ({left_raw!r}) and "
                            f"{right_doc} ({right_raw!r}); normalized similarity {score:.2f} "
                            f"(threshold {ADDRESS_SIMILARITY_THRESHOLD}). "
                            f"Sources: {_fmt_sources(sources)}."
                        ),
                        fields_compared=["address"],
                        sources=sources,
                        status="mismatch",
                        values={left_doc: left_raw, right_doc: right_raw},
                    )
                )
    return findings


def _try_parse_date(value: Any) -> date | None:
    try:
        return normalize_date(value)
    except (ValueError, TypeError):
        return None


def _check_date_consistency(
    fields: list[ExtractedField],
    application_date: date | None,
) -> list[Finding]:
    findings: list[Finding] = []
    today = application_date or date.today()

    for field in _fields_named(fields, ID_EXPIRY_FIELDS):
        expiry = _try_parse_date(field.value)
        if expiry is None:
            findings.append(
                make_finding(
                    finding_type="date_invalid",
                    severity=Severity.MEDIUM,
                    message=(
                        f"ID expiry date on {field.source.doc_id} is unparseable: {field.value!r}. "
                        f"Sources: {_fmt_sources([field.source])}."
                    ),
                    fields_compared=[field.field_name],
                    sources=[field.source],
                    status="invalid",
                    values={"id_expiry_date": field.value},
                )
            )
            continue
        if expiry < today:
            findings.append(
                make_finding(
                    finding_type="date_invalid",
                    severity=Severity.HIGH,
                    message=(
                        f"ID on {field.source.doc_id} expired on {expiry.isoformat()} "
                        f"(application date {today.isoformat()}). "
                        f"Sources: {_fmt_sources([field.source])}."
                    ),
                    fields_compared=[field.field_name],
                    sources=[field.source],
                    status="invalid",
                    values={"id_expiry_date": expiry.isoformat(), "application_date": today.isoformat()},
                )
            )

    for field in _fields_named(fields, EMPLOYMENT_START_FIELDS):
        start = _try_parse_date(field.value)
        if start is None:
            findings.append(
                make_finding(
                    finding_type="date_invalid",
                    severity=Severity.MEDIUM,
                    message=(
                        f"Employment start date on {field.source.doc_id} is unparseable: {field.value!r}. "
                        f"Sources: {_fmt_sources([field.source])}."
                    ),
                    fields_compared=[field.field_name],
                    sources=[field.source],
                    status="invalid",
                    values={"employment_start_date": field.value},
                )
            )
            continue
        if start > today:
            findings.append(
                make_finding(
                    finding_type="date_potentially_suspicious",
                    severity=Severity.MEDIUM,
                    message=(
                        f"Employment start date {start.isoformat()} on {field.source.doc_id} "
                        f"is in the future relative to application date {today.isoformat()}. "
                        f"Sources: {_fmt_sources([field.source])}."
                    ),
                    fields_compared=[field.field_name],
                    sources=[field.source],
                    status="potentially_suspicious",
                    values={"employment_start_date": start.isoformat()},
                )
            )

    pay_starts = _fields_named(fields, PAY_PERIOD_START)
    pay_ends = _fields_named(fields, PAY_PERIOD_END)
    stmt_starts = _fields_named(fields, STMT_PERIOD_START)
    stmt_ends = _fields_named(fields, STMT_PERIOD_END)
    if pay_starts and pay_ends and stmt_starts and stmt_ends:
        ps = _try_parse_date(pay_starts[0].value)
        pe = _try_parse_date(pay_ends[0].value)
        ss = _try_parse_date(stmt_starts[0].value)
        se = _try_parse_date(stmt_ends[0].value)
        if ps is not None and pe is not None and ss is not None and se is not None:
            gap = min(abs((ps - se).days), abs((ss - pe).days), abs((ps - ss).days))
            overlapping = not (pe < ss or se < ps)
            if not overlapping and gap > DATE_TOLERANCE_DAYS:
                sources = [pay_starts[0].source, stmt_starts[0].source]
                findings.append(
                    make_finding(
                        finding_type="date_inconsistent",
                        severity=Severity.MEDIUM,
                        message=(
                            f"Payslip period {ps.isoformat()}–{pe.isoformat()} "
                            f"({pay_starts[0].source.doc_id}) does not overlap bank statement "
                            f"period {ss.isoformat()}–{se.isoformat()} ({stmt_starts[0].source.doc_id}); "
                            f"gap exceeds {DATE_TOLERANCE_DAYS} days. "
                            f"Sources: {_fmt_sources(sources)}."
                        ),
                        fields_compared=[
                            pay_starts[0].field_name,
                            pay_ends[0].field_name,
                            stmt_starts[0].field_name,
                            stmt_ends[0].field_name,
                        ],
                        sources=sources,
                        status="inconsistent",
                    )
                )

    tax_years = _fields_named(fields, TAX_YEAR_FIELDS)
    if tax_years and pay_ends:
        pe = _try_parse_date(pay_ends[0].value)
        # assessment_year like '2025-26' — compare starting year if parseable
        if pe is not None:
            raw_year = str(tax_years[0].value)
            year_match = None
            try:
                year_match = int(str(raw_year)[:4])
            except ValueError:
                year_match = None
            if year_match is not None and abs(pe.year - year_match) > 1:
                sources = [pay_ends[0].source, tax_years[0].source]
                findings.append(
                    make_finding(
                        finding_type="date_inconsistent",
                        severity=Severity.LOW,
                        message=(
                            f"Payslip year {pe.year} ({pay_ends[0].source.doc_id}) is inconsistent with "
                            f"tax assessment year {raw_year!r} ({tax_years[0].source.doc_id}). "
                            f"Sources: {_fmt_sources(sources)}."
                        ),
                        fields_compared=[pay_ends[0].field_name, tax_years[0].field_name],
                        sources=sources,
                        status="inconsistent",
                    )
                )

    return findings


def _check_employment_consistency(fields: list[ExtractedField]) -> list[Finding]:
    employers = _fields_named(fields, EMPLOYER_FIELD_NAMES)
    if len(employers) < 2:
        return []

    groups: dict[str, list[ExtractedField]] = defaultdict(list)
    for field in employers:
        groups[normalize_name(str(field.value))].append(field)

    keys = [k for k in groups if k]
    if len(keys) <= 1:
        return []

    findings: list[Finding] = []
    for i, left_key in enumerate(keys):
        for right_key in keys[i + 1 :]:
            score = string_similarity(left_key, right_key)
            if score >= NAME_SIMILARITY_THRESHOLD:
                continue
            left = groups[left_key][0]
            right = groups[right_key][0]
            sources = [left.source, right.source]
            findings.append(
                make_finding(
                    finding_type="employer_mismatch",
                    severity=Severity.HIGH,
                    message=(
                        f"Employer name differs across documents: "
                        f"{left.source.doc_id} has {left.value!r} vs "
                        f"{right.source.doc_id} has {right.value!r} "
                        f"(normalized similarity {score:.2f}, threshold {NAME_SIMILARITY_THRESHOLD}). "
                        f"Sources: {_fmt_sources(sources)}."
                    ),
                    fields_compared=[left.field_name, right.field_name],
                    sources=sources,
                    status="mismatch",
                    values={left.source.doc_id: left.value, right.source.doc_id: right.value},
                )
            )
    return findings


def validate(
    extracted_fields: Any,
    *,

    application_date: date | str | None = None,
) -> list[Finding]:
    """Run all cross-document checks. Skip any check whose inputs are absent."""
    fields = coerce_extracted_fields(extracted_fields)
    app_date: date | None = None
    if application_date is not None:
        app_date = _try_parse_date(application_date)
    if app_date is None:
        app_fields = _fields_named(fields, APPLICATION_DATE_FIELDS)
        if app_fields:
            app_date = _try_parse_date(app_fields[0].value)

    findings: list[Finding] = []
    findings.extend(_check_name_consistency(fields))
    findings.extend(_check_income_consistency(fields))
    findings.extend(_check_address_consistency(fields))
    findings.extend(_check_date_consistency(fields, app_date))
    findings.extend(_check_employment_consistency(fields))
    return findings
