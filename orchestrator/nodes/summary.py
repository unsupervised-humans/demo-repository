"""Summary node — runs the summarization agent and populates summary_report.

Delegates to ``orchestrator.agents.summarizer`` for the actual LLM-powered
summary generation, with a deterministic fallback.
"""

from __future__ import annotations

import logging
from typing import Any

from orchestrator.audit import append_audit

logger = logging.getLogger(__name__)


def run_summary(loan_file: dict[str, Any]) -> dict[str, Any]:
    """Generate the summary_report for the loan_file.

    Parameters
    ----------
    loan_file : dict
        Fully populated loan_file (post risk/compliance).

    Returns
    -------
    dict
        Updated loan_file with ``summary_report`` populated.
    """
    from orchestrator.agents.summarizer import generate_summary

    append_audit(loan_file, "summary generation started")

    summary_report = generate_summary(loan_file)
    loan_file["summary_report"] = summary_report

    append_audit(
        loan_file,
        f"summary generated: recommendation={summary_report.get('recommendation', '?')}",
    )

    return loan_file
