"""Structured retrieval from loan_file for the Reviewer Q&A agent.

For the MVP, this uses keyword-based structured retrieval rather than
vector embeddings (FAISS / Sentence Transformers).  The loan_file is
small and structured — embedding-based retrieval adds complexity without
proportional benefit at this scale.
"""

from __future__ import annotations

import json
from typing import Any


# ── Keyword → section mapping ────────────────────────────────────────────────

_SECTION_KEYWORDS: dict[str, list[str]] = {
    "applicant": ["applicant", "name", "borrower", "person", "who"],
    "documents": ["document", "upload", "file", "pdf", "received", "missing"],
    "extracted_fields": [
        "income", "salary", "amount", "employer", "bank", "deposit",
        "field", "extract", "value", "confidence", "expiry",
    ],
    "validation_findings": [
        "validation", "finding", "inconsistency", "mismatch", "check",
        "discrepancy", "conflict", "differ",
    ],
    "missing_documents": ["missing", "required", "absent", "incomplete"],
    "fraud_flags": [
        "fraud", "flag", "suspicious", "tamper", "anomaly", "fake",
        "forged",
    ],
    "risk_score": [
        "risk", "score", "probability", "approval", "factor", "shap",
        "model", "predict",
    ],
    "compliance": [
        "compliance", "fairness", "bias", "protected", "attribute",
        "discriminat",
    ],
    "summary_report": ["summary", "recommend", "decision", "review"],
}


def _match_sections(question: str) -> list[str]:
    """Return loan_file sections relevant to *question*."""
    q_lower = question.lower()
    matched: list[str] = []

    for section, keywords in _SECTION_KEYWORDS.items():
        for kw in keywords:
            if kw in q_lower:
                matched.append(section)
                break

    # "Why was this flagged?" is a common catch-all.
    if "flag" in q_lower or "why" in q_lower:
        for s in ("fraud_flags", "validation_findings", "risk_score", "missing_documents"):
            if s not in matched:
                matched.append(s)

    # "Where did X come from?" → extraction + documents.
    if "where" in q_lower or "source" in q_lower or "come from" in q_lower:
        for s in ("extracted_fields", "documents"):
            if s not in matched:
                matched.append(s)

    # Default: if nothing matched, return everything.
    if not matched:
        matched = list(_SECTION_KEYWORDS.keys())

    return matched


def _format_section(section: str, data: Any) -> str:
    """Format a single loan_file section as readable context."""
    if data is None:
        return f"## {section}\nNo data available.\n"

    if isinstance(data, list):
        if not data:
            return f"## {section}\nEmpty — no entries.\n"
        lines = [f"## {section} ({len(data)} entries)"]
        for i, item in enumerate(data, 1):
            if isinstance(item, dict):
                lines.append(f"\n### Entry {i}")
                for k, v in item.items():
                    lines.append(f"  {k}: {v}")
            else:
                lines.append(f"  - {item}")
        return "\n".join(lines) + "\n"

    if isinstance(data, dict):
        lines = [f"## {section}"]
        for k, v in data.items():
            lines.append(f"  {k}: {v}")
        return "\n".join(lines) + "\n"

    return f"## {section}\n{data}\n"


def retrieve_context(
    loan_file: dict[str, Any],
    question: str,
) -> str:
    """Retrieve relevant structured context from loan_file for a question.

    Parameters
    ----------
    loan_file : dict
        The full loan_file state.
    question : str
        The reviewer's question.

    Returns
    -------
    str
        Formatted context string with source references.
    """
    sections = _match_sections(question)

    parts: list[str] = [
        f"Application ID: {loan_file.get('application_id', '?')}",
        f"Status: {loan_file.get('status', '?')}",
        "",
    ]

    for section in sections:
        data = loan_file.get(section)
        parts.append(_format_section(section, data))

    return "\n".join(parts)


def get_source_references(
    loan_file: dict[str, Any],
    question: str,
) -> list[dict[str, Any]]:
    """Extract source references relevant to a question.

    Returns a list of ``{doc_id, page, field_name, value}`` entries.
    """
    refs: list[dict[str, Any]] = []
    seen: set[tuple[str, int]] = set()

    sections = _match_sections(question)

    if "extracted_fields" in sections:
        for f in loan_file.get("extracted_fields") or []:
            src = f.get("source", {})
            if isinstance(src, dict) and "doc_id" in src:
                key = (src["doc_id"], src.get("page", 0))
                if key not in seen:
                    seen.add(key)
                    refs.append({
                        "doc_id": src["doc_id"],
                        "page": src.get("page", 1),
                        "field_name": f.get("field_name", "?"),
                        "value": f.get("value"),
                    })

    if "validation_findings" in sections:
        for finding in loan_file.get("validation_findings") or []:
            for doc_id in finding.get("doc_ids") or []:
                key = (doc_id, 0)
                if key not in seen:
                    seen.add(key)
                    refs.append({
                        "doc_id": doc_id,
                        "page": 1,
                        "field_name": finding.get("finding_id", "?"),
                        "value": finding.get("description", "?"),
                    })

    if "fraud_flags" in sections:
        for flag in loan_file.get("fraud_flags") or []:
            for doc_id in flag.get("doc_ids") or []:
                key = (doc_id, 0)
                if key not in seen:
                    seen.add(key)
                    refs.append({
                        "doc_id": doc_id,
                        "page": 1,
                        "field_name": flag.get("flag_id", "?"),
                        "value": flag.get("description", "?"),
                    })

    return refs
