"""Alina's validation, missing-document, and fraud agents."""

from validation.audit import log_failure, log_validation_run
from validation.findings import (
    ExtractedField,
    Finding,
    FraudFlag,
    MissingDocumentFinding,
    Severity,
    make_finding,
    make_fraud_flag,
)
from validation.fraud_detector import GrokVisualClient, detect_fraud, maybe_run_visual_check
from validation.graph import build_consistency_graph, graph_to_dict
from validation.missing_documents import check_missing_documents
from validation.pipeline import process_loan_file
from validation.validator import validate

__all__ = [
    "ExtractedField",
    "Finding",
    "FraudFlag",
    "GrokVisualClient",
    "MissingDocumentFinding",
    "Severity",
    "build_consistency_graph",
    "check_missing_documents",
    "detect_fraud",
    "graph_to_dict",
    "log_failure",
    "log_validation_run",
    "make_finding",
    "make_fraud_flag",
    "maybe_run_visual_check",
    "process_loan_file",
    "validate",
]
