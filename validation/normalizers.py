"""String / date normalizers used before any cross-document comparison."""

from __future__ import annotations

import re
from datetime import date, datetime
from difflib import SequenceMatcher

_TITLES = frozenset(
    {
        "mr",
        "mrs",
        "ms",
        "miss",
        "dr",
        "prof",
        "sir",
        "smt",
        "shri",
        "sri",
        "md",
        "mx",
    }
)

# Small extensible city-alias map. Keys and values are lowercase.
CITY_ALIASES: dict[str, str] = {
    "bengaluru": "bangalore",
    "bangalore": "bangalore",
    "bombay": "mumbai",
    "mumbai": "mumbai",
    "calcutta": "kolkata",
    "kolkata": "kolkata",
    "madras": "chennai",
    "chennai": "chennai",
    "poona": "pune",
    "pune": "pune",
    "cochin": "kochi",
    "kochi": "kochi",
    "gurgaon": "gurugram",
    "gurugram": "gurugram",
    "trivandrum": "thiruvananthapuram",
    "thiruvananthapuram": "thiruvananthapuram",
}

_ADDRESS_ABBREVIATIONS: list[tuple[re.Pattern[str], str]] = [
    (re.compile(r"\bmg\b"), "mahatma gandhi"),
    (re.compile(r"\brd\b"), "road"),
    (re.compile(r"\bst\b"), "street"),
    (re.compile(r"\bave\b"), "avenue"),
    (re.compile(r"\bblvd\b"), "boulevard"),
    (re.compile(r"\bln\b"), "lane"),
    (re.compile(r"\bdr\b"), "drive"),
    (re.compile(r"\bapt\b"), "apartment"),
    (re.compile(r"\bno\b"), "number"),
    (re.compile(r"\bnr\b"), "near"),
    (re.compile(r"\bopp\b"), "opposite"),
    (re.compile(r"\bsec\b"), "sector"),
    (re.compile(r"\bnagar\b"), "nagar"),
]

_DATE_FORMATS = (
    "%Y-%m-%d",
    "%Y/%m/%d",
    "%d-%m-%Y",
    "%d/%m/%Y",
    "%d.%m.%Y",
    "%m/%d/%Y",
    "%d-%b-%Y",
    "%d %b %Y",
    "%d %B %Y",
    "%b %d, %Y",
    "%B %d, %Y",
    "%Y-%m-%dT%H:%M:%S",
    "%Y-%m-%dT%H:%M:%SZ",
    "%Y-%m-%dT%H:%M:%S%z",
)


def _collapse_ws(text: str) -> str:
    return re.sub(r"\s+", " ", text).strip()


def normalize_name(name: str) -> str:
    """Lowercase, strip titles, collapse whitespace.

    Middle initials and extra given/family names are preserved so
    "John A. Thomas" is not silently treated as equal to "John Abraham".
    """
    if name is None:
        raise ValueError("name is required")
    tokens = re.sub(r"[,]+", " ", str(name)).replace(".", " ").lower()
    tokens = _collapse_ws(tokens)
    kept = [t for t in tokens.split(" ") if t and t not in _TITLES]
    return " ".join(kept)


def normalize_address(address: str) -> str:
    """Lowercase, expand abbreviations, apply city aliases, strip punctuation."""
    if address is None:
        raise ValueError("address is required")
    text = str(address).lower()
    text = text.replace("&", " and ")
    text = re.sub(r"[#,.;:()/\\-]+", " ", text)
    text = _collapse_ws(text)
    for pattern, replacement in _ADDRESS_ABBREVIATIONS:
        text = pattern.sub(replacement, text)
    words = []
    for word in text.split(" "):
        words.append(CITY_ALIASES.get(word, word))
    return _collapse_ws(" ".join(words))


def normalize_date(date_str: str) -> date:
    """Parse multiple common date formats. Raise ValueError on unparseable input."""
    if date_str is None:
        raise ValueError("date_str is required")
    if isinstance(date_str, datetime):
        return date_str.date()
    if isinstance(date_str, date):
        return date_str

    raw = str(date_str).strip()
    if not raw:
        raise ValueError("date_str is empty")

    if raw.endswith("Z") and "T" in raw:
        try:
            return datetime.fromisoformat(raw.replace("Z", "+00:00")).date()
        except ValueError:
            pass

    try:
        return datetime.fromisoformat(raw).date()
    except ValueError:
        pass

    for fmt in _DATE_FORMATS:
        try:
            return datetime.strptime(raw, fmt).date()
        except ValueError:
            continue

    raise ValueError(f"Unparseable date: {date_str!r}")


def string_similarity(a: str, b: str) -> float:
    """Return a 0.0–1.0 similarity score using stdlib difflib (no extra dependency)."""
    left = "" if a is None else str(a)
    right = "" if b is None else str(b)
    if not left and not right:
        return 1.0
    return SequenceMatcher(None, left, right).ratio()
