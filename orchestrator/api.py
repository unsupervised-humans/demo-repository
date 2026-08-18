"""FastAPI backend for the LoanIQ orchestrator.

Exposes REST endpoints so the React review dashboard (and any other
client) can trigger the pipeline, check status, ask reviewer questions,
and submit decisions.

Usage
-----
::

    uvicorn orchestrator.api:app --reload --port 8000

Endpoints are documented at ``/docs`` (Swagger UI).
"""

from __future__ import annotations

import json
import logging
import shutil
import tempfile
from pathlib import Path
from typing import Any

try:
    from fastapi import FastAPI, File, HTTPException, UploadFile
    from fastapi.middleware.cors import CORSMiddleware
    from fastapi.responses import FileResponse, RedirectResponse
    from fastapi.staticfiles import StaticFiles
    from pydantic import BaseModel, Field
except ImportError as exc:
    raise ImportError(
        "FastAPI and pydantic are required for the API server:\n"
        "  pip install fastapi uvicorn pydantic"
    ) from exc

from orchestrator.graph import run_pipeline
from orchestrator.reviewer.qa import ask_question
from orchestrator.state import initialize_loan_file

logger = logging.getLogger(__name__)

# ── App setup ─────────────────────────────────────────────────────────────────

app = FastAPI(
    title="LoanIQ Orchestrator API",
    description="REST API for the LoanIQ loan processing pipeline, "
    "reviewer Q&A, and human review decisions.",
    version="1.0.0",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # tighten in production
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# ── Static dashboard ──────────────────────────────────────────────────────────
# Serve index.html (and any other static assets) from the project root.
_ROOT = Path(__file__).parent.parent
app.mount("/dashboard", StaticFiles(directory=str(_ROOT), html=True), name="static")

# In-memory store (replace with DB in production)
_loan_files: dict[str, dict[str, Any]] = {}


# ── Request / Response models ─────────────────────────────────────────────────


class RunPipelineRequest(BaseModel):
    """Run the pipeline on a pre-ingested loan_file."""

    loan_file: dict[str, Any] = Field(
        ..., description="A loan_file dict conforming to the shared schema."
    )


class QuestionRequest(BaseModel):
    """Ask a reviewer question about an application."""

    question: str = Field(..., min_length=1, description="The reviewer's question.")


class ReviewDecisionRequest(BaseModel):
    """Submit a human reviewer's decision."""

    decision: str = Field(
        ..., description='One of: "approved", "rejected", "more_docs_requested"'
    )
    reviewer: str = Field(..., description="Name/ID of the human reviewer.")
    notes: str = Field("", description="Optional reviewer notes.")


class PipelineResponse(BaseModel):
    """Response from the pipeline run."""

    application_id: str
    status: str
    needs_review: bool
    review_reasons: list[str]
    summary: dict[str, Any] | None = None


class QAResponse(BaseModel):
    """Response from the Q&A endpoint."""

    answer: str
    sources: list[dict[str, Any]]
    confidence: str


# ── Endpoints ─────────────────────────────────────────────────────────────────


@app.get("/", include_in_schema=False)
async def root():
    """Redirect root to the test dashboard."""
    return RedirectResponse(url="/dashboard")


@app.post("/api/pipeline/run", response_model=PipelineResponse)
async def api_run_pipeline(request: RunPipelineRequest) -> dict[str, Any]:
    """Run the full LoanIQ pipeline on a loan_file."""
    loan_file = request.loan_file

    # Ensure required fields
    if "application_id" not in loan_file:
        lf = initialize_loan_file()
        loan_file["application_id"] = lf["application_id"]
        loan_file["created_at"] = lf["created_at"]

    loan_file.setdefault("status", "ingested")
    loan_file.setdefault("audit_log", [])

    try:
        result = run_pipeline(loan_file)
    except Exception as exc:
        logger.error("Pipeline failed: %s", exc, exc_info=True)
        raise HTTPException(status_code=500, detail=str(exc))

    app_id = result["application_id"]
    _loan_files[app_id] = result

    return {
        "application_id": app_id,
        "status": result.get("status", "failed"),
        "needs_review": bool(result.get("_review_reasons")),
        "review_reasons": result.get("_review_reasons", []),
        "summary": result.get("summary_report"),
    }


def _lookup_loan_file(app_id: str) -> dict[str, Any]:
    """Look up a loan_file by app_id, tolerating trailing dots or whitespace."""
    clean_id = app_id.strip().rstrip(".")
    if clean_id in _loan_files:
        return _loan_files[clean_id]
    if app_id in _loan_files:
        return _loan_files[app_id]
    raise HTTPException(status_code=404, detail=f"Application '{app_id}' not found")


def _build_pipeline_response(app_id: str, result: dict[str, Any]) -> dict[str, Any]:
    return {
        "application_id": app_id,
        "status": result.get("status", "failed"),
        "needs_review": bool(result.get("_review_reasons")),
        "review_reasons": result.get("_review_reasons", []),
        "summary": result.get("summary_report"),
    }


@app.post("/api/pipeline/upload", response_model=PipelineResponse)
async def api_upload_pipeline(
    files: list[UploadFile] = File(...),
    applicant_name: str = "",
    loan_amount: float = 0.0,
    loan_type: str = "personal",
) -> dict[str, Any]:
    """Run the full pipeline from uploaded PDF/image files.

    Accepts one or more documents (payslip, bank statement, KYC ID,
    employment letter, etc.). The LLM classifier will auto-detect each
    document type — no manual labelling required.
    """
    from orchestrator.graph import run_from_files
    from orchestrator.state import initialize_loan_file

    if not files:
        raise HTTPException(status_code=400, detail="No files uploaded.")

    # Save uploads to a temp folder so run_from_files() can read them
    tmp_dir = tempfile.mkdtemp(prefix="loaniq_upload_")
    try:
        for upload in files:
            dest = Path(tmp_dir) / (upload.filename or "document.pdf")
            content = await upload.read()
            dest.write_bytes(content)

        # Build a minimal loan_file shell with applicant info if provided
        loan_file = initialize_loan_file()
        if applicant_name or loan_amount:
            loan_file["applicant"] = {
                "name": applicant_name or "Unknown",
                "declared_income": 0,
                "loan_amount_requested": loan_amount,
                "loan_type": loan_type or "personal",
            }

        # run_from_files: ingestion (classify) → extraction → validation → risk → …
        result = run_from_files(tmp_dir, application_id=loan_file["application_id"])
    except HTTPException:
        raise
    except Exception as exc:
        logger.error("Upload pipeline failed: %s", exc, exc_info=True)
        raise HTTPException(status_code=500, detail=str(exc))
    finally:
        shutil.rmtree(tmp_dir, ignore_errors=True)

    # Merge applicant info back if the pipeline didn't set it
    if applicant_name and not result.get("applicant", {}).get("name"):
        result.setdefault("applicant", {})["name"] = applicant_name

    app_id = result["application_id"]
    _loan_files[app_id] = result

    return _build_pipeline_response(app_id, result)


@app.get("/api/loans")
async def api_list_loans() -> dict[str, Any]:
    """List all processed loan applications (in-memory, current session)."""
    loans = []
    for app_id, lf in _loan_files.items():
        summary = lf.get("summary_report") or {}
        risk = lf.get("risk_score") or {}
        loans.append({
            "application_id": app_id,
            "applicant_name": (lf.get("applicant") or {}).get("name", "Unknown"),
            "status": lf.get("status", "unknown"),
            "needs_review": bool(lf.get("_review_reasons")),
            "recommendation": summary.get("recommendation", "—"),
            "approval_probability": risk.get("approval_probability"),
            "created_at": lf.get("created_at", ""),
            "doc_count": len(lf.get("documents") or []),
        })
    # Most recent first
    loans.sort(key=lambda x: x["created_at"], reverse=True)
    return {"loans": loans, "total": len(loans)}




@app.get("/api/pipeline/{app_id}/status")
async def api_get_status(app_id: str) -> dict[str, Any]:
    """Get the current status of a loan application."""
    lf = _lookup_loan_file(app_id)
    return {
        "application_id": lf.get("application_id", app_id),
        "status": lf.get("status", "unknown"),
        "needs_review": bool(lf.get("_review_reasons")),
    }


@app.get("/api/pipeline/{app_id}/result")
async def api_get_result(app_id: str) -> dict[str, Any]:
    """Get the full loan_file result."""
    lf = dict(_lookup_loan_file(app_id))
    lf.pop("_pipeline_results", None)
    lf.pop("_review_reasons", None)
    return lf


@app.post("/api/review/{app_id}/question", response_model=QAResponse)
async def api_ask_question(app_id: str, request: QuestionRequest) -> dict[str, Any]:
    """Ask a question about a loan application."""
    lf = _lookup_loan_file(app_id)
    result = ask_question(lf, request.question)
    return result


@app.post("/api/review/{app_id}/decision")
async def api_submit_decision(
    app_id: str, request: ReviewDecisionRequest,
) -> dict[str, Any]:
    """Submit a human reviewer's decision."""
    lf = _lookup_loan_file(app_id)
    valid_decisions = {"approved", "rejected", "more_docs_requested"}
    if request.decision not in valid_decisions:
        raise HTTPException(
            status_code=400,
            detail=f"Invalid decision. Must be one of: {valid_decisions}",
        )

    from datetime import datetime, timezone

    lf = _loan_files[app_id]
    lf["reviewer_decision"] = {
        "decision": request.decision,
        "reviewer": request.reviewer,
        "decided_at": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "notes": request.notes,
    }

    # Update status based on decision
    status_map = {
        "approved": "approved",
        "rejected": "rejected",
        "more_docs_requested": "more_docs_requested",
    }
    lf["status"] = status_map[request.decision]

    # Audit
    from orchestrator.audit import append_audit
    append_audit(
        lf,
        f"human review completed: {request.decision} by {request.reviewer}",
        agent="reviewer",
    )

    return {
        "application_id": app_id,
        "status": lf["status"],
        "decision": request.decision,
    }


@app.get("/api/health")
async def health_check() -> dict[str, str]:
    """Health check endpoint."""
    return {"status": "ok", "service": "loaniq-orchestrator"}
