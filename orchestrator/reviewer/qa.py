"""Reviewer Q&A Agent (#10) — answers reviewer questions with grounded evidence.

Uses the shared Grok client to produce answers, with strict grounding rules:
- Never invent evidence.
- Always cite source documents (doc_id, page).
- Say "I cannot determine this" when evidence is missing.
"""

from __future__ import annotations

import json
import logging
from typing import Any

from orchestrator.error_handling import retry_with_backoff
from orchestrator.reviewer.retrieval import get_source_references, retrieve_context

logger = logging.getLogger(__name__)


_SYSTEM_PROMPT = """\
You are a loan review assistant for LoanIQ. A human reviewer is asking
questions about a specific loan application.

RULES — follow these strictly:
1. Answer ONLY based on the structured data provided in the context.
2. NEVER invent, assume, or hallucinate facts not present in the data.
3. Always cite source documents by doc_id and page number when available.
4. If the data does not contain enough information to answer, respond with:
   "I cannot determine this from the available documents."
5. Keep answers concise, factual, and directly responsive to the question.
6. Distinguish between extracted facts, validation findings, and model outputs.

Respond with a valid JSON object (no markdown fences):
{
  "answer": "<your grounded answer>",
  "sources": [{"doc_id": "<id>", "page": <number>}, ...],
  "confidence": "<high | medium | low>"
}
"""


def _extract_json_dict(text: str) -> dict[str, Any] | None:
    """Extract and parse a JSON dictionary from arbitrary LLM response text."""
    text = text.strip()

    if "<think>" in text:
        if "</think>" in text:
            text = text.split("</think>", 1)[1].strip()
        else:
            idx = text.find("{")
            if idx != -1:
                text = text[idx:]

    try:
        data = json.loads(text)
        if isinstance(data, dict):
            return data
    except json.JSONDecodeError:
        pass

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


def _parse_qa_response(raw: str) -> dict[str, Any] | None:
    """Parse the LLM's JSON response."""
    data = _extract_json_dict(raw)
    if not data:
        logger.warning("Failed to parse Q&A response: %s", raw[:200])
        return None

    answer = data.get("answer", "")
    sources = data.get("sources", [])
    confidence = data.get("confidence", "low")

    # Normalize sources
    clean_sources = []
    for s in sources if isinstance(sources, list) else []:
        if isinstance(s, dict) and "doc_id" in s:
            clean_sources.append({
                "doc_id": s["doc_id"],
                "page": s.get("page", 1),
            })

    return {
        "answer": answer or "I cannot determine this from the available documents.",
        "sources": clean_sources,
        "confidence": confidence if confidence in ("high", "medium", "low") else "low",
    }


@retry_with_backoff(max_retries=2, base_delay=1.0)
def _call_llm(system_prompt: str, user_prompt: str) -> str:
    """Call the shared Grok client."""
    from shared.llm_client import active_model, get_llm_client

    client = get_llm_client()
    response = client.chat.completions.create(
        model=active_model,
        messages=[
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_prompt},
        ],
        temperature=0,
        max_tokens=4096,
    )
    content = response.choices[0].message.content
    if not content:
        raise ValueError("LLM returned empty content")
    return content


def ask_question(
    loan_file: dict[str, Any],
    question: str,
) -> dict[str, Any]:
    """Answer a reviewer's question about a loan application.

    Parameters
    ----------
    loan_file : dict
        The full loan_file state.
    question : str
        The reviewer's natural-language question.

    Returns
    -------
    dict
        ``{"answer": str, "sources": list[sourceRef], "confidence": str}``
    """
    if not question or not question.strip():
        return {
            "answer": "Please provide a question.",
            "sources": [],
            "confidence": "low",
        }

    # Retrieve relevant context
    context = retrieve_context(loan_file, question)
    source_refs = get_source_references(loan_file, question)

    user_prompt = (
        f"QUESTION: {question}\n\n"
        f"APPLICATION CONTEXT:\n{context}\n\n"
        f"AVAILABLE SOURCE REFERENCES:\n{json.dumps(source_refs, indent=2)}"
    )

    # Try LLM
    try:
        raw = _call_llm(_SYSTEM_PROMPT, user_prompt)
        parsed = _parse_qa_response(raw)
        if parsed:
            logger.info("Q&A answered via LLM (confidence=%s)", parsed["confidence"])
            return parsed
        else:
            logger.warning("LLM Q&A response could not be parsed — using fallback")
    except Exception as exc:
        logger.warning("LLM Q&A call failed (%s) — using fallback", exc)

    # Fallback: return the raw context as the answer
    return {
        "answer": (
            f"Based on the available data:\n\n{context}\n\n"
            "Please review the source documents for more details."
        ),
        "sources": [{"doc_id": r["doc_id"], "page": r["page"]} for r in source_refs],
        "confidence": "low",
    }
