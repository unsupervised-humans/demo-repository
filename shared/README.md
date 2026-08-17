# shared — Austin

Common code every agent depends on, so nobody copy-pastes the same helper five times.

## What goes here
- **`schema_loader.py`** — one function every folder imports to load and validate a `loan_file` against `/schema/loan_file.schema.json`. Nobody hand-rolls their own JSON loading.
- Shared LLM client wrapper (model name, API key handling, retry logic) if agents are calling the same underlying model
- Shared logging helper so every agent writes `audit_log` entries in the same format
- Any prompt templates reused across more than one agent

## Rule
If two or more folders need the same piece of code, it belongs here — not duplicated in each folder. If only one folder needs it, it stays in that folder, not here.

## Ownership
Austin owns this folder because it's also the integration point — anything here affects every other agent, so changes should be flagged in the team chat before merging, same as `/schema`.
