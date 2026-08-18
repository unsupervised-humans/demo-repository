# LoanIQ — Complete Project Context for a New LLM

## 1. Project Identity

**Project:** LoanIQ  
**Repository:** `unsupervised-humans/loanIQ`  
**Purpose:** Multi-agent AI-powered loan processing and underwriting assistance system.

LoanIQ is a hackathon implementation designed not to simply ask one LLM whether a person should receive a loan. The core idea is to use a pipeline of specialized agents that independently process, validate, cross-check, score, and explain a loan application before presenting an evidence-backed result to a human reviewer.

The system should process:
- Payslips
- Bank statements
- KYC/identity documents
- Tax returns
- Employment proof
- Address proof

It should identify:
- Extracted applicant information
- Missing documents
- Cross-document inconsistencies
- Fraud/anomaly indicators
- Risk score
- Compliance/fairness issues
- Evidence/citations
- Human-review requirements
- Final summarized review packet

---

## 2. Core Architecture

```text
                    LOAN APPLICATION
                           │
                           ▼
                ┌────────────────────┐
                │ Document Ingestion │
                │      Agent         │
                └─────────┬──────────┘
                          │
                          ▼
                ┌────────────────────┐
                │ Document Classifier│
                │       Agent        │
                └─────────┬──────────┘
                          │
                          ▼
                ┌────────────────────┐
                │ Multimodal         │
                │ Extraction Agent   │
                └─────────┬──────────┘
                          │
                    extracted_fields
                          │
                          ▼
             ┌──────────────────────────┐
             │ Validation Agent         │
             │ Missing-Document Agent   │
             │ Fraud/Anomaly Agent      │
             └────────────┬─────────────┘
                          │
                          ▼
             ┌──────────────────────────┐
             │ Risk Scoring Agent       │
             │ Compliance/Fairness Agent│
             └────────────┬─────────────┘
                          │
                          ▼
             ┌──────────────────────────┐
             │ Decision / Policy Agent  │
             └────────────┬─────────────┘
                          │
                          ▼
             ┌──────────────────────────┐
             │ Summarization Agent      │
             │ Reviewer Explanation     │
             └────────────┬─────────────┘
                          │
                          ▼
                    HUMAN REVIEWER
```

---

## 3. Agents

The project uses a **10-agent architecture**.

### Agent 1 — Document Ingestion Agent
**Owner:** Harris

Responsibilities:
- Receive uploaded loan documents.
- Validate file types.
- Prepare documents for downstream processing.
- Handle PDF/document metadata.
- Provide documents to classification/extraction.

Technology:
- Python
- PDF/document processing

### Agent 2 — Document Classification Agent
**Owner:** Harris

Responsibilities:
- Determine what type of document was uploaded.
- Examples: payslip, bank statement, KYC/ID, tax return, address proof, employment proof.
- Should not assume the applicant correctly labels files.
- Should handle unordered/messy document batches.

### Agent 3 — Multimodal Extraction Agent
**Owner:** Austin

Austin's extraction module is already implemented and merged into `main`.

Main files:

```text
extraction/
├── __init__.py
├── extractor.py
├── prompts.py
├── confidence.py
├── citations.py
├── ocr_fallback.py
└── tests/
```

Also:

```text
shared/llm_client.py
```

Purpose:
- Convert unstructured loan documents into structured fields.

Example:

```json
{
  "field_name": "gross_monthly_income",
  "value": 65000,
  "confidence": 0.95,
  "source": {
    "doc_id": "doc-01",
    "page": 1
  },
  "needs_review": false
}
```

Important requirements:
- Every extracted field should have `field_name`, `value`, `confidence`, `source`, and optional `needs_review`.
- Confidence is between `0.0` and `1.0`.
- Current threshold: `confidence < 0.70` → `needs_review = true`.
- Never fabricate bounding boxes.
- If a bounding box is unavailable, omit it.
- Malformed LLM output/API failures should produce a schema-compliant failure sentinel rather than crashing the pipeline.

### Agent 4 — Validation Agent
**Owner:** Alina

Determines whether information extracted from different documents is consistent.

Examples:
- KYC name vs bank statement name vs payslip name.
- Payslip income vs bank deposits vs ITR income.

Mismatches should become explicit findings.

Potential output:
```text
validation_findings[]
```

### Agent 5 — Missing Document Agent

Checks whether all documents required for the specific loan scenario are present.

Example:
```text
✓ KYC
✓ Payslip
✓ Bank statement
✗ Tax return
✗ Address proof
```

Potential output:
```text
missing_documents[]
```

The system should be able to produce a reviewer/applicant-facing missing-document request.

### Agent 6 — Fraud / Anomaly Agent
**Owner:** Alina

Looks for suspicious patterns:
- Inconsistent information
- Numbers that do not reconcile
- Document anomalies
- Metadata anomalies
- Formatting/tampering indicators
- Reused documents
- Potential cross-application patterns

