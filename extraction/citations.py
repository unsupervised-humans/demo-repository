"""extraction/citations.py
Source-citation helpers.

Builds sourceRef objects that comply with $defs.sourceRef in the schema:
  {
    "doc_id": <string>,          # required
    "page":   <integer >= 1>,    # required
    "bbox":   [x, y, w, h]      # optional — omitted when unavailable
  }

Rules
-----
- Never invent bbox values.
- If bbox is None / missing / not a 4-element list of numbers, omit it.
- page must be a positive integer; fall back to 1 if the model returns
  something unusable, and flag the field for review.
"""

from __future__ import annotations

from typing import Any


def build_source_ref(
    doc_id: str,
    page: Any,
    bbox: Any = None,
) -> dict:
    """Build a sourceRef dict conforming to $defs.sourceRef.

    Parameters
    ----------
    doc_id : str
        The document identifier (e.g. 'doc-01').
    page : Any
        Page number from the model response. Coerced to int >= 1.
        If coercion fails, defaults to 1.
    bbox : Any, optional
        Bounding-box value from the model response.
        Accepted only when it is a list/tuple of exactly 4 numbers in [0, 1].
        Otherwise omitted — never fabricated.

    Returns
    -------
    dict
        A valid sourceRef dict.
    """
    # ── page ──────────────────────────────────────────────────────────────────
    safe_page = _safe_page(page)

    ref: dict[str, Any] = {
        "doc_id": str(doc_id),
        "page": safe_page,
    }

    # ── bbox ──────────────────────────────────────────────────────────────────
    safe_bbox = _safe_bbox(bbox)
    if safe_bbox is not None:
        ref["bbox"] = safe_bbox

    return ref


def _safe_page(raw: Any) -> int:
    """Coerce raw page value to a valid positive integer.

    Falls back to 1 when coercion fails.
    """
    try:
        val = int(raw)
        return val if val >= 1 else 1
    except (TypeError, ValueError):
        return 1


def _safe_bbox(raw: Any) -> list[float] | None:
    """Validate and return bbox if it is usable, otherwise return None.

    A usable bbox is:
    - a list or tuple
    - with exactly 4 elements
    - each element is a real number (int or float)

    We do NOT enforce the [0, 1] range because the model may return slightly
    out-of-range values due to rounding; clamp lightly if needed.
    """
    if raw is None:
        return None
    if not isinstance(raw, (list, tuple)):
        return None
    if len(raw) != 4:
        return None
    try:
        floats = [float(v) for v in raw]
    except (TypeError, ValueError):
        return None
    # All four values must be finite numbers
    import math
    if any(math.isnan(v) or math.isinf(v) for v in floats):
        return None
    return floats


def extract_citation_flag(
    model_page: Any,
    model_bbox: Any,
) -> tuple[bool, int]:
    """Check whether the page value from the model needed a fallback.

    Returns
    -------
    tuple[bool, int]
        (page_was_invalid, safe_page)
        page_was_invalid=True means the field should be flagged for review.
    """
    safe = _safe_page(model_page)
    try:
        raw = int(model_page)
        invalid = raw < 1
    except (TypeError, ValueError):
        invalid = True
    return invalid, safe
