"""extraction/__init__.py
Public API for Austin's extraction module.

Christy's orchestrator (and anyone else) imports like:
    from extraction import extract_fields
"""

from extraction.extractor import extract_fields

__all__ = ["extract_fields"]
