"""Consistency graph: entity → document → field → value, with agreement/conflict edges."""

from __future__ import annotations

from collections import defaultdict
from typing import Any

import networkx as nx

from validation.findings import ExtractedField, Finding, coerce_extracted_fields
from validation.normalizers import normalize_name
from validation.validator import NAME_FIELD_NAMES, _usable

ENTITY_NODE = "entity:applicant"


def _value_node_id(field_name: str, value: Any) -> str:
    return f"value:{field_name}:{value}"


def _field_node_id(doc_id: str, field_name: str) -> str:
    return f"field:{doc_id}:{field_name}"


def _doc_node_id(doc_id: str) -> str:
    return f"doc:{doc_id}"


def build_consistency_graph(
    extracted_fields: list[ExtractedField | dict[str, Any]],
    findings: list[Finding],
) -> nx.Graph:
    """Build an undirected graph of extracted values and their agreement/conflict."""
    fields = coerce_extracted_fields(extracted_fields)
    graph: nx.Graph = nx.Graph()
    graph.add_node(ENTITY_NODE, kind="entity", label="applicant")

    by_name: dict[str, list[ExtractedField]] = defaultdict(list)
    for field in fields:
        if not _usable(field):
            continue
        doc_id = field.source.doc_id
        doc_node = _doc_node_id(doc_id)
        field_node = _field_node_id(doc_id, field.field_name)
        value_node = _value_node_id(field.field_name, field.value)

        graph.add_node(doc_node, kind="document", doc_id=doc_id, page=field.source.page)
        graph.add_node(
            field_node,
            kind="field",
            field_name=field.field_name,
            doc_id=doc_id,
        )
        graph.add_node(
            value_node,
            kind="value",
            field_name=field.field_name,
            value=field.value,
        )
        graph.add_edge(ENTITY_NODE, doc_node, relation="submitted")
        graph.add_edge(doc_node, field_node, relation="has_field")
        graph.add_edge(field_node, value_node, relation="has_value")
        by_name[field.field_name].append(field)

    # Pairwise agreement/conflict for the same field_name.
    for field_name, group in by_name.items():
        for i, left in enumerate(group):
            for right in group[i + 1 :]:
                left_node = _value_node_id(left.field_name, left.value)
                right_node = _value_node_id(right.field_name, right.value)
                if str(left.value) == str(right.value):
                    graph.add_edge(left_node, right_node, relation="agreement", field_name=field_name)
                else:
                    graph.add_edge(left_node, right_node, relation="conflict", field_name=field_name)

    # Semantic name group: applicant_name / employee_name / account_holder_name.
    name_fields = [f for f in fields if f.field_name in NAME_FIELD_NAMES and _usable(f)]
    for i, left in enumerate(name_fields):
        for right in name_fields[i + 1 :]:
            left_node = _value_node_id(left.field_name, left.value)
            right_node = _value_node_id(right.field_name, right.value)
            if left_node == right_node:
                continue
            same = normalize_name(str(left.value)) == normalize_name(str(right.value))
            relation = "agreement" if same else "conflict"
            if graph.has_edge(left_node, right_node):
                graph.edges[left_node, right_node]["relation"] = relation
                graph.edges[left_node, right_node]["field_name"] = "applicant_name"
            else:
                graph.add_edge(left_node, right_node, relation=relation, field_name="applicant_name")

    # Stamp conflict edges mentioned by findings so dashboard consumers can filter.
    for finding in findings:
        graph.graph.setdefault("finding_ids", [])
        graph.graph["finding_ids"].append(finding.finding_id)
        if finding.status in {"mismatch", "invalid", "inconsistent", "potentially_suspicious"}:
            graph.graph.setdefault("conflict_finding_types", [])
            graph.graph["conflict_finding_types"].append(finding.finding_type)

    return graph


def graph_to_dict(graph: nx.Graph) -> dict[str, Any]:
    """JSON-serializable projection for the dashboard (no NetworkX required on Christy's side)."""
    nodes = []
    for node_id, data in graph.nodes(data=True):
        item = {"id": node_id}
        item.update({k: v for k, v in data.items() if _jsonable(v)})
        nodes.append(item)
    edges = []
    for source, target, data in graph.edges(data=True):
        item = {"source": source, "target": target}
        item.update({k: v for k, v in data.items() if _jsonable(v)})
        edges.append(item)
    meta = {k: v for k, v in graph.graph.items() if _jsonable(v)}
    return {"nodes": nodes, "edges": edges, "meta": meta}


def _jsonable(value: Any) -> bool:
    return isinstance(value, (str, int, float, bool, list, dict, type(None)))
