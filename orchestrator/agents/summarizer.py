"""Summarization Agent — generates an explainable loan review summary.

Uses the shared Grok client to produce a structured narrative from the
full loan_file, with a deterministic fallback when the LLM is unavailable.

Summary rules:
- Separate FACTS from FINDINGS from MODEL OUTPUT from RECOMMENDATION.
- Never invent facts — every claim must trace to structured data.
- Never present an AI recommendation as a guaranteed approval.
"""

from __future__ import annotations

import json
import logging
from typing import Any

from orchestrator.error_handling import retry_with_backoff

logger = logging.getLogger(__name__)


# ── Prompt template ───────────────────────────────────────────────────────────

_SYSTEM_PROMPT = """\
You are a senior loan underwriter AI for LoanIQ, writing an internal credit review memo.

Your job: produce a detailed, DATA-DRIVEN summary of THIS specific loan application for a human reviewer.
Every sentence MUST reference actual extracted values from the structured data provided.

REQUIREMENTS:
1. Lead with the applicant's name, loan amount, and loan type.
2. Describe the income evidence: what documents were received, what income figures were extracted, and their confidence levels.
3. Describe the risk score: state the exact approval_probability (as a %) and explain the top 3 risk factors (feature name + contribution).
4. Note any missing documents, validation findings, or fraud flags explicitly.
5. Give a clear, reasoned recommendation with specific justification (not generic boilerplate).
6. If data is missing/low-confidence, say exactly which fields are missing and why that matters.
7. Keep it concise: max 300 words. No bullet points — write in prose paragraphs.

CRITICAL: Do NOT write generic text. Every sentence must cite a specific value, date, amount, or document from the data.

Respond with ONLY a valid JSON object (no markdown fences, no preamble) with these exact keys:
{
  "narrative": "<detailed prose summary, 150-300 words>",
  "recommendation": "<approve | reject | request_more_info>",
  "citations": [{"doc_id": "<id>", "page": <number>}, ...]
}
"""


def _build_user_prompt(loan_file: dict[str, Any]) -> str:
    """Build the user-facing prompt from structured loan_file data."""
    parts: list[str] = []

    # Applicant
    applicant = loan_file.get("applicant") or {}
    parts.append(f"APPLICANT INFO: {json.dumps(applicant, ensure_ascii=False)}")

    # Documents received
    docs = loan_file.get("documents") or []
    doc_summary = [{"doc_id": d.get("doc_id"), "type": d.get("type") or d.get("document_type"), "file": d.get("file_name")} for d in docs]
    parts.append(f"DOCUMENTS RECEIVED ({len(docs)} total): {json.dumps(doc_summary, ensure_ascii=False)}")

    # Extracted fields — include all non-sentinel fields with their values and confidence
    fields = loan_file.get("extracted_fields") or []
    useful_fields = [
        {"field": f.get("field_name"), "value": f.get("value"), "confidence": round(float(f.get("confidence") or 0), 2)}
        for f in fields
        if f.get("field_name") and not str(f.get("field_name", "")).startswith("extraction_failure_")
        and f.get("value") is not None
    ]
    parts.append(f"EXTRACTED FIELD VALUES ({len(useful_fields)} fields with data): {json.dumps(useful_fields, ensure_ascii=False)}")

    # Missing and low-confidence fields
    missing_fields = [
        {"field": f.get("field_name"), "confidence": round(float(f.get("confidence") or 0), 2)}
        for f in fields
        if f.get("value") is None or float(f.get("confidence") or 0) < 0.4
    ]
    if missing_fields:
        parts.append(f"LOW-CONFIDENCE OR MISSING FIELDS: {json.dumps(missing_fields, ensure_ascii=False)}")

    # Validation findings
    findings = loan_file.get("validation_findings") or []
    parts.append(f"VALIDATION FINDINGS: {json.dumps(findings, ensure_ascii=False)}")

    # Missing documents
    missing = loan_file.get("missing_documents") or []
    if missing:
        parts.append(f"MISSING REQUIRED DOCUMENTS: {json.dumps([m.get('document_type') for m in missing], ensure_ascii=False)}")

    # Fraud flags
    fraud = loan_file.get("fraud_flags") or []
    parts.append(f"FRAUD FLAGS: {json.dumps(fraud, ensure_ascii=False)}")

    # Risk score — include full detail
    risk = loan_file.get("risk_score") or {}
    prob = risk.get("approval_probability")
    prob_str = f"{prob:.1%}" if prob is not None else "N/A (INSUFFICIENT_DATA)"
    factors = risk.get("factors") or []
    top_factors = sorted(factors, key=lambda x: abs(x.get("contribution", 0)), reverse=True)[:5]
    risk_summary = {
        "approval_probability": prob_str,
        "status": risk.get("status"),
        "top_factors": top_factors,
        "data_completeness_note": risk.get("data_completeness_note"),
    }
    parts.append(f"RISK ASSESSMENT: {json.dumps(risk_summary, ensure_ascii=False)}")

    # Compliance
    compliance = loan_file.get("compliance") or {}
    parts.append(f"COMPLIANCE: {json.dumps(compliance, ensure_ascii=False)}")

    return "\n\n".join(parts)


