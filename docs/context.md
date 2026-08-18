# LoanIQ — Multi-Agent Loan Processing System

## Technical Summary Report

## 1. Project Overview

LoanIQ is a multi-agent AI-powered loan processing system designed to automate loan-document processing, verification, risk assessment, compliance, and human review.

It processes:

- Payslips
- Bank statements
- KYC/identity documents
- Tax returns
- Employment proof
- Address proof

The architecture uses **10 specialized agents** grouped across five team members. Agents communicate through structured data defined by the shared `loan_file.schema.json`.

### End-to-End Pipeline

```text
Loan Application
    ↓
Ingestion
    ↓
Classification
    ↓
Multimodal Extraction
    ↓
Validation
    ↓
Fraud / Anomaly Detection
    ↓
Risk Scoring
    ↓
Compliance / Fairness
    ↓
Decision / Policy
    ↓
Reviewer Explanation
```

---

## 2. Agent Architecture

| # | Agent | Owner | Responsibility | Technology |
|---|---|---|---|---|
| 1 | Document Ingestion Agent | Harris | Receives/prepares loan documents | Python |
| 2 | Document Classification Agent | Harris | Identifies document type | AI/ML + Python |
| 3 | Multimodal Extraction Agent | Austin | Extracts information from documents | Groq + Qwen multimodal LLM |
| 4 | Document Validation Agent | Alina | Checks consistency and validity | Python + AI/rules |
| 5 | Fraud/Anomaly Agent | Alina | Detects suspicious information | Rules + anomaly logic |
| 6 | Risk Scoring Agent | Rohit | Calculates applicant risk | scikit-learn / XGBoost |
| 7 | Compliance/Fairness Agent | Rohit | Checks compliance/fairness | Python + policy logic |
| 8 | Decision/Policy Agent | Christy | Applies final decision rules | Agent/LLM + policy |
| 9 | Orchestrator Agent | Christy | Coordinates agents | Python / LangGraph planned |
| 10 | Reviewer/Explanation Agent | Christy | Presents explainable result | LLM + backend/UI |

---

## 3. Architecture Diagram

The diagram on **page 2** presents LoanIQ as a pipeline of specialized agents rather than a single LLM call.

```text
Documents & KYC Files
(Payslips, statements, tax forms)
            ↓
     Orchestrator Agent
     Routes tasks across agents
            ↓
      Specialist Agent Layer
 ┌───────────────────────────────────┐
 │ Doc Classifier │ Field Extraction │
 │ Validation     │ Missing-doc      │
 │ Fraud Detection│ Risk Scoring     │
 └───────────────────────────────────┘
            ↓
 ┌───────────────────┐   ┌─────────────────────┐
 │ Compliance &      │   │ Summarization Agent │
 │ Fairness Agent    │   │ Builds review report│
 └───────────────────┘   └─────────────────────┘
            ↓
       Human Review Dashboard
       Approve / reject / request docs
            ↓
        Feedback Loop
       Corrects / retrains models
```

### Core Idea

LoanIQ is **not a single LLM call**. It uses a pipeline of specialized agents that cross-check each other, with confidence scores and source citations before information reaches the human reviewer.

### 3.1 Orchestrator

- Controls the complete workflow.
- Routes documents to the correct agents.
- Handles retries and failures.
- Decides when an application is ready for review.

### 3.2 Document Classifier

- Identifies each uploaded document.
- Detects payslip, bank statement, KYC, tax return, etc.
- Handles documents uploaded in random order.

### 3.3 Field Extraction Agent

- Uses **multimodal AI (vision + text)**.
- Extracts important fields from documents.
- Assigns confidence scores.
- Provides page/bounding-box citations.
- Flags low-confidence fields for review.

### 3.4 Validation Agent

- Cross-checks information across documents.
- Checks names, income, dates, account information, and other inconsistencies.
- Converts mismatches into explicit findings.

### 3.5 Missing-Document Agent

- Checks whether all required documents are present.
- Requirements can depend on loan type/amount.
- Identifies missing documents and can draft a request to the applicant.

### 3.6 Fraud/Anomaly Agent

Looks for suspicious information and document inconsistencies, including:

- Formatting/tampering signals
- Unreconciled numbers
- Metadata anomalies
- Potentially reused documents

### 3.7 Risk Scoring Agent

- Uses the **Kaggle Loan Approval Prediction Dataset** for ML training.
- Uses models such as **XGBoost / Logistic Regression**.
- Produces a risk/approval score.
- Uses **SHAP** to explain important risk factors.

### 3.8 Compliance & Fairness Agent

- Checks whether recommendations are explainable.
- Checks for inappropriate use of protected attributes.
- Adds a responsible-AI and fairness layer.

### 3.9 Summarization Agent

Combines findings into a concise review packet containing:

- Extracted information
- Validation issues
- Fraud alerts
- Risk score
- Compliance findings
- Supporting citations

---

## 4. Generative AI

The primary external Generative AI service is the **Groq API** using a **Qwen multimodal model**.

The shared client is:

```text
shared/llm_client.py
```

It uses:

```text
GROQ_API_KEY
```

The actual API key is never stored in the repository.

### External API Strategy

One external GenAI provider is used rather than separate API integrations for every agent.

The following components can run locally/open-source:

- OCR
- Risk modeling
- SHAP
- Schema validation
- Most backend functions

This minimizes external API dependencies.

---

## 5. Austin — Multimodal Extraction

Austin converts unstructured loan documents into structured fields using **Groq/Qwen**.

The module supports:

