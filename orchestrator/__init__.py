"""orchestrator — Christy's pipeline orchestration, decision, and reviewer layer.

Public API
----------
::

    from orchestrator import run_pipeline, run_from_files, ask_reviewer_question

    # Run on pre-ingested loan_file
    result = run_pipeline(loan_file)

    # Run from raw document files
    result = run_from_files("path/to/uploads")

    # Reviewer Q&A
    answer = ask_reviewer_question(loan_file, "Why was this flagged?")
"""

from orchestrator.agents.decision import evaluate_decision
from orchestrator.graph import run_from_files, run_pipeline
from orchestrator.reviewer.qa import ask_question as ask_reviewer_question
from orchestrator.state import initialize_loan_file, requires_human_review

__all__ = [
    "run_pipeline",
    "run_from_files",
    "ask_reviewer_question",
    "evaluate_decision",
    "initialize_loan_file",
    "requires_human_review",
]
