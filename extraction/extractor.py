"""extraction/extractor.py
Austin's extraction entry point.

Public API
----------
    from extraction import extract_fields

    updated_loan_file = extract_fields(loan_file)

    # Or, passing just a documents list (useful for unit tests):
    fields = extract_fields({"documents": [...]})[\"extracted_fields\"]

Pipeline per document
---------------------
    document
    -> determine usable text or image
    -> OCR fallback if necessary
    -> Grok multimodal extraction (text or image+text message)
    -> parse structured JSON from model response
    -> normalize fields (confidence clamp, needs_review flag, sourceRef)
    -> append to extracted_fields[]
    -> append audit_log entry

Failure handling
----------------
A single failed document never crashes the whole loan file.
For unextractable fields: value=null, confidence=0.0, needs_review=True.

Schema compliance
-----------------
Output conforms to $defs.extractedField and $defs.auditEntry in
schema/loan_file.schema.json. Validated by shared.schema_loader if
VALIDATE_OUTPUT env var is set to '1'.
"""

from __future__ import annotations

import base64
import json
import logging
import os
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from extraction.citations import build_source_ref, extract_citation_flag
from extraction.confidence import apply_confidence
from extraction.ocr_fallback import (
    encode_image_base64,
    extract_text,
    get_image_mime_type,
)
from extraction.prompts import SYSTEM_PROMPT, get_prompt

try:
    from shared.llm_client import active_model, get_llm_client
except ImportError:
    # shared.llm_client is optional at import time; failure is reported at call time.
    get_llm_client = None  # type: ignore[assignment]
    active_model = "openai/gpt-oss-20b"

logger = logging.getLogger(__name__)

# -- Constants -----------------------------------------------------------------
AGENT_NAME = "extraction"
API_TIMEOUT = int(os.environ.get("EXTRACTION_API_TIMEOUT", "60"))  # seconds

_IMAGE_SUFFIXES = {".pdf", ".png", ".jpg", ".jpeg", ".tiff", ".tif", ".bmp", ".webp"}


# -- Main entry point ----------------------------------------------------------

def extract_fields(loan_file: dict) -> dict:
    """Run extraction over all documents in *loan_file*.

    Parameters
    ----------
    loan_file : dict
        A loan_file dict conforming to the shared schema.  Must contain a
        ``documents`` key.  The function mutates and returns the same dict
        with ``extracted_fields`` and ``audit_log`` extended.

    Returns
    -------
    dict
        The updated loan_file dict (same object, mutated in place).
    """
    loan_file.setdefault("extracted_fields", [])
    loan_file.setdefault("audit_log", [])

    documents: list[dict] = loan_file.get("documents", [])

    if not documents:
        logger.warning("extract_fields: no documents to process")
        _append_audit(loan_file, "no documents to process - skipped extraction")
        return loan_file

    _append_audit(loan_file, f"extraction started for {len(documents)} document(s)")

    total_extracted = 0
    for doc in documents:
        try:
            fields = _extract_document(doc)
            loan_file["extracted_fields"].extend(fields)
            total_extracted += len(fields)
            _append_audit(
                loan_file,
                f"extracted {len(fields)} field(s) from {doc.get('doc_id', '?')} "
                f"(type={doc.get('type') or doc.get('document_type', '?')})",
            )
        except Exception as exc:  # noqa: BLE001
            doc_id = doc.get("doc_id", "?")
            logger.error("Extraction failed for document %s: %s", doc_id, exc, exc_info=True)
            _append_audit(loan_file, f"extraction failed for {doc_id}: {exc}")

    _append_audit(loan_file, f"extraction complete - {total_extracted} field(s) extracted")
    return loan_file


# -- Per-document extraction ---------------------------------------------------

