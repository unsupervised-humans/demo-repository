"""Rule-based, explainable fraud / anomaly detection.

Every flag is built with ``make_fraud_flag()``. This is not an ML classifier.
Optional Grok visual checks run only after a rule already flagged a document.
"""

from __future__ import annotations

import hashlib
import os
from collections import defaultdict
from typing import Any, Iterable

from validation.findings import (
    ExtractedField,
    Finding,
    FraudFlag,
    coerce_extracted_fields,
    make_fraud_flag,
    Severity,
)
from validation.normalizers import normalize_date
from validation.thresholds import INCOME_FRAUD_THRESHOLD, INCOME_MISMATCH_THRESHOLD
from validation.validator import _relative_diff, _to_number

METADATA_CAVEAT = "Metadata anomaly alone is not proof of fraud"
XAI_API_KEY_ENV = "XAI_API_KEY"


class GrokVisualClient:
    """Thin, mockable client for an optional xAI Grok visual inspection.

    Reads ``XAI_API_KEY`` from the environment only. Never logs the key.
    """

    def __init__(self, api_key: str | None = None) -> None:
        self._api_key = api_key if api_key is not None else os.environ.get(XAI_API_KEY_ENV)

    def check(self, document: dict[str, Any], trigger_reason: str) -> dict[str, Any] | None:
        """Return a visual-inspection payload or None if the client cannot run.

        Tests should mock this method. The default implementation is a no-op stub
        so the pipeline never calls an external API unless a subclass/mock does.
        """
        if not self._api_key:
            return None
        # Stub: real HTTP calls belong behind a mock in tests / a future integration.
        _ = (document, trigger_reason)
        return None


def maybe_run_visual_check(
    document: dict[str, Any],
    trigger_reason: str,
    client: GrokVisualClient | None = None,
) -> FraudFlag | None:
    """Run only when a rule already flagged ``document``. Returns None if skipped/unavailable."""
    client = client or GrokVisualClient()
    result = client.check(document, trigger_reason)
    if not result:
        return None
    doc_id = str(document.get("doc_id") or result.get("doc_id") or "unknown")
    detail = str(result.get("detail") or result.get("description") or trigger_reason)
    evidence = str(result.get("evidence") or trigger_reason)
    severity_raw = str(result.get("severity") or "MEDIUM").upper()
    try:
        severity = Severity[severity_raw]
    except KeyError:
        severity = Severity.MEDIUM
    return make_fraud_flag(
        flag_type="visual_anomaly",
        severity=severity,
        evidence=evidence,
        doc_ids=[doc_id],
        detail=detail,
        weak_signal=False,
    )


def _findings_of_type(findings: Iterable[Finding], finding_type: str) -> list[Finding]:
    return [f for f in findings if f.finding_type == finding_type]


def _doc_ids_from_finding(finding: Finding) -> list[str]:
    ids: list[str] = []
    for src in finding.sources:
        if src.doc_id not in ids:
            ids.append(src.doc_id)
    return ids


def _escalate_name_mismatch(findings: list[Finding]) -> list[FraudFlag]:
    flags: list[FraudFlag] = []
    for finding in _findings_of_type(findings, "name_mismatch"):
        values = finding.values or {}
        named = ", ".join(f"{doc}={val!r}" for doc, val in values.items()) or finding.message
        flags.append(
            make_fraud_flag(
                flag_type="name_mismatch",
                severity=finding.severity if finding.severity != Severity.CRITICAL else Severity.HIGH,
                evidence=finding.message,
                doc_ids=_doc_ids_from_finding(finding),
                detail=(
                    f"Name mismatch reused from validation (not re-compared): {named}."
                ),
                weak_signal=False,
            )
        )
    return flags


