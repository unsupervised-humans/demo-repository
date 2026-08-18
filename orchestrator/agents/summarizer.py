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
You are a loan application summarization agent for LoanIQ.
Your job is to produce a clear, structured review summary for a human reviewer.

RULES:
1. Separate your output into these sections: FACTS, FINDINGS, MODEL OUTPUT, RECOMMENDATION.
2. Every claim must come from the structured data provided — never invent facts.
3. The recommendation is an AI suggestion, NOT a guaranteed approval decision.
4. Be concise but include all material information.
5. Reference source documents by doc_id and page where available.
6. If information is missing or uncertain, say so explicitly.

Respond with ONLY a valid JSON object (no markdown fences) with these keys:
{
  "narrative": "<the full summary text>",
  "recommendation": "<approve | reject | request_more_info>",
  "citations": [{"doc_id": "<id>", "page": <number>}, ...]
}
"""


def _build_user_prompt(loan_file: dict[str, Any]) -> str:
    """Build the user-facing prompt from structured loan_file data."""
    parts: list[str] = ["Summarize this loan application:\n"]

    # Applicant
    applicant = loan_file.get("applicant") or {}
    if applicant:
        parts.append(f"APPLICANT: {json.dumps(applicant)}")

    # Documents
    docs = loan_file.get("documents") or []
    parts.append(f"DOCUMENTS ({len(docs)} total): {json.dumps(docs)}")

    # Extracted fields
    fields = loan_file.get("extracted_fields") or []
    parts.append(f"EXTRACTED FIELDS ({len(fields)} total): {json.dumps(fields)}")

    # Validation
    findings = loan_file.get("validation_findings") or []
    parts.append(f"VALIDATION FINDINGS: {json.dumps(findings)}")

    # Missing docs
    missing = loan_file.get("missing_documents") or []
    parts.append(f"MISSING DOCUMENTS: {json.dumps(missing)}")

    # Fraud
    fraud = loan_file.get("fraud_flags") or []
    parts.append(f"FRAUD FLAGS: {json.dumps(fraud)}")

    # Risk
    risk = loan_file.get("risk_score")
    parts.append(f"RISK SCORE: {json.dumps(risk)}")

    # Compliance
    compliance = loan_file.get("compliance")
    parts.append(f"COMPLIANCE: {json.dumps(compliance)}")

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
        prob = risk.get("approval_probability", 0)
        parts.append(f"\nApproval probability: {prob:.0%}")
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
        max_tokens=2048,
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
