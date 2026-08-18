"""
LoanIQ Agent Health-Check Script
=================================
Tests every agent in the pipeline by posting the example JSON loan_file
directly to the running API server.  No PDF upload required.

Usage
-----
    python scripts/test_agents.py                  # default: http://localhost:8000
    python scripts/test_agents.py --url http://localhost:8000
    python scripts/test_agents.py --verbose        # dump full response bodies

What it tests
-------------
1. GET  /api/health                 → server alive?
2. POST /api/pipeline/run           → full pipeline (all 7 agents)
   - Stage results reported individually
3. GET  /api/pipeline/{id}/status   → status query
4. GET  /api/pipeline/{id}/result   → full result retrieval
5. POST /api/review/{id}/question   → QA agent (reviewer Q&A)
6. POST /api/review/{id}/decision   → reviewer decision agent
7. Edge cases: unknown app_id, empty documents
"""

from __future__ import annotations

import argparse
import json
import sys
import textwrap
import time
from typing import Any

try:
    import requests
except ImportError:
    sys.exit("❌  'requests' not installed.  Run: pip install requests")

# ── ANSI colours (Windows-safe when using colorama) ──────────────────────────
try:
    import colorama
    colorama.init()
    GREEN  = "\033[92m"
    RED    = "\033[91m"
    YELLOW = "\033[93m"
    CYAN   = "\033[96m"
    BOLD   = "\033[1m"
    RESET  = "\033[0m"
except ImportError:
    GREEN = RED = YELLOW = CYAN = BOLD = RESET = ""

# ── Example loan_file (mirrors schema/loan_file.example.json) ─────────────────

EXAMPLE_LOAN_FILE: dict[str, Any] = {
    "application_id": f"TEST-{int(time.time())}",
    "created_at": "2026-08-18T12:00:00Z",
    "status": "ingested",
    "applicant": {
        "name": "Priya Sharma",
        "declared_income": 72000,
        "loan_amount_requested": 400000,
        "loan_type": "personal",
    },
    "documents": [
        {
            "doc_id": "doc-01",
            "file_path": "uploads/doc-01.pdf",
            "type": "payslip",
            "classification_confidence": 0.98,
            "page_count": 1,
            "is_synthetic": True,
        },
        {
            "doc_id": "doc-02",
            "file_path": "uploads/doc-02.pdf",
            "type": "bank_statement",
            "classification_confidence": 0.95,
            "page_count": 3,
            "is_synthetic": True,
        },
        {
            "doc_id": "doc-03",
            "file_path": "uploads/doc-03.pdf",
            "type": "kyc_id",
            "classification_confidence": 0.99,
            "page_count": 1,
            "is_synthetic": True,
        },
    ],
    "extracted_fields": [
        {
            "field_name": "employer_name",
            "value": "TechCorp Solutions",
            "confidence": 0.97,
            "source": {"doc_id": "doc-01", "page": 1},
            "needs_review": False,
        },
        {
            "field_name": "gross_monthly_income",
            "value": 72000,
            "confidence": 0.96,
            "source": {"doc_id": "doc-01", "page": 1},
            "needs_review": False,
        },
        {
            "field_name": "avg_monthly_deposit",
            "value": 69000,
            "confidence": 0.91,
            "source": {"doc_id": "doc-02", "page": 2},
            "needs_review": False,
        },
        {
            "field_name": "applicant_name",
            "value": "Priya Sharma",
            "confidence": 0.99,
            "source": {"doc_id": "doc-03", "page": 1},
            "needs_review": False,
        },
        {
            "field_name": "id_expiry_date",
            "value": "2030-06-15",
            "confidence": 0.60,
            "source": {"doc_id": "doc-03", "page": 1},
            "needs_review": True,
        },
    ],
    "validation_findings": [],
    "missing_documents": [],
    "fraud_flags": [],
    "risk_score": None,
    "compliance": None,
    "summary_report": None,
    "reviewer_decision": None,
    "audit_log": [],
}

# ── Helpers ───────────────────────────────────────────────────────────────────