def _escalate_income_mismatch(findings: list[Finding]) -> list[FraudFlag]:
    flags: list[FraudFlag] = []
    for finding in _findings_of_type(findings, "income_mismatch"):
        rel = float(finding.values.get("relative_difference") or 0.0)
        if rel < INCOME_FRAUD_THRESHOLD:
            continue
        income = finding.values.get("gross_monthly_income")
        deposits = finding.values.get("avg_monthly_deposit")
        pct = finding.values.get("percent_difference")
        # MEDIUM severity: income > deposits is common (taxes, multiple accounts,
        # cash usage). Only flag as HIGH if the gap exceeds 85% (nearly no income
        # reaches this account at all).
        severity = Severity.HIGH if rel > 0.85 else Severity.MEDIUM
        flags.append(
            make_fraud_flag(
                flag_type="income_mismatch",
                severity=severity,
                evidence=finding.message,
                doc_ids=_doc_ids_from_finding(finding),
                detail=(
                    f"Income {income} vs deposits {deposits} differs by {pct:.2f}% "
                    f"(threshold {INCOME_FRAUD_THRESHOLD:.0%}). May indicate multiple "
                    f"bank accounts or cash-based spending. Verify with additional statements."
                ),
                weak_signal=False,
            )
        )
    return flags


def _date_tampering(fields: list[ExtractedField], findings: list[Finding]) -> list[FraudFlag]:
    flags: list[FraudFlag] = []
    for finding in findings:
        if finding.finding_type == "date_invalid" and finding.status == "invalid":
            flags.append(
                make_fraud_flag(
                    flag_type="date_tampering",
                    severity=Severity.HIGH if "expired" in finding.message.lower() else Severity.MEDIUM,
                    evidence=finding.message,
                    doc_ids=_doc_ids_from_finding(finding),
                    detail=f"Date check classified as invalid: {finding.message}",
                    weak_signal=False,
                )
            )
        elif finding.finding_type == "date_potentially_suspicious":
            flags.append(
                make_fraud_flag(
                    flag_type="date_tampering",
                    severity=Severity.MEDIUM,
                    evidence=finding.message,
                    doc_ids=_doc_ids_from_finding(finding),
                    detail=f"Suspicious future or impossible date: {finding.message}",
                    weak_signal=False,
                )
            )

    for field in fields:
        if field.field_name not in {"id_expiry_date", "employment_start_date", "document_date"}:
            continue
        try:
            normalize_date(field.value)
        except (ValueError, TypeError):
            flags.append(
                make_fraud_flag(
                    flag_type="date_tampering",
                    severity=Severity.MEDIUM,
                    evidence=f"{field.field_name}={field.value!r} on {field.source.doc_id}",
                    doc_ids=[field.source.doc_id],
                    detail=(
                        f"Impossible/unparseable date {field.value!r} on {field.source.doc_id} "
                        f"page {field.source.page}."
                    ),
                    weak_signal=False,
                )
            )
    return flags


def _document_hash(document: dict[str, Any], fields: list[ExtractedField]) -> tuple[str, str]:
    """Return (hash_hex, method). Prefer file bytes / provided digest; else extracted text proxy."""
    provided = document.get("sha256") or document.get("file_hash") or document.get("content_hash")
    if provided:
        return str(provided).lower(), "provided_digest"

    file_path = document.get("file_path")
    if file_path and isinstance(file_path, str):
        try:
            with open(file_path, "rb") as handle:
                digest = hashlib.sha256(handle.read()).hexdigest()
            return digest, "file_bytes"
        except OSError:
            pass

    doc_id = str(document.get("doc_id") or "")
    parts = []
    for field in sorted(fields, key=lambda f: (f.field_name, str(f.value))):
        if field.source.doc_id != doc_id:
            continue
        parts.append(f"{field.field_name}={field.value}")
    proxy = "|".join(parts)
    digest = hashlib.sha256(proxy.encode("utf-8")).hexdigest()
    return digest, "extracted_text_proxy"


