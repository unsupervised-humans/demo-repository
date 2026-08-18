"""Pipeline executor — pure-Python state machine for the LoanIQ workflow.

Runs the loan-processing pipeline in sequence:

    Ingestion → Extraction → Validation → Risk/Compliance → Decision → Summary → Review Gate

Each stage is isolated: a failure in one stage is caught, recorded, and the
pipeline decides whether to continue or stop based on explicit policy.

Usage
-----
::

    from orchestrator.graph import run_pipeline, run_from_files

    # Pre-ingested loan_file (e.g. from the example fixture)
    result = run_pipeline(loan_file)

    # From raw document files
    result = run_from_files("path/to/uploads", application_id="APP-2026-001")
"""

from __future__ import annotations

import logging
import time
from typing import Any

from orchestrator.audit import append_audit
from orchestrator.error_handling import (
    NoCriticalDataError,
    PipelineError,
    StageResult,
    StageStatus,
)
from orchestrator.state import (
    WorkflowStatus,
    initialize_loan_file,
    requires_human_review,
    set_status,
)

logger = logging.getLogger(__name__)


# ── Stage definitions ────────────────────────────────────────────────────────

def _run_stage(
    name: str,
    fn: Any,
    loan_file: dict[str, Any],
    workflow_status: WorkflowStatus,
    *,
    critical: bool = False,
) -> StageResult:
    """Execute a single pipeline stage with error isolation.

    Parameters
    ----------
    name : str
        Human-readable stage name.
    fn : callable
        Stage function: ``fn(loan_file) -> loan_file``.
    loan_file : dict
        Shared state (mutated in place).
    workflow_status : WorkflowStatus
        The status to set before running.
    critical : bool
        If True, a failure in this stage stops the pipeline.

    Returns
    -------
    StageResult
    """
    set_status(loan_file, workflow_status)
    start = time.time()

    try:
        fn(loan_file)
        duration = (time.time() - start) * 1000
        return StageResult(
            stage_name=name,
            status=StageStatus.SUCCESS,
            duration_ms=duration,
        )
    except NoCriticalDataError as exc:
        duration = (time.time() - start) * 1000
        append_audit(loan_file, f"{name} failed (critical): {exc}")
        logger.error("Stage %s failed (critical): %s", name, exc)
        return StageResult(
            stage_name=name,
            status=StageStatus.FAILED,
            error=str(exc),
            duration_ms=duration,
        )
    except Exception as exc:
        duration = (time.time() - start) * 1000
        append_audit(loan_file, f"{name} failed: {exc}")
        logger.error("Stage %s failed: %s", name, exc, exc_info=True)
        status = StageStatus.FAILED if critical else StageStatus.PARTIAL_FAILURE
        return StageResult(
            stage_name=name,
            status=status,
            error=str(exc),
            duration_ms=duration,
        )