def _extract_document(doc: dict) -> list[dict]:
    """Extract fields from a single document dict.

    Returns a list of extractedField dicts (may be empty on failure).
    """
    doc_id: str = doc.get("doc_id", "unknown")
    doc_type: str = doc.get("type") or doc.get("document_type") or "other"
    file_path: str = doc.get("file_path", "")
    # For combined_loan_package: list of section types inside the file
    detected_sections: list[str] = doc.get("detected_sections") or []

    logger.info("Extracting document %s (type=%s)", doc_id, doc_type)

    # Build the LLM message content
    user_prompt = get_prompt(doc_type, doc_id, detected_sections=detected_sections or None)
    messages = _build_messages(user_prompt, file_path, doc_id)

    # Call the model
    raw_json = _call_model(messages, doc_id)
    if raw_json is None:
        return _failure_field(doc_id, doc_type, reason="model returned no content")

    # Parse model JSON
    model_fields = _parse_model_json(raw_json, doc_id)
    if model_fields is None:
        # JSON parse failure: return empty list instead of failure sentinel.
        # Sentinels contaminate extracted_fields with fake fields that
        # downstream checks (missing-doc detection, risk scoring) cannot
        # distinguish from real but unreadable fields.
        logger.warning(
            "JSON parse failed for %s (type=%s) - returning empty extraction",
            doc_id, doc_type,
        )
        return []

    # Normalize each field
    extracted: list[dict] = []
    for item in model_fields:
        ef = _normalize_field(item, doc_id)
        if ef is not None:
            extracted.append(ef)

    return extracted


# -- Message building (text vs multimodal) -------------------------------------

def _build_messages(user_prompt: str, file_path: str, doc_id: str) -> list[dict]:
    """Construct the chat messages list for the Grok API call.

    Strategy (in priority order):
    1. OCR text from file_path (PyMuPDF/pdfminer for PDFs, pytesseract for images).
    2. Base64-encode the file bytes and send as multimodal image_url.
       Works for both PDFs (application/pdf) and images.
    3. Text-only prompt (no file content available) -- last resort.
    """
    system_msg = {"role": "system", "content": SYSTEM_PROMPT}

    path = Path(file_path) if file_path else None
    path_exists = path is not None and path.exists()

    # Attempt OCR text extraction from disk
    ocr_text: str | None = None
    if path_exists:
        ocr_text = extract_text(path)

    if ocr_text:
        # Embed the extracted text directly in the prompt
        user_content = (
            f"{user_prompt}\n\n"
            f"--- DOCUMENT TEXT (doc_id={doc_id!r}) ---\n{ocr_text}\n---"
        )
        return [system_msg, {"role": "user", "content": user_content}]

    # Attempt base64 file encoding (PDF or image)
    raw_bytes: bytes | None = None
    if path_exists:
        try:
            raw_bytes = path.read_bytes()
        except OSError as exc:
            logger.warning("Could not read file %s: %s", file_path, exc)

    if raw_bytes is not None:
        suffix = path.suffix.lower() if path else ".pdf"
        mime = get_image_mime_type(path) if path else "application/pdf"
        if suffix != ".pdf":
            b64 = base64.b64encode(raw_bytes).decode("ascii")
            user_content = [
                {"type": "text", "text": user_prompt},
                {
                    "type": "image_url",
                    "image_url": {"url": f"data:{mime};base64,{b64}"},
                },
            ]
            return [system_msg, {"role": "user", "content": user_content}]

    # Text-only fallback (no file / no deps)
    logger.warning(
        "Document %s: no file content available; sending text-only prompt", doc_id
    )
    return [system_msg, {"role": "user", "content": user_prompt}]


# -- Model call ----------------------------------------------------------------

def _call_model(messages: Any, doc_id: str) -> str | None:
    """Call Grok and return the raw response string, or None on error."""
    if get_llm_client is None:
        logger.error("shared.llm_client could not be imported; skipping model call for %s", doc_id)
        return None

    try:
        client = get_llm_client()
    except EnvironmentError as exc:
        logger.error("LLM client init failed for %s: %s", doc_id, exc)
        return None

    model = active_model

    try:
        logger.debug("Calling model %s for doc %s", model, doc_id)
        response = client.chat.completions.create(
            model=model,
            messages=messages,
            temperature=0,          # deterministic extraction
            timeout=API_TIMEOUT,
            max_tokens=4096,
        )
        content = response.choices[0].message.content
        if not content:
            logger.warning("Model returned empty content for doc %s", doc_id)
            return None
        return content
    except Exception as exc:  # noqa: BLE001
        logger.error("Model API call failed for %s: %s", doc_id, exc, exc_info=True)
        return None


# -- JSON parsing --------------------------------------------------------------