def _duplicate_documents(
    documents: list[dict[str, Any]],
    fields: list[ExtractedField],
) -> list[FraudFlag]:
    if len(documents) < 2:
        return []

    by_hash: dict[str, list[tuple[str, str]]] = defaultdict(list)
    for document in documents:
        doc_id = str(document.get("doc_id") or "")
        if not doc_id:
            continue
        digest, method = _document_hash(document, fields)
        by_hash[digest].append((doc_id, method))

    flags: list[FraudFlag] = []
    for digest, entries in by_hash.items():
        unique_ids = list(dict.fromkeys(e[0] for e in entries))
        if len(unique_ids) < 2:
            continue
        method = entries[0][1]
        lower_confidence = method == "extracted_text_proxy"
        named = " and ".join(unique_ids)
        detail = (
            f"POSSIBLE_DOCUMENT_REUSE: {named} share digest {digest[:12]}… "
            f"(method={method}"
            + (
                "; this is a lower-confidence proxy because file bytes were not available"
                if lower_confidence
                else ""
            )
            + ")."
        )
        flags.append(
            make_fraud_flag(
                flag_type="POSSIBLE_DOCUMENT_REUSE",
                severity=Severity.HIGH if not lower_confidence else Severity.MEDIUM,
                evidence=f"shared_hash={digest}; docs={named}; method={method}",
                doc_ids=unique_ids,
                detail=detail,
                weak_signal=lower_confidence,
            )
        )
    return flags


def _metadata_anomalies(documents: list[dict[str, Any]]) -> list[FraudFlag]:
    flags: list[FraudFlag] = []
    for document in documents:
        doc_id = str(document.get("doc_id") or "")
        metadata = document.get("metadata") if isinstance(document.get("metadata"), dict) else {}
        created = metadata.get("created_at") or document.get("created_at")
        modified = metadata.get("modified_at") or document.get("modified_at")
        software = str(metadata.get("software") or document.get("software") or "")

        reasons: list[str] = []
        if created and modified:
            try:
                created_d = normalize_date(created)
                modified_d = normalize_date(modified)
                if modified_d < created_d:
                    reasons.append(
                        f"modified_at {modified} is earlier than created_at {created}"
                    )
            except (ValueError, TypeError):
                pass
        if software.lower() in {"unknown", "edited", "photoshop", "gimp"}:
            reasons.append(f"unusual software metadata {software!r}")

        if not reasons:
            continue
        flags.append(
            make_fraud_flag(
                flag_type="metadata_anomaly",
                severity=Severity.LOW,
                evidence="; ".join(reasons),
                doc_ids=[doc_id] if doc_id else [],
                detail=(
                    f"{METADATA_CAVEAT}. Observed on {doc_id or 'unknown document'}: "
                    + "; ".join(reasons)
                    + "."
                ),
                weak_signal=True,
            )
        )
    return flags


def detect_fraud(
    extracted_fields: Any,
    documents: list[dict[str, Any]] | None,
    validation_findings: list[Finding],

    *,
    visual_client: GrokVisualClient | None = None,
    run_visual: bool = True,
) -> list[FraudFlag]:
    """Detect potential fraud indicators from validation findings + document metadata."""
    fields = coerce_extracted_fields(extracted_fields)
    docs = list(documents or [])

    flags: list[FraudFlag] = []
    flags.extend(_escalate_name_mismatch(validation_findings))
    flags.extend(_escalate_income_mismatch(validation_findings))
    flags.extend(_date_tampering(fields, validation_findings))
    flags.extend(_duplicate_documents(docs, fields))
    flags.extend(_metadata_anomalies(docs))

    flagged_doc_ids = {doc_id for flag in flags for doc_id in flag.doc_ids}
    if run_visual and flagged_doc_ids:
        client = visual_client or GrokVisualClient()
        for document in docs:
            doc_id = str(document.get("doc_id") or "")
            if doc_id not in flagged_doc_ids:
                continue
            visual_flag = maybe_run_visual_check(
                document,
                trigger_reason=f"rule-based flag already present for {doc_id}",
                client=client,
            )
            if visual_flag is not None:
                flags.append(visual_flag)

    # One weak signal alone must never be CRITICAL (also enforced in make_fraud_flag).
    if len(flags) == 1 and flags[0].weak_signal and flags[0].severity is Severity.CRITICAL:
        flags[0] = make_fraud_flag(
            flag_type=flags[0].flag_type,
            severity=Severity.MEDIUM,
            evidence=flags[0].evidence,
            doc_ids=flags[0].doc_ids,
            detail=flags[0].description,
            weak_signal=True,
        )

    return flags