Results: list[dict[str, Any]] = []


def _status(ok: bool) -> str:
    return f"{GREEN}PASS{RESET}" if ok else f"{RED}FAIL{RESET}"


def _header(title: str) -> None:
    print(f"\n{BOLD}{CYAN}{'=' * 60}{RESET}")
    print(f"{BOLD}{CYAN}  {title}{RESET}")
    print(f"{BOLD}{CYAN}{'=' * 60}{RESET}")


def _check(
    label: str,
    ok: bool,
    detail: str = "",
    verbose_body: Any = None,
    verbose: bool = False,
) -> None:
    Results.append({"label": label, "ok": ok, "detail": detail})
    icon = _status(ok)
    print(f"  [{icon}]  {label}")
    if detail:
        print(f"          {YELLOW}{detail}{RESET}")
    if verbose and verbose_body is not None:
        body_str = json.dumps(verbose_body, indent=2, default=str)
        lines = body_str.splitlines()
        for line in lines[:40]:
            print(f"          {line}")
        if len(lines) > 40:
            print(f"          ... ({len(lines) - 40} more lines)")


def _post(url: str, payload: dict, timeout: int = 120) -> "requests.Response":
    return requests.post(url, json=payload, timeout=timeout)


def _get(url: str, timeout: int = 15) -> "requests.Response":
    return requests.get(url, timeout=timeout)


# ── Test suites ───────────────────────────────────────────────────────────────

def test_health(base: str, verbose: bool, timeout: int = 15) -> None:
    _header("1 . Health Check")
    try:
        r = _get(f"{base}/api/health", timeout=timeout)
        ok = r.status_code == 200 and r.json().get("status") == "ok"
        _check("GET /api/health returns 200 ok", ok,
               f"HTTP {r.status_code}", r.json(), verbose)
    except Exception as exc:
        _check("GET /api/health", False, str(exc))


def test_pipeline(base: str, verbose: bool, timeout: int = 120) -> str | None:
    """Run the full pipeline; returns app_id on success."""
    _header("2 . Full Pipeline Run  (ingestion -> extraction -> validation -> risk -> compliance -> decision -> summary)")

    app_id: str | None = None
    try:
        t0 = time.time()
        r = _post(f"{base}/api/pipeline/run", {"loan_file": EXAMPLE_LOAN_FILE}, timeout=timeout)
        elapsed = round((time.time() - t0) * 1000)
        ok = r.status_code == 200
        body = r.json() if ok else {}

        _check(
            f"POST /api/pipeline/run -> {r.status_code}",
            ok,
            f"elapsed={elapsed}ms",
            body,
            verbose,
        )

        if not ok:
            print(f"  {RED}Response: {r.text[:300]}{RESET}")
            return None

        app_id       = body.get("application_id")
        status       = body.get("status", "?")
        needs_review = body.get("needs_review", False)
        review_reasons = body.get("review_reasons", [])
        summary      = body.get("summary") or {}

        _check("application_id present", bool(app_id), app_id or "MISSING")
        _check("status field is set",    bool(status), f"status={status}")
        _check("needs_review is boolean", isinstance(needs_review, bool),
               f"needs_review={needs_review}")

        if review_reasons:
            print(f"\n  {YELLOW}  Review reasons ({len(review_reasons)}):{RESET}")
            for i, reason in enumerate(review_reasons[:5], 1):
                print(f"     {i}. {reason}")

        if summary:
            rec       = summary.get("recommendation", "?")
            narrative = summary.get("narrative", "")
            print(f"\n  {CYAN}  Recommendation: {BOLD}{rec}{RESET}")
            if narrative:
                short = textwrap.shorten(narrative, width=90, placeholder="...")
                print(f"     {short}")

    except Exception as exc:
        _check("POST /api/pipeline/run", False, str(exc))

    return app_id


