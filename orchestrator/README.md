# orchestrator — Person 5

Owns: pipeline orchestrator (state machine), summarization agent, RAG Q&A agent, human review dashboard.

Reads/writes the full `loan_file` object. The only folder allowed to change `status`.

## Checklist
- [ ] Build the state machine (LangGraph/CrewAI) that calls ingestion → extraction → validation → risk in sequence, updating `status` at each stage
- [ ] Summarization agent: compile `summary_report.narrative` + `recommendation` from the full file, with `citations[]` pointing back to source docs
- [ ] RAG Q&A agent: let a reviewer ask "why was this flagged?" against the assembled `loan_file`
- [ ] Review dashboard: document viewer + summary side by side, approve/reject/request-more-docs buttons that write `reviewer_decision`
- [ ] Wire in the other 4 repos/folders as they land PRs — this is the integration point, merge last
- [ ] End-to-end smoke test: run a synthetic doc from `/ingestion` all the way to a reviewer decision

## Test against
Run the whole pipeline against `/schema/loan_file.example.json` as a golden test before the final demo.
