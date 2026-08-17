# loanIQ

Multi-agent loan document processing agent — Christ (Deemed to be University) hackathon, `unsupervised-humans` org.

Banks receive large volumes of loan-related documents (payslips, bank statements, tax returns, KYC). This pipeline extracts key fields, flags missing/inconsistent documents, scores risk, checks fairness, and hands a human reviewer a decision-ready summary with citations back to the source page.

## Structure

One monorepo, one folder per owner. Everyone builds against the shared `loan_file` contract in `/schema` so work can run in parallel without blocking on anyone else's code.

| Folder | Owner | Agents |
|---|---|---|
| `/ingestion` | Harris | document classifier, synthetic document generator |
| `/extraction` | Austin | field extraction agent (OCR + LLM, confidence + citations) |
| `/validation` | Alina | cross-document validation, missing-document, fraud detection |
| `/risk` | Rohit | risk scoring model (Kaggle dataset), compliance & fairness agent |
| `/orchestrator` | Christy | pipeline orchestrator, summarization agent, RAG Q&A, review dashboard |
| `/schema` | shared | `loan_file.schema.json` (the contract), `loan_file.example.json` (test fixture) |
| `/shared` | Austin | code more than one agent depends on (schema loader, shared LLM client, logging) |
| `/.github` | Austin | CI workflow that validates the schema on every PR |

See `CODEOWNERS` — GitHub auto-requests the right person's review based on which folder a PR touches.

## The contract

Every agent reads and writes a shared `loan_file` object, defined in [`schema/loan_file.schema.json`](schema/loan_file.schema.json). Validate your agent's output against it before opening a PR — that catches most integration bugs before merge day. Use [`schema/loan_file.example.json`](schema/loan_file.example.json) as a fixture to build against even before the upstream agent is ready.

Rules:
- Only the orchestrator (`/orchestrator`) writes `status`.
- `audit_log` is append-only — every agent adds one entry when it runs.
- Never rename or remove a field another agent depends on without raising it in the group chat first.
- Validate your agent's output with `shared/schema_loader.py` before opening a PR — CI runs the same check automatically and will fail your PR if the example fixture doesn't validate.

## Branching

- `main` is protected — no direct pushes, PRs only.
- Work in `feature/<your-folder>-<short-description>`, e.g. `feature/extraction-payslip-parser`.
- Open the PR against `main` as soon as your agent runs against `loan_file.example.json`, even if incomplete — small PRs merge faster than one big one at the deadline.
- Person 5 merges last for the orchestrator, since it depends on every other agent's interface.

## Getting started

```bash
git clone https://github.com/unsupervised-humans/loanIQ.git
cd loanIQ
git checkout -b feature/<your-folder>-<short-description>
```

Each folder has its own README with that person's task checklist.
