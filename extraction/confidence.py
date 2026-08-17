"""extraction/confidence.py
Confidence handling for extracted fields.

Rules (from schema + Austin's spec):
  - confidence is clamped to [0, 1]
  - REVIEW_THRESHOLD = 0.70
  - needs_review = True  when confidence < REVIEW_THRESHOLD
  - needs_review = False when confidence >= REVIEW_THRESHOLD
"""

REVIEW_THRESHOLD: float = 0.70


def clamp_confidence(raw: float) -> float:
    """Clamp confidence to the valid [0, 1] range.

    Parameters
    ----------
    raw : float
        Unclamped confidence from the model.

    Returns
    -------
    float
        Value guaranteed to be in [0, 1].
    """
    return max(0.0, min(1.0, float(raw)))


def needs_review(confidence: float) -> bool:
    """Return True when the field should be queued for human review.

    Parameters
    ----------
    confidence : float
        Already-clamped confidence value.

    Returns
    -------
    bool
        True  → confidence < REVIEW_THRESHOLD
        False → confidence >= REVIEW_THRESHOLD
    """
    return confidence < REVIEW_THRESHOLD


def apply_confidence(raw: float) -> tuple[float, bool]:
    """Clamp and compute review flag in one call.

    Parameters
    ----------
    raw : float
        Raw confidence value from the model response.

    Returns
    -------
    tuple[float, bool]
        (clamped_confidence, needs_review_flag)
    """
    clamped = clamp_confidence(raw)
    return clamped, needs_review(clamped)