The agent should flag suspicious evidence, not blindly declare someone fraudulent.

### Agent 7 — Risk Scoring Agent
**Owner:** Rohit

Conventional ML component based on the Kaggle loan approval dataset.

Technology:
- scikit-learn
- XGBoost

Flow:
```text
Extracted fields
      +
Validation findings
      +
Fraud indicators
      +
Financial information
      ↓
Feature engineering
      ↓
Risk model
      ↓
Risk / approval probability
```

The LLM should not be the sole authority for numerical risk prediction.

### Agent 8 — Compliance & Fairness Agent
**Owner:** Rohit

Responsibilities:
- Check whether the recommendation is explainable.
- Check that inappropriate/protected attributes are not driving decisions.
- Add responsible-AI checks.
- Identify potential fairness/compliance concerns.

### Agent 9 — Decision / Policy Agent
**Owner:** Christy

Takes earlier outputs and applies final policy/business rules.

Example:
```text
Risk = Low
Fraud = Low
Required docs = Complete
Validation = Pass
        ↓
Recommendation = APPROVE / REVIEW
```

Policy should be deterministic where possible. The LLM should not arbitrarily override the risk model or validation findings.

### Agent 10 — Summarization / Reviewer Agent
**Owner:** Christy

Creates a reviewer-friendly packet containing:
- Applicant information
- Documents received
- Extracted fields
- Confidence scores
- Citations
- Validation findings
- Missing documents
- Fraud alerts
- Risk score
- Risk explanation
- Compliance findings
- Final recommendation

---

## 4. GenAI Architecture

The current external GenAI provider is:

```text
Groq API
```

with a Qwen multimodal model.

Environment variable:
```text
GROQ_API_KEY
```

The API key must never be committed to GitHub.

Shared client:
```text
shared/llm_client.py
```

Architecture:
```text
Agents
   ↓
shared/llm_client.py
   ↓
Groq API
   ↓
Qwen multimodal model
```

### API Count

Currently the project is designed around **one external GenAI API provider: Groq**.

Local components such as OCR, scikit-learn, XGBoost, SHAP, and JSON Schema do not require separate external API keys.

---

## 5. OCR / Document Processing

Fallback technologies:
- `pdfminer.six`
- `pytesseract`
- `Pillow`

Conceptually:

```text
PDF
 ↓
PDF text extraction
 ↓
LLM

OR

Image/scanned PDF
 ↓
OCR
 ↓
LLM
```

Real PDFs may be:
- Text-based
- Scanned
- Image-heavy
- Poor quality
- Multi-page
- Structured differently from synthetic examples

Real-PDF handling is a major integration area that needs testing.

---

## 6. Agent Relationships

The main data flow is:

```text
Harris
  ↓
documents + classification
  ↓
Austin
  ↓
extracted_fields[]
  ↓
Alina
  ↓
validation_findings[]
fraud_flags[]
missing_documents[]
  ↓
Rohit
  ↓
risk + compliance
  ↓
Christy
  ↓
decision + summary + UI
```

This shared flow is the main connection between contributors.

---

## 7. Christy — Orchestration + UI

Christy owns the final integration layer.

Responsibilities:
- Connect existing modules into one pipeline.
- Manage application state.
- Route data between agents.
- Handle retries/failures.
- Produce final application state.
- Build the reviewer-facing UI.

The UI should display:
- Uploaded documents
- Document classification
- Extracted fields
- Confidence
- Source citations
- Validation issues
- Fraud alerts
- Missing documents
- Risk score
- Explainability
- Compliance
- Final recommendation

Christy should integrate existing modules rather than rewriting them unnecessarily.

---

## 8. Shared Data Contract

Central schema:

```text
schema/loan_file.schema.json
```

Important structures include:
```text
extracted_fields[]
validation_findings[]
fraud_flags[]
missing_documents[]
risk_result
compliance_result
audit_log[]
```

All agents should communicate through compatible structured data. Do not create arbitrary incompatible formats for individual agents.

---

## 9. Technology Stack

### Frontend
- React
- Vite

### Backend
- Python
- FastAPI

### Generative AI
- Groq API
- Qwen multimodal model
- Prompt engineering

### Document Processing
- pdfminer.six
- pytesseract
- Pillow

### Machine Learning
- scikit-learn
- XGBoost

### Explainability
- SHAP

### Validation / Testing
- JSON Schema
- pytest

### Infrastructure
- Docker
- Docker Compose

Kubernetes compatibility is an architectural goal, but should not be considered complete until actually tested.

---

## 10. Repository Structure

Major areas:

```text
loanIQ/
│
├── ingestion/
├── extraction/
├── validation/
├── risk/
├── orchestrator/
├── shared/
├── schema/
├── tests/
├── .github/
├── requirements.txt
├── README.md
└── frontend/UI components
```

