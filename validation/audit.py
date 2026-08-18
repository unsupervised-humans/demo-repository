"""Structured JSON-line audit logging for the validation module.

Matches the shared ``audit_log[]`` contract (agent, action, timestamp) and
adds count fields the schema allows as extra properties.

Never log raw document content, PII field values, or environment variable
names/values (including XAI_API_KEY).
"""

from __future__ import annotations

import json
import logging
from datetime import datetime, timezone
from typing import Any

logger = logging.getLogger("validation.audit")

AGENT_NAME = "validation"
_FORBIDDEN_TOKENS = ("XAI_API_KEY", "GROQ_API_KEY", "API_KEY", "api_key")

_AUDIT_LINES: list[str] = []


def _now() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def _sanitize(value: Any) -> Any:
    if isinstance(value, str):
        lowered = value
        for token in _FORBIDDEN_TOKENS:
            lowered = lowered.replace(token, "[redacted]")
        return lowered
    if isinstance(value, dict):
        return {k: _sanitize(v) for k, v in value.items() if k not in _FORBIDDEN_TOKENS}
    if isinstance(value, list):
        return [_sanitize(v) for v in value]
    return value


def _emit(record: dict[str, Any]) -> dict[str, Any]:
    clean = _sanitize(record)
    line = json.dumps(clean, separators=(",", ":"), ensure_ascii=True)
    for token in _FORBIDDEN_TOKENS:
        if token in line:
            line = line.replace(token, "[redacted]")
    logger.info(line)
    _AUDIT_LINES.append(line)
    return json.loads(line)


def get_audit_lines() -> list[str]:
    """Return in-memory JSON lines (used by tests)."""
    return list(_AUDIT_LINES)


def clear_audit_lines() -> None:
    _AUDIT_LINES.clear()


def log_validation_run(
    status: str,
    findings_count: int,
    fraud_flags_count: int,
    missing_documents_count: int,
) -> dict[str, Any]:
    """Record a successful (or completed) validation pass. No PII."""
    timestamp = _now()
    payload = {
        "event": "validation_completed",
        "status": status,
        "findings_count": findings_count,
        "fraud_flags_count": fraud_flags_count,
        "missing_documents_count": missing_documents_count,
        "agent": AGENT_NAME,
        "action": (
            f"ran cross-document checks findings={findings_count} "
            f"fraud_flags={fraud_flags_count} missing_documents={missing_documents_count}"
        ),
        "timestamp": timestamp,
    }
    return _emit(payload)


def log_failure(stage: str, error: str) -> dict[str, Any]:
    """Record a pipeline failure. ``error`` should be a class name or short code, not PII."""
    timestamp = _now()
    safe_error = _sanitize(str(error))[:200]
    payload = {
        "event": "validation_failed",
        "status": "failure",
        "stage": str(stage),
        "error": safe_error,
        "agent": AGENT_NAME,
        "action": f"failed at {stage}",
        "timestamp": timestamp,
    }
    return _emit(payload)
