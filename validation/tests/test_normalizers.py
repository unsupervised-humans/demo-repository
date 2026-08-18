"""Normalizer unit tests."""

import pytest

from validation.normalizers import (
    normalize_address,
    normalize_date,
    normalize_name,
    string_similarity,
)


def test_normalize_name_strips_titles_keeps_middle_token():
    assert normalize_name("Mr. John Abraham") == "john abraham"
    left = normalize_name("John A. Thomas")
    right = normalize_name("John Abraham")
    assert left != right
    assert "thomas" in left
    assert "a" in left.split()


def test_normalize_address_aliases_and_abbreviations():
    a = normalize_address("12 MG Road, Bengaluru")
    b = normalize_address("12, Mahatma Gandhi Road, Bangalore")
    assert a == b
    assert "mahatma gandhi" in a
    assert "bangalore" in a


def test_normalize_date_multiple_formats():
    assert normalize_date("2026-04-01").isoformat() == "2026-04-01"
    assert normalize_date("01/04/2026").isoformat() == "2026-04-01"
    assert normalize_date("01 Apr 2026").isoformat() == "2026-04-01"


def test_normalize_date_unparseable_raises():
    with pytest.raises(ValueError, match="Unparseable date"):
        normalize_date("not-a-date")


def test_string_similarity_bounds():
    assert string_similarity("abc", "abc") == 1.0
    assert 0.0 <= string_similarity("abc", "xyz") <= 1.0