def run_pipeline(
    loan_file: dict[str, Any],
    *,
    skip_ingestion: bool = True,
) -> dict[str, Any]:
    """Run the full LoanIQ pipeline on a loan_file.

    Parameters
    ----------
    loan_file : dict
        The shared state object.  For pre-ingested data (e.g. the example
        fixture), ``documents[]`` should already be populated.
    skip_ingestion : bool
        If True (default), assumes documents are already present and
        runs a passthrough validation instead of calling Harris's pipeline.

    Returns
    -------
    dict
        The final loan_file with all agent outputs, summary, and status.
        Also includes ``_pipeline_results`` with per-stage details.
    """
    results: list[StageResult] = []

    append_audit(loan_file, "workflow started")

    # ── Stage 1: Ingestion ────────────────────────────────────────────────────
    if skip_ingestion:
        from orchestrator.nodes.ingestion import run_ingestion_passthrough
        result = _run_stage(
            "ingestion", run_ingestion_passthrough, loan_file,
            WorkflowStatus.CLASSIFYING, critical=True,
        )
    else:
        # When called via run_from_files, ingestion is handled before this
        result = StageResult(
            stage_name="ingestion", status=StageStatus.SKIPPED,
        )

    results.append(result)
    if result.status == StageStatus.FAILED:
        set_status(loan_file, WorkflowStatus.FAILED)
        append_audit(loan_file, "workflow stopped: no documents")
        loan_file["_pipeline_results"] = [r.__dict__ for r in results]
        return loan_file

    # ── Stage 2: Extraction ───────────────────────────────────────────────────
    from orchestrator.nodes.extraction import run_extraction
    result = _run_stage(
        "extraction", run_extraction, loan_file,
        WorkflowStatus.EXTRACTING, critical=False,
    )
    results.append(result)

    # Extraction failure is non-critical if some fields exist
    if result.status == StageStatus.FAILED:
        fields = loan_file.get("extracted_fields") or []
        if not fields:
            set_status(loan_file, WorkflowStatus.FAILED)
            append_audit(loan_file, "workflow stopped: extraction produced no fields")
            loan_file["_pipeline_results"] = [r.__dict__ for r in results]
            return loan_file

    # ── Stage 3: Validation ───────────────────────────────────────────────────
    from orchestrator.nodes.validation import run_validation
    result = _run_stage(
        "validation", run_validation, loan_file,
        WorkflowStatus.VALIDATING, critical=False,
    )
    results.append(result)
    # Validation failure is non-critical — continue with review flag

    # ── Stage 4: Risk Assessment ──────────────────────────────────────────────
    from orchestrator.nodes.risk import run_risk_assessment
    result = _run_stage(
        "risk_assessment", run_risk_assessment, loan_file,
        WorkflowStatus.RISK_ASSESSMENT, critical=False,
    )
    results.append(result)
    # Risk failure is non-critical — summary will note missing risk score

    # ── Stage 5: Compliance ───────────────────────────────────────────────────
    from orchestrator.nodes.compliance import run_compliance_check
    result = _run_stage(
        "compliance", run_compliance_check, loan_file,
        WorkflowStatus.COMPLIANCE, critical=False,
    )
    results.append(result)
    # Compliance failure is non-critical — forces human review

    # ── Stage 6: Decision ─────────────────────────────────────────────────────
    from orchestrator.agents.decision import evaluate_decision

    set_status(loan_file, WorkflowStatus.DECIDING)
    start = time.time()
    try:
        decision = evaluate_decision(loan_file)
        duration = (time.time() - start) * 1000
        append_audit(
            loan_file,
            f"decision: {decision['recommendation']} "
            f"(needs_review={decision['needs_review']}, "
            f"reasons={len(decision['reasons'])})",
        )
        results.append(StageResult(
            stage_name="decision",
            status=StageStatus.SUCCESS,
            duration_ms=duration,
            details=decision,
        ))
    except Exception as exc:
        duration = (time.time() - start) * 1000
        logger.error("Decision agent failed: %s", exc)
        append_audit(loan_file, f"decision failed: {exc}")
        decision = {
            "recommendation": "request_more_info",
            "needs_review": True,
            "reasons": [f"Decision agent error: {exc}"],
        }
        results.append(StageResult(
            stage_name="decision",
            status=StageStatus.PARTIAL_FAILURE,
            error=str(exc),
            duration_ms=duration,
        ))

    # ── Stage 6: Summary ──────────────────────────────────────────────────────
    from orchestrator.nodes.summary import run_summary
    result = _run_stage(
        "summary", run_summary, loan_file,
        WorkflowStatus.SUMMARIZING, critical=False,
    )
    results.append(result)

    # ── Stage 7: Human Review Gate ────────────────────────────────────────────
    needs_review, review_reasons = requires_human_review(loan_file)

    # Also check decision agent's verdict
    if decision.get("needs_review"):
        needs_review = True
        reasons_list = decision.get("reasons")
        if isinstance(reasons_list, list):
            for reason in reasons_list:
                if reason not in review_reasons:
                    review_reasons.append(reason)


    # Check for any stage failures
    failed_stages = [r.stage_name for r in results if r.status in (StageStatus.FAILED, StageStatus.PARTIAL_FAILURE)]
    if failed_stages:
        needs_review = True
        review_reasons.append(f"Pipeline stage failures: {', '.join(failed_stages)}")

    if needs_review:
        set_status(loan_file, WorkflowStatus.REVIEW_REQUIRED)
        append_audit(
            loan_file,
            f"marked for human review ({len(review_reasons)} reason(s)): "
            + "; ".join(review_reasons[:5]),
        )
    else:
        # Map decision recommendation to schema status
        rec = decision.get("recommendation", "request_more_info")
        if rec == "approve":
            loan_file["status"] = "approved"
        elif rec == "reject":
            loan_file["status"] = "rejected"
        else:
            loan_file["status"] = "ready_for_review"

    append_audit(
        loan_file,
        f"workflow completed — final status: {loan_file['status']}",
    )

    # Attach pipeline metadata (not part of schema, for debugging)
    loan_file["_pipeline_results"] = [r.__dict__ for r in results]
    loan_file["_review_reasons"] = review_reasons

    return loan_file


def run_from_files(
    folder_path: str,
    application_id: str | None = None,
) -> dict[str, Any]:
    """Run the full pipeline starting from raw document files.

    Parameters
    ----------
    folder_path : str
        Path to folder containing applicant's uploaded documents.
    application_id : str, optional
        Unique ID for this application.

    Returns
    -------
    dict
        Completed loan_file.
    """
    loan_file = initialize_loan_file(application_id)

    # Run Harris's ingestion
    from orchestrator.nodes.ingestion import run_ingestion_from_folder

    try:
        run_ingestion_from_folder(loan_file, folder_path)
    except NoCriticalDataError:
        set_status(loan_file, WorkflowStatus.FAILED)
        append_audit(loan_file, "workflow stopped: no documents in folder")
        return loan_file

    # Run the rest of the pipeline
    return run_pipeline(loan_file, skip_ingestion=True)
