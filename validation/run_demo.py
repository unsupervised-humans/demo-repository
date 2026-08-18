"""Runnable demo: name-mismatch fixture through Alina's agents.

Usage:
    python -m validation.run_demo
"""

from __future__ import annotations

import json
from pathlib import Path

from validation.fraud_detector import detect_fraud
from validation.graph import build_consistency_graph, graph_to_dict
from validation.missing_documents import check_missing_documents
from validation.validator import validate

SAMPLE_PATH = Path(__file__).resolve().parent / "samples" / "sample_name_mismatch.json"


def main() -> None:
    payload = json.loads(SAMPLE_PATH.read_text(encoding="utf-8"))
    fields = payload["extracted_fields"]
    documents = payload.get("documents") or []
    loan_type = payload.get("loan_type") or "personal"

    findings = validate(fields)
    missing = check_missing_documents(loan_type, None, documents)
    flags = detect_fraud(fields, documents, findings)
    graph = build_consistency_graph(fields, findings)
    graph_payload = graph_to_dict(graph)

    name_findings = [f for f in findings if f.finding_type == "name_mismatch"]
    if name_findings:
        finding = name_findings[0]
        print("NAME MISMATCH")
        print(f"Severity: {finding.severity.value}")
        values = finding.values
        # Demo layout from the role brief.
        kyc_val = values.get("DOC-001", "")
        bank_val = values.get("DOC-003", "")
        if not kyc_val or not bank_val:
            # Fall back to scanning sources.
            for src in finding.sources:
                if src.doc_id == "DOC-001":
                    kyc_val = kyc_val or values.get(src.doc_id, "")
                if src.doc_id == "DOC-003":
                    bank_val = bank_val or values.get(src.doc_id, "")
        print(f"KYC:  {kyc_val}")
        print(f"Bank: {bank_val}")
        source_bits = [f"{s.doc_id}/Page {s.page}" for s in finding.sources]
        print(f"Sources: {', '.join(source_bits)}")
        print()
        print(finding.message)
    else:
        print("No name mismatch finding.")

    print()
    print(f"Validation findings: {len(findings)}")
    print(f"Missing documents:   {len(missing.missing)}")
    print(f"Fraud flags:         {len(flags)}")
    print(f"Graph nodes/edges:   {len(graph_payload['nodes'])}/{len(graph_payload['edges'])}")
    for flag in flags:
        print(f"- {flag.flag_type} [{flag.severity.value}] {flag.description}")


if __name__ == "__main__":
    main()
