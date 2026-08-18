# orchestrator — Christy

Owns: pipeline orchestrator (state machine), decision agent, summarization agent, reviewer Q&A agent, human review API.

Reads/writes the full `loan_file` object. The only folder allowed to change `status`.

---

## Architecture

```text
                    ┌─────────────────────┐
                    │ CHRISTY             │
                    │ ORCHESTRATOR        │
                    └──────────┬──────────┘
                               │
             ┌─────────────────┼─────────────────┐
             ▼                 ▼                 ▼
          Harris            Austin             Alina
       Classification      Extraction       Validation/Fraud
             │                 │                 │
             └─────────────────┼─────────────────┘
                               ▼
                             Rohit
                         Risk/Compliance
                               │
                               ▼
                    ┌─────────────────────┐
                    │ Christy Summary     │
                    │ + Reviewer Q&A      │
                    └──────────┬──────────┘
                               ▼
                         Human Reviewer
```

## Pipeline Stages

```text
START → Ingestion → Extraction → Validation → Risk → Compliance → Decision → Summary → Review Gate → END
```

| Stage | Node Adapter | Upstream Module | Status |
|-------|-------------|-----------------|--------|
| Ingestion | `nodes/ingestion.py` | `ingestion/` (Harris) | ✅ |
| Extraction | `nodes/extraction.py` | `extraction/` (Austin) | ✅ |
| Validation | `nodes/validation.py` | `validation/` (Alina) | ✅ |
| Risk | `nodes/risk.py` | `risk/predict.py` (Rohit) | ✅ |
| Compliance | `nodes/compliance.py` | `risk/compliance.py` (Rohit) | ✅ |
| Decision | `agents/decision.py` | Internal | ✅ |
| Summary | `agents/summarizer.py` | Grok LLM + fallback | ✅ |
| Reviewer Q&A | `reviewer/qa.py` | Grok LLM + fallback | ✅ |

## Usage

### Run pipeline on pre-ingested data

```python
from orchestrator import run_pipeline, ask_reviewer_question

result = run_pipeline(loan_file)

# Ask reviewer questions
answer = ask_reviewer_question(result, "Why was this flagged?")
```

### Run pipeline from raw files

```python
from orchestrator import run_from_files

result = run_from_files("path/to/uploads", application_id="APP-2026-001")
```

### REST API

```bash
uvicorn orchestrator.api:app --reload --port 8000
```

Endpoints:
- `POST /api/pipeline/run` — Run the full pipeline
- `GET  /api/pipeline/{app_id}/status` — Check application status
- `GET  /api/pipeline/{app_id}/result` — Get full loan_file result
- `POST /api/review/{app_id}/question` — Ask a reviewer question
- `POST /api/review/{app_id}/decision` — Submit human review decision
- `GET  /api/health` — Health check

## Project Structure

```text
orchestrator/
├── __init__.py          # Public API exports
├── graph.py             # Pipeline executor (state machine)
├── state.py             # Workflow states, init, review triggers
├── audit.py             # Audit trail helpers
├── error_handling.py    # Retry, backoff, custom exceptions
├── api.py               # FastAPI REST endpoints
├── nodes/
│   ├── ingestion.py     # Harris adapter
│   ├── extraction.py    # Austin adapter
│   ├── validation.py    # Alina adapter
│   ├── risk.py          # Rohit risk adapter
│   ├── compliance.py    # Rohit compliance adapter
│   └── summary.py       # Summary node adapter
├── agents/
│   ├── decision.py      # Decision/Policy agent
│   └── summarizer.py    # LLM summarization + fallback
├── reviewer/
│   ├── qa.py            # Reviewer Q&A agent
│   └── retrieval.py     # Structured retrieval from loan_file
└── tests/
    ├── test_graph.py
    ├── test_state.py
    ├── test_decision.py
    ├── test_failure_handling.py
    ├── test_reviewer_qa.py
    └── test_e2e.py
```

## Testing

```bash
python -m pytest orchestrator/tests -v
```

Test against the golden fixture:
```text
/schema/loan_file.example.json
```

## Checklist
- [x] Build state machine that calls ingestion → extraction → validation → risk → compliance in sequence
- [x] Decision agent: holistic policy evaluation across all pipeline outputs
- [x] Summarization agent: compile `summary_report` with `citations[]` pointing to source docs
- [x] RAG Q&A agent: let reviewer ask "why was this flagged?" against the assembled `loan_file`
- [x] REST API: pipeline run, status, result, Q&A, and decision endpoints
- [x] Error handling: retry with backoff, stage isolation, failure recording
- [x] Audit trail: workflow lifecycle logging with secret sanitization
- [x] Human review gate: automatic routing based on 7 trigger conditions
- [x] End-to-end tests with golden fixture