def test_per_stage(base: str, app_id: str, verbose: bool, timeout: int = 15) -> None:
    """Fetch full result and validate each pipeline stage."""
    _header("3 . Per-Agent Stage Validation")

    try:
        r = _get(f"{base}/api/pipeline/{app_id}/result", timeout=timeout)
        ok = r.status_code == 200
        if not ok:
            _check("GET /api/pipeline/{id}/result", False, f"HTTP {r.status_code}")
            return

        body = r.json()

        docs = body.get("documents") or []
        _check("Agent: Classifier / Ingestion",
               len(docs) > 0, f"{len(docs)} document(s)")

        fields = body.get("extracted_fields") or []
        _check("Agent: Extraction",
               len(fields) > 0, f"{len(fields)} field(s) extracted")

        findings = body.get("validation_findings")
        _check("Agent: Validation",
               findings is not None, f"{len(findings or [])} finding(s)")

        risk = body.get("risk_score")
        _check("Agent: Risk Scoring",
               risk is not None,
               f"approval_probability={risk.get('approval_probability') if risk else 'N/A'}")

        compliance = body.get("compliance")
        _check("Agent: Compliance",
               compliance is not None,
               f"bias_check_passed={compliance.get('bias_check_passed') if compliance else 'N/A'}")

        summary = body.get("summary_report")
        _check("Agent: Decision + Summarizer",
               summary is not None and "recommendation" in (summary or {}),
               f"recommendation={summary.get('recommendation') if summary else 'N/A'}")

        audit = body.get("audit_log") or []
        _check("Audit log populated", len(audit) >= 3, f"{len(audit)} entries")

        if verbose:
            print(f"\n  {CYAN}  Audit log (last 8 entries):{RESET}")
            for entry in audit[-8:]:
                ts     = entry.get("timestamp", "")
                agent  = entry.get("agent", "system")
                action = entry.get("action", "")
                print(f"     [{ts}] {agent}: {action}")

    except Exception as exc:
        _check("Per-stage validation", False, str(exc))


def test_status_endpoint(base: str, app_id: str, verbose: bool, timeout: int = 15) -> None:
    _header("4 . Status Query")
    try:
        r = _get(f"{base}/api/pipeline/{app_id}/status", timeout=timeout)
        ok = r.status_code == 200
        body = r.json() if ok else {}
        _check(
            f"GET /api/pipeline/{{id}}/status -> {r.status_code}",
            ok,
            f"status={body.get('status', '?')}",
            body,
            verbose,
        )
    except Exception as exc:
        _check("GET /api/pipeline/{id}/status", False, str(exc))


def test_qa_agent(base: str, app_id: str, verbose: bool, timeout: int = 60) -> None:
    _header("5 . Reviewer Q&A Agent")
    questions = [
        "What is the applicant's declared income?",
        "Are there any fraud flags?",
        "Why does this application need review?",
    ]
    for q in questions:
        try:
            r = _post(f"{base}/api/review/{app_id}/question", {"question": q}, timeout=timeout)
            ok = r.status_code == 200
            body = r.json() if ok else {}
            answer = body.get("answer", "")
            short  = textwrap.shorten(answer, width=70, placeholder="...") if answer else "no answer"
            label  = f'Q: "{q[:50]}"' if len(q) > 50 else f'Q: "{q}"'
            _check(label, ok, f"A: {short}", body, verbose)
        except Exception as exc:
            _check(f"QA: {q[:40]}", False, str(exc))


def test_decision_agent(base: str, app_id: str, verbose: bool, timeout: int = 15) -> None:
    _header("6 . Reviewer Decision Submission")
    try:
        payload = {
            "decision": "approved",
            "reviewer": "test-script",
            "notes": "Automated test approval - all agents verified.",
        }
        r = _post(f"{base}/api/review/{app_id}/decision", payload, timeout=timeout)
        ok = r.status_code == 200
        body = r.json() if ok else {}
        _check(
            f"POST /api/review/{{id}}/decision -> {r.status_code}",
            ok,
            f"status={body.get('status', '?')}, decision={body.get('decision', '?')}",
            body,
            verbose,
        )
    except Exception as exc:
        _check("POST /api/review/{id}/decision", False, str(exc))