def _extract_json_dict(text: str) -> dict[str, Any] | None:
    """Extract and parse a JSON dictionary from arbitrary LLM response text."""
    text = text.strip()

    # 1. Strip thinking tags <think>...</think> if present
    if "<think>" in text:
        if "</think>" in text:
            text = text.split("</think>", 1)[1].strip()
        else:
            idx = text.find("{")
            if idx != -1:
                text = text[idx:]

    # 2. Try direct json.loads
    try:
        data = json.loads(text)
        if isinstance(data, dict):
            return data
    except json.JSONDecodeError:
        pass

    # 3. Extract text inside markdown code fences ```json ... ``` or ``` ... ```
    if "```" in text:
        for part in text.split("```"):
            cleaned = part.strip()
            if cleaned.startswith("json"):
                cleaned = cleaned[4:].strip()
            try:
                data = json.loads(cleaned)
                if isinstance(data, dict):
                    return data
            except json.JSONDecodeError:
                pass

    # 4. Search for JSON object by matching braces { ... }
    first_brace = text.find("{")
    last_brace = text.rfind("}")
    while first_brace != -1 and last_brace > first_brace:
        candidate = text[first_brace : last_brace + 1]
        try:
            data = json.loads(candidate)
            if isinstance(data, dict):
                return data
        except json.JSONDecodeError:
            first_brace = text.find("{", first_brace + 1)

    return None


def _parse_summary_response(raw: str) -> dict[str, Any] | None:
    """Parse the LLM's JSON response into a summary_report dict."""
    data = _extract_json_dict(raw)
    if not data:
        logger.warning("Failed to parse LLM summary response: %s", raw[:200])
        return None

    # Validate required keys
    narrative = data.get("narrative")
    recommendation = data.get("recommendation", "request_more_info")
    citations = data.get("citations", [])

    # Normalize recommendation
    valid_recs = {"approve", "reject", "request_more_info"}
    if recommendation not in valid_recs:
        recommendation = "request_more_info"

    # Normalize citations
    clean_citations = []
    for c in citations if isinstance(citations, list) else []:
        if isinstance(c, dict) and "doc_id" in c and "page" in c:
            clean_citations.append({"doc_id": c["doc_id"], "page": c["page"]})

    return {
        "narrative": narrative or "Summary could not be generated.",
        "recommendation": recommendation,
        "citations": clean_citations,
    }