def _parse_model_json(raw: str, doc_id: str) -> list[dict] | None:
    """Parse the model's JSON response into a list of raw field dicts.

    Tolerates JSON fenced in markdown code blocks and pre-pended reasoning
    chains (e.g. <think>...</think> tags).
    Returns None when parsing fails entirely.
    """
    text = raw.strip()

    # Strip reasoning chain (<think>...</think>) if present
    if "<think>" in text:
        if "</think>" in text:
            text = text.split("</think>", 1)[1].strip()
        else:
            # If thinking is truncated/unclosed, extract from the first '{'
            idx = text.find("{")
            if idx != -1:
                text = text[idx:].strip()

    # Extract content from markdown code block if present
    if "```" in text:
        parts = text.split("```")
        # Find the block that looks like a JSON object/dict
        for part in parts:
            part_clean = part.strip()
            if part_clean.startswith("json\n") or part_clean.startswith("json\r\n"):
                part_clean = part_clean.split("\n", 1)[1].strip()
            elif part_clean.startswith("json "):
                part_clean = part_clean.split(" ", 1)[1].strip()
            elif part_clean.startswith("json"):
                part_clean = part_clean[4:].strip()

            if part_clean.startswith("{") and part_clean.endswith("}"):
                text = part_clean
                break
            elif part_clean.startswith("{"):
                # Loose fallback if end is messy
                text = part_clean
                break

    try:
        data = json.loads(text)
    except json.JSONDecodeError as exc:
        logger.warning("JSON parse failed for doc %s: %s | raw=%r", doc_id, exc, raw[:200])
        return None

    if not isinstance(data, dict):
        logger.warning("Model returned non-dict JSON for doc %s: %r", doc_id, data)
        return None

    fields = data.get("fields")
    if not isinstance(fields, list):
        logger.warning("Model JSON missing 'fields' list for doc %s", doc_id)
        return None

    return fields


# -- Field normalisation -------------------------------------------------------

def _normalize_field(item: Any, doc_id: str) -> dict | None:
    """Convert one raw model-field dict to a schema-compliant extractedField.

    Returns None if *item* is not a usable dict (skip silently).
    """
    if not isinstance(item, dict):
        return None

    field_name = item.get("field_name")
    if not field_name or not isinstance(field_name, str):
        logger.debug("Skipping model field with missing/invalid field_name: %r", item)
        return None

    # Skip extraction failure sentinels from any prior runs
    if str(field_name).startswith("extraction_failure_"):
        logger.debug("Skipping extraction_failure sentinel field: %s", field_name)
        return None

    # -- confidence -----------------------------------------------------------
    raw_confidence = item.get("confidence", 0.0)
    try:
        raw_confidence = float(raw_confidence)
    except (TypeError, ValueError):
        raw_confidence = 0.0

    confidence, review_flag = apply_confidence(raw_confidence)

    # -- value ----------------------------------------------------------------
    value = item.get("value")  # may legitimately be None / null

    # -- source citation -------------------------------------------------------
    raw_page = item.get("page")
    raw_bbox = item.get("bbox")

    page_invalid, _ = extract_citation_flag(raw_page, raw_bbox)
    if page_invalid:
        # Force review when the model couldn't even specify a page
        review_flag = True

    source = build_source_ref(doc_id=doc_id, page=raw_page, bbox=raw_bbox)

    return {
        "field_name": field_name,
        "value": value,
        "confidence": confidence,
        "source": source,
        "needs_review": review_flag,
    }


# -- Graceful failure fields ---------------------------------------------------

def _failure_field(doc_id: str, doc_type: str, reason: str = "") -> list[dict]:
    """Return a single sentinel extractedField for a completely failed document.

    This keeps the schema contract (extracted_fields is never silently empty
    for a document that was attempted) while signalling the failure clearly.
    Only used when the model itself fails to return any content (not for JSON
    parse failures, which return an empty list to avoid contamination).
    """
    logger.warning("Generating failure sentinel for %s (%s): %s", doc_id, doc_type, reason)
    return [
        {
            "field_name": f"extraction_failure_{doc_type}",
            "value": None,
            "confidence": 0.0,
            "source": build_source_ref(doc_id=doc_id, page=1),
            "needs_review": True,
        }
    ]


# -- Audit log -----------------------------------------------------------------

def _append_audit(loan_file: dict, action: str) -> None:
    """Append an auditEntry to loan_file['audit_log'].

    Conforms to $defs.auditEntry:
        { "agent": str, "action": str, "timestamp": ISO-8601 }
    """
    entry = {
        "agent": AGENT_NAME,
        "action": action,
        "timestamp": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
    }
    loan_file["audit_log"].append(entry)
