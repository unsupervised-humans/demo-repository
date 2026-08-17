"""extraction/tests/test_confidence.py
Unit tests for extraction.confidence.

Covers:
- Confidence clamping (below 0, above 1, within range)
- needs_review threshold (exact boundary + above/below)
- apply_confidence combined helper
"""

import pytest
from extraction.confidence import (
    REVIEW_THRESHOLD,
    apply_confidence,
    clamp_confidence,
    needs_review,
)


class TestClampConfidence:
    def test_clamp_below_zero(self):
        assert clamp_confidence(-0.5) == 0.0

    def test_clamp_above_one(self):
        assert clamp_confidence(1.5) == 1.0

    def test_clamp_at_zero(self):
        assert clamp_confidence(0.0) == 0.0

    def test_clamp_at_one(self):
        assert clamp_confidence(1.0) == 1.0

    def test_clamp_within_range(self):
        assert clamp_confidence(0.75) == pytest.approx(0.75)

    def test_clamp_negative_large(self):
        assert clamp_confidence(-99) == 0.0

    def test_clamp_string_float(self):
        # float() coercion
        assert clamp_confidence("0.5") == pytest.approx(0.5)  # type: ignore[arg-type]


class TestNeedsReview:
    def test_below_threshold(self):
        assert needs_review(REVIEW_THRESHOLD - 0.01) is True

    def test_exactly_at_threshold(self):
        # confidence == REVIEW_THRESHOLD → does NOT need review
        assert needs_review(REVIEW_THRESHOLD) is False

    def test_above_threshold(self):
        assert needs_review(REVIEW_THRESHOLD + 0.01) is False

    def test_zero_confidence(self):
        assert needs_review(0.0) is True

    def test_full_confidence(self):
        assert needs_review(1.0) is False

    def test_threshold_value_is_0_70(self):
        """Ensure the threshold constant matches the spec."""
        assert REVIEW_THRESHOLD == pytest.approx(0.70)


class TestApplyConfidence:
    def test_low_confidence_returns_review_true(self):
        conf, review = apply_confidence(0.50)
        assert conf == pytest.approx(0.50)
        assert review is True

    def test_high_confidence_returns_review_false(self):
        conf, review = apply_confidence(0.95)
        assert conf == pytest.approx(0.95)
        assert review is False

    def test_clamped_negative(self):
        conf, review = apply_confidence(-1.0)
        assert conf == 0.0
        assert review is True

    def test_clamped_above_one(self):
        conf, review = apply_confidence(2.0)
        assert conf == 1.0
        assert review is False

    def test_exactly_at_threshold(self):
        conf, review = apply_confidence(0.70)
        assert conf == pytest.approx(0.70)
        assert review is False
