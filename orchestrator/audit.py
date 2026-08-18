"""Audit trail helpers for the orchestrator.

Every agent appends entries to loan_file['audit_log'].
This module provides a consistent interface so the orchestrator
never accidentally logs secrets or produces malformed entries.

Format per schema/$defs/auditEntry:
    {"agent": str, "action": str, "timestamp": ISO-8601}
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

# Strings that must NEVER appear in audit log values.
_REDACT_PREFIXES = ("gsk_", "sk-", "xai-", "Bearer ")

ORCHESTRATOR_AGENT = "orchestrator"


def _now_iso() -> str:
    """Return current UTC time as ISO-8601 string."""
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def _sanitize(text: str) -> str:
    """Strip anything that looks like an API key or token."""
    for prefix in _REDACT_PREFIXES:
        if prefix in text:
            text = text.replace(text[text.index(prefix):], "[REDACTED]")
    return text


def append_audit(
    loan_file: dict[str, Any],
    action: str,
    agent: str = ORCHESTRATOR_AGENT,
) -> None:
    """Append a single audit entry to *loan_file['audit_log']*.

    Parameters
    ----------
    loan_file : dict
        The shared loan_file state object.
    action : str
        Human-readable description of what happened.
    agent : str
        Agent identifier (default: ``"orchestrator"``).
    """
    loan_file.setdefault("audit_log", [])
    loan_file["audit_log"].append(
        {
            "agent": _sanitize(agent),
            "action": _sanitize(action),
            "timestamp": _now_iso(),
        }
    )