Important files:
```text
schema/loan_file.schema.json
schema/loan_file.example.json
shared/schema_loader.py
shared/llm_client.py
```

---

## 11. Current Git Baseline

Current merged `main` baseline:

```text
cf1c151
Merge pull request #12 from unsupervised-humans/feature/christy-orchestration
```

Merged contributions:
```text
Harris   → merged
Austin   → merged
Alina    → merged
Rohit    → merged
Christy  → merged
```

Current objective is NOT to redo their individual contributions.

The objective is:

> Take the complete merged system, evaluate it end-to-end locally, identify integration failures, fix them, test everything, and only then push the final corrected version.

---

## 12. Current Testing Status

The first complete pytest run showed:

```text
191 passed
10 failed
8 errors
18 skipped
```

Known categories:

### Pytest collection problem

`scripts/test_agents.py` contains functions that pytest interprets as tests even though they expect command-line parameters/arguments such as `base`, `verbose`, and `timeout`.

This should be inspected before changing application logic.

### Austin extraction regression

Two extraction tests failed around malformed/invalid LLM output.

Expected:
```text
invalid LLM output
       ↓
failure sentinel
       ↓
needs_review = true
```

Current behavior returned empty extraction in those cases.

### Harris classifier interface mismatch

Tests and implementation appear to use different assumptions about the classifier/LLM client interface. Determine the intended contract before changing tests or code.

### Rohit risk dependency

The risk model requires XGBoost in the runtime environment. Missing dependency produced:
```text
ModuleNotFoundError: No module named 'xgboost'
```

### Rohit CIBIL feature issue

A test expected a CIBIL score such as `780`, but current feature extraction returned `600`. This requires investigation because CIBIL can materially affect the risk model.

---

## 13. Current Priority

Do not immediately add new features.

Priority:

```text
1. Establish clean local baseline
        ↓
2. Fix dependencies
        ↓
3. Fix unit/integration test failures
        ↓
4. Run complete test suite
        ↓
5. Launch actual application
        ↓
6. Test real PDFs
        ↓
7. Test complete agent pipeline
        ↓
8. Test UI
        ↓
9. Test Groq API
        ↓
10. Test schema/data flow
        ↓
11. Test Docker
        ↓
12. Final security/secrets audit
        ↓
13. Final end-to-end demo
        ↓
14. Push final corrected version
```

Do not push partial fixes while debugging. Make changes locally, run the complete system, and push only after stabilization.

---

## 14. Real PDF Test Cases

Three synthetic PDFs are available.

### Case 1 — Normal Application

Tests:
- Normal document processing
- Extraction
- Confidence
- Citations
- Validation
- Risk

Expected:
```text
Mostly consistent
→ normal/low-risk path
```

### Case 2 — Inconsistent/Fraud Application

Contains deliberate inconsistencies such as:
- Payslip income ≠ bank deposits
- Expired ID
- Salary mismatch

Expected:
```text
Validation alerts
+
Fraud/anomaly findings
+
Risk escalation
+
Human review
```

### Case 3 — Missing/Partial Application

Contains:
- Missing property documents
- Missing tax return
- Missing address proof
- Partial income information

Expected:
```text
Missing-document findings
+
Low-confidence/partial information
+
Human review
```

These must be used to test the actual PDF → complete pipeline, not only individual functions.

---

## 15. Engineering Principles

### Do not trust individual tests alone

A module can have all unit tests passing and still fail when connected to another module.

The real test is:

```text
REAL PDF
 ↓
REAL API
 ↓
REAL AGENTS
 ↓
REAL SHARED STATE
 ↓
REAL UI
```

### Never fabricate evidence

If the system does not know a value:
```text
value = null
needs_review = true
```

Do not make the LLM invent information.

### Never fabricate citations

If a bounding box is unavailable, do not create one.

### Do not let the LLM make arbitrary risk decisions

Risk should come from the ML/policy layer. The LLM can explain the result.

### Keep secrets out of Git

Never commit:
```text
GROQ_API_KEY
.env
API credentials
tokens
```

The API key must remain an environment/deployment secret.

---

## 16. Final Demo Story

The ideal demonstration:

```text
Applicant uploads 4–6 documents
          ↓
System automatically identifies them
          ↓
Multimodal AI extracts information
          ↓
Every field receives confidence + evidence
          ↓
Validation compares documents
          ↓
Fraud agent finds suspicious inconsistencies
          ↓
Missing-document agent checks completeness
          ↓
ML model calculates risk
          ↓
SHAP explains risk
          ↓
Compliance checks recommendation
          ↓
Orchestrator combines everything
          ↓
Reviewer receives one evidence-backed dashboard
```

## Core Pitch

> **LoanIQ doesn't simply ask an LLM for a loan decision. It creates an evidence-backed chain of specialized checks before anything reaches the human reviewer.**

This is the central concept that every LLM or developer working on LoanIQ must preserve.