def _build_deterministic_summary(
    loan_file: dict[str, Any],
    recommendation: str,
) -> dict[str, Any]:
    """Build a summary without the LLM — pure structured data extraction."""
    parts: list[str] = []

    # Applicant facts
    applicant = loan_file.get("applicant") or {}
    if applicant.get("name"):
        parts.append(f"Applicant: {applicant['name']}")
    if applicant.get("declared_income"):
        parts.append(f"Declared income: ₹{applicant['declared_income']:,.0f}")
    if applicant.get("loan_amount_requested"):
        parts.append(f"Loan amount requested: ₹{applicant['loan_amount_requested']:,.0f}")
    if applicant.get("loan_type"):
        parts.append(f"Loan type: {applicant['loan_type']}")

    # Documents
    docs = loan_file.get("documents") or []
    parts.append(f"\nDocuments: {len(docs)} received")

    # Key extracted values
    fields = loan_file.get("extracted_fields") or []
    income_fields = [f for f in fields if "income" in f.get("field_name", "").lower()]
    for f in income_fields:
        parts.append(
            f"  {f['field_name']}: {f.get('value', 'N/A')} "
            f"(confidence: {f.get('confidence', 0):.2f})"
        )

    # Validation
    findings = loan_file.get("validation_findings") or []
    if findings:
        parts.append(f"\nValidation: {len(findings)} finding(s)")
        for f in findings:
            parts.append(f"  [{f.get('severity', '?')}] {f.get('description', '?')}")
    else:
        parts.append("\nValidation: Passed")

    # Missing docs
    missing = loan_file.get("missing_documents") or []
    if missing:
        types = [m.get("document_type", "?") for m in missing]
        parts.append(f"\nMissing documents: {', '.join(types)}")

    # Fraud
    fraud = loan_file.get("fraud_flags") or []
    if fraud:
        parts.append(f"\nFraud flags: {len(fraud)}")
        for f in fraud:
            parts.append(f"  [{f.get('severity', '?')}] {f.get('description', '?')}")
    else:
        parts.append("\nFraud: No flags detected")

    # Risk
    risk = loan_file.get("risk_score")
    if risk and isinstance(risk, dict):
        prob = risk.get("approval_probability")
        prob_str = f"{prob:.0%}" if prob is not None else "N/A (Insufficient Data)"
        parts.append(f"\nApproval probability: {prob_str}")
        factors = risk.get("factors") or []
        if factors:
            top = sorted(factors, key=lambda x: abs(x.get("contribution", 0)), reverse=True)[:3]
            parts.append("Top risk factors:")
            for f in top:
                sign = "+" if f.get("contribution", 0) >= 0 else ""
                parts.append(f"  {f.get('feature', '?')}: {sign}{f.get('contribution', 0):.3f}")

    # Compliance
    compliance = loan_file.get("compliance")
    if compliance and isinstance(compliance, dict):
        status = "Passed" if compliance.get("bias_check_passed") else "FAILED"
        parts.append(f"\nCompliance: {status}")

    # Recommendation
    rec_map = {
        "approve": "Proceed to approval.",
        "reject": "Recommend rejection — see findings above.",
        "request_more_info": "Proceed to human review — additional information needed.",
    }
    parts.append(f"\nRecommendation: {rec_map.get(recommendation, 'Proceed to human review.')}")

    # Collect citations from extracted fields
    citations = []
    seen = set()
    for f in fields:
        src = f.get("source", {})
        if isinstance(src, dict) and "doc_id" in src and "page" in src:
            key = (src["doc_id"], src["page"])
            if key not in seen:
                seen.add(key)
                citations.append({"doc_id": src["doc_id"], "page": src["page"]})

    return {
        "narrative": "\n".join(parts),
        "recommendation": recommendation,
        "citations": citations,
    }


@retry_with_backoff(max_retries=2, base_delay=1.0)
def _call_llm(system_prompt: str, user_prompt: str) -> str:
    """Call the shared Grok client and return raw response text."""
    from shared.llm_client import active_model, get_llm_client

    client = get_llm_client()
    response = client.chat.completions.create(
        model=active_model,
        messages=[
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_prompt},
        ],
        temperature=0.1,
        max_tokens=4096,
    )
    content = response.choices[0].message.content
    if not content:
        raise ValueError("LLM returned empty content")
    return content


def generate_summary(
    loan_file: dict[str, Any],
    recommendation_override: str | None = None,
) -> dict[str, Any]:
    """Generate a summary_report for the loan_file.

    Tries the LLM first; falls back to deterministic summary on failure.

    Parameters
    ----------
    loan_file : dict
        Fully populated loan_file.
    recommendation_override : str, optional
        If provided, forces this recommendation regardless of LLM output.

    Returns
    -------
    dict
        Schema-compliant ``summaryReport``:
        ``{"narrative": str, "recommendation": str, "citations": list}``.
    """
    # Get decision agent's recommendation for the deterministic fallback.
    from orchestrator.agents.decision import evaluate_decision

    decision = evaluate_decision(loan_file)
    rec = recommendation_override or decision.get("recommendation", "request_more_info")

    # Try LLM-powered summary
    try:
        user_prompt = _build_user_prompt(loan_file)
        raw = _call_llm(_SYSTEM_PROMPT, user_prompt)
        parsed = _parse_summary_response(raw)

        if parsed:
            # Override recommendation if the decision agent says differently
            if recommendation_override:
                parsed["recommendation"] = recommendation_override
            logger.info("LLM summary generated successfully")
            return parsed
        else:
            logger.warning("LLM response could not be parsed — using deterministic fallback")

    except Exception as exc:
        logger.warning("LLM summary failed (%s) — using deterministic fallback", exc)

    # Deterministic fallback
    return _build_deterministic_summary(loan_file, rec)
