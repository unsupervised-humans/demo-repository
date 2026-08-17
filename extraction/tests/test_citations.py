"""extraction/tests/test_citations.py
Unit tests for extraction.citations.

Covers:
- build_source_ref with bbox present
- build_source_ref with bbox missing → omitted from dict
- Invalid bbox shapes are rejected
- Page coercion: None, string, float, negative → safe fallback
- extract_citation_flag page-invalid detection
"""

import pytest
from extraction.citations import build_source_ref, extract_citation_flag


class TestBuildSourceRef:
    def test_full_ref_with_bbox(self):
        ref = build_source_ref("doc-01", 1, [0.1, 0.2, 0.3, 0.04])
        assert ref["doc_id"] == "doc-01"
        assert ref["page"] == 1
        assert ref["bbox"] == pytest.approx([0.1, 0.2, 0.3, 0.04])

    def test_ref_without_bbox(self):
        ref = build_source_ref("doc-02", 3)
        assert ref["doc_id"] == "doc-02"
        assert ref["page"] == 3
        assert "bbox" not in ref

    def test_bbox_none_is_omitted(self):
        ref = build_source_ref("doc-03", 2, None)
        assert "bbox" not in ref

    def test_bbox_wrong_length_rejected(self):
        ref = build_source_ref("doc-04", 1, [0.1, 0.2, 0.3])  # only 3 elements
        assert "bbox" not in ref

    def test_bbox_five_elements_rejected(self):
        ref = build_source_ref("doc-04", 1, [0.1, 0.2, 0.3, 0.4, 0.5])
        assert "bbox" not in ref

    def test_bbox_non_numeric_rejected(self):
        ref = build_source_ref("doc-05", 1, ["a", "b", "c", "d"])
        assert "bbox" not in ref

    def test_bbox_not_list_rejected(self):
        ref = build_source_ref("doc-06", 1, "0.1,0.2,0.3,0.4")
        assert "bbox" not in ref

    def test_doc_id_coerced_to_string(self):
        ref = build_source_ref(123, 1)  # type: ignore[arg-type]
        assert ref["doc_id"] == "123"


class TestPageCoercion:
    def test_page_string_int(self):
        ref = build_source_ref("d", "2", None)
        assert ref["page"] == 2

    def test_page_float(self):
        ref = build_source_ref("d", 3.9, None)
        assert ref["page"] == 3

    def test_page_none_defaults_to_1(self):
        ref = build_source_ref("d", None, None)
        assert ref["page"] == 1

    def test_page_zero_clamps_to_1(self):
        ref = build_source_ref("d", 0, None)
        assert ref["page"] == 1

    def test_page_negative_clamps_to_1(self):
        ref = build_source_ref("d", -5, None)
        assert ref["page"] == 1

    def test_page_string_non_numeric_defaults_to_1(self):
        ref = build_source_ref("d", "N/A", None)
        assert ref["page"] == 1


class TestExtractCitationFlag:
    def test_valid_page_not_flagged(self):
        invalid, page = extract_citation_flag(2, None)
        assert invalid is False
        assert page == 2

    def test_none_page_is_flagged(self):
        invalid, page = extract_citation_flag(None, None)
        assert invalid is True
        assert page == 1

    def test_zero_page_is_flagged(self):
        invalid, page = extract_citation_flag(0, None)
        assert invalid is True

    def test_string_page_not_flagged_if_valid(self):
        invalid, page = extract_citation_flag("5", None)
        assert invalid is False
        assert page == 5