- Document-specific prompts
- Confidence scoring
- Human-review flags
- Source citations
- Audit logging
- OCR/PDF fallback
- Graceful API failure handling
- Schema validation

### Confidence Threshold

Values below **0.70** result in:

```text
needs_review = true
```

This allows uncertain extraction results to be routed toward human review instead of being silently accepted.

---

## 6. Harris — Ingestion & Classification

Harris provides the front door of the workflow.

Responsibilities:

1. Receive documents.
2. Prepare documents for downstream processing.
3. Identify document types.
4. Select the appropriate processing path for each document.

---

## 7. Alina — Validation & Fraud

The report distinguishes the roles of extraction and validation:

> Austin answers what information is present in a document; Alina checks whether the information is valid and consistent.

Alina's intended outputs include:

```text
validation_findings[]
fraud_flags[]
missing_documents[]
```

This enables the system to surface:

- Cross-document inconsistencies
- Suspicious values
- Incomplete applications

before risk scoring.

---

## 8. Rohit — Risk & Compliance

Rohit combines:

```text
Austin's extracted_fields[]
        +
Alina's validation_findings[]
        +
Alina's fraud_flags[]
        +
Alina's missing_documents[]
```

### Training / Reference Dataset

The **Kaggle Loan Approval Prediction Dataset** is used as the training/reference source.

### Planned Model Stack

- **Logistic Regression** — baseline
- **XGBoost** — comparison model
- **SHAP** — explainability

### Evaluation

Evaluation includes:

- Precision
- Recall
- F1-score
- ROC-AUC
- Confusion matrix
- Calibration

The risk output should be **reproducible rather than being decided arbitrarily by an LLM**.

---

## 9. Shared Data Contract

The central contract between agents is:

```text
schema/loan_file.schema.json
```

### Main Data Flow

```text
Harris
  ↓
documents / classification
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
risk / compliance result
  ↓
Christy
```

The shared JSON schema provides a structured communication layer between agents.

---

## 10. Technology Stack

| Area | Technology |
|---|---|
| Frontend | React, Vite |
| Backend | Python, FastAPI |
| Generative AI | Groq API, Qwen multimodal model, prompt engineering |
| Document Processing | pdfminer.six, pytesseract, Pillow |
| Machine Learning | scikit-learn, XGBoost |
| Explainability | SHAP |
| Validation/Testing | JSON Schema, pytest |
| Infrastructure | Docker, Docker Compose |
| Deployment Architecture | Kubernetes-compatible architecture planned |

---

## 11. API & Cost Architecture

The current design minimizes external API dependencies.

The only external GenAI provider currently integrated is:

```text
Groq
```

The shared client uses:

```text
GROQ_API_KEY
```

Local/open-source components are planned for:

- OCR
- Risk ML
- SHAP
- JSON schema validation
- Backend logic
- Containerization

This architecture reduces the number of external API dependencies and helps control operational cost.

---

## 12. End-to-End Vision

```text
User
  ↓
Loan Documents
  ↓
Harris
Ingestion + Classification
  ↓
Austin
Multimodal Extraction
  ↓
Alina
Validation + Fraud
  ↓
Rohit
Risk + Compliance
  ↓
Christy
Orchestration + Explanation
  ↓
Human Reviewer
```

---

## 13. Final Project Statement

LoanIQ is a **10-agent AI-powered loan processing platform** combining:

- Multimodal Generative AI
- Traditional machine learning
- Explainable AI
- Document processing
- Rule-based validation

### Core Technologies

**Groq/Qwen**

Provides the primary GenAI capability for:

- Document understanding
- Multimodal extraction
- Agent reasoning

**XGBoost / scikit-learn**

Provides reproducible risk prediction.

**SHAP**

Provides model explainability.

**Shared JSON Schema**

Enables structured communication between agents.

### Current Status

The following components are merged and tested:

- Harris
- Austin
- Alina
- Rohit

### Next Milestone

The next milestone is:

**Christy's orchestration and the final end-to-end workflow/demo.**

---

## Quick Architecture Summary

```text
                    ┌──────────────────────┐
                    │   Loan Application   │
                    └──────────┬───────────┘
                               ↓
                    ┌──────────────────────┐
                    │ Harris               │
                    │ Ingestion +          │
                    │ Classification       │
                    └──────────┬───────────┘
                               ↓
                    ┌──────────────────────┐
                    │ Austin               │
                    │ Multimodal           │
                    │ Extraction           │
                    │ Groq + Qwen           │
                    └──────────┬───────────┘
                               ↓
                    ┌──────────────────────┐
                    │ Alina                │
                    │ Validation + Fraud   │
                    └──────────┬───────────┘
                               ↓
                    ┌──────────────────────┐
                    │ Rohit                │
                    │ Risk + Compliance    │
                    │ ML + SHAP             │
                    └──────────┬───────────┘
                               ↓
                    ┌──────────────────────┐
                    │ Christy              │
                    │ Orchestration +      │
                    │ Decision +           │
                    │ Explanation          │
                    └──────────┬───────────┘
                               ↓
                    ┌──────────────────────┐
                    │ Human Reviewer       │
                    └──────────────────────┘
```

## Key Design Principles

1. **Specialized agents instead of a single LLM call**
2. **Structured communication through a shared JSON schema**
3. **Confidence-aware multimodal extraction**
4. **Cross-document validation**
5. **Fraud and anomaly detection before risk scoring**
6. **Reproducible ML-based risk prediction**
7. **SHAP-based explainability**
8. **Compliance and fairness checks**
9. **Human-in-the-loop review**
10. **Minimal external API dependencies**
11. **Graceful failure and retry handling**
12. **Auditability through source citations and logging**