def test_not_found(base: str, verbose: bool, timeout: int = 15) -> None:
    _header("7 . Error Handling: Unknown app_id")
    try:
        r = _get(f"{base}/api/pipeline/UNKNOWN-APP-XYZ-99999/status", timeout=timeout)
        ok = r.status_code == 404
        _check("Unknown app_id -> 404 Not Found", ok, f"HTTP {r.status_code}")
    except Exception as exc:
        _check("404 error handling", False, str(exc))


def test_empty_documents(base: str, verbose: bool, timeout: int = 30) -> None:
    _header("8 . Edge Case: Empty Documents List")
    try:
        bad_payload = {
            "loan_file": {
                "application_id": "TEST-EMPTY-DOCS",
                "status": "ingested",
                "documents": [],
                "audit_log": [],
            }
        }
        r = _post(f"{base}/api/pipeline/run", bad_payload, timeout=timeout)
        # Expect either HTTP 500 or status=failed — should NOT silently succeed
        if r.status_code == 500:
            _check("Empty documents -> graceful 500 error", True, "HTTP 500")
        elif r.status_code == 200:
            status = r.json().get("status", "?")
            ok = status in ("failed", "error")
            _check("Empty documents -> status=failed", ok, f"status={status}")
        else:
            _check("Empty documents -> error response", False,
                   f"Unexpected HTTP {r.status_code}")
    except Exception as exc:
        _check("Empty documents edge case", False, str(exc))


# ── Summary ───────────────────────────────────────────────────────────────────

def print_summary() -> int:
    _header("SUMMARY")
    passed = sum(1 for r in Results if r["ok"])
    failed = sum(1 for r in Results if not r["ok"])
    total  = len(Results)

    print(f"\n  Total checks : {total}")
    print(f"  {GREEN}Passed       : {passed}{RESET}")
    if failed:
        print(f"  {RED}Failed       : {failed}{RESET}")
        print(f"\n  {RED}Failed checks:{RESET}")
        for r in Results:
            if not r["ok"]:
                print(f"    [FAIL]  {r['label']}")
                if r["detail"]:
                    print(f"            -> {r['detail']}")
    else:
        print(f"\n  {GREEN}{BOLD}All agents are healthy!{RESET}")
    print()
    return failed


# ── Entrypoint ────────────────────────────────────────────────────────────────

def main() -> None:
    parser = argparse.ArgumentParser(description="LoanIQ agent health-check")
    parser.add_argument("--url", default="http://localhost:8000",
                        help="Base URL of the API server (default: http://localhost:8000)")
    parser.add_argument("--verbose", action="store_true",
                        help="Print full JSON response bodies")
    parser.add_argument("--timeout", type=int, default=120,
                        help="Timeout in seconds for the pipeline POST (default: 120)")
    args = parser.parse_args()

    base    = args.url.rstrip("/")
    verbose = args.verbose
    timeout = args.timeout

    print(f"\n{BOLD}LoanIQ Agent Health-Check{RESET}")
    print(f"  Server  : {CYAN}{base}{RESET}")
    print(f"  App ID  : {CYAN}{EXAMPLE_LOAN_FILE['application_id']}{RESET}")
    print(f"  Timeout : {timeout}s (pipeline POST)")
    print(f"  Mode    : {'verbose' if verbose else 'summary'}")

    # Run all test suites
    test_health(base, verbose)
    app_id = test_pipeline(base, verbose, timeout=timeout)

    if app_id:
        test_per_stage(base, app_id, verbose)
        test_status_endpoint(base, app_id, verbose)
        test_qa_agent(base, app_id, verbose, timeout=min(timeout, 60))
        test_decision_agent(base, app_id, verbose)
    else:
        print(f"\n{RED}  Pipeline failed to return an app_id — skipping downstream tests.{RESET}")

    test_not_found(base, verbose)
    test_empty_documents(base, verbose)

    failed = print_summary()
    sys.exit(1 if failed else 0)


if __name__ == "__main__":
    main()
