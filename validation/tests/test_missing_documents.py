"""Missing-document agent tests."""

from validation.missing_documents import DEFAULT_REQUIRED_DOCUMENTS, check_missing_documents
from validation.tests.conftest import load_sample


def test_all_required_docs_present_empty_missing_list():
    sample = load_sample("sample_clean_application.json")
    result = check_missing_documents("personal", None, sample["documents"])
    assert result.missing == []
    assert set(result.present) == set(DEFAULT_REQUIRED_DOCUMENTS["personal"])


def test_one_doc_missing_correct_finding_and_message():
    sample = load_sample("sample_missing_document.json")
    result = check_missing_documents("personal_loan", None, sample["documents"])
    assert len(result.missing) == 1
    finding = result.missing[0]
    assert finding.document_type == "bank_statement"
    assert finding.status == "missing"
    assert finding.request_message == (
        "Please provide your latest bank statement to continue processing your application."
    )
    assert "bank statement" in finding.draft_message.lower()
    assert "kyc_id" in result.present
    assert "payslip" in result.present


def test_different_loan_type_uses_different_required_set():
    docs = [
        {"doc_id": "d1", "type": "kyc_id"},
        {"doc_id": "d2", "type": "payslip"},
        {"doc_id": "d3", "type": "bank_statement"},
    ]
    personal = check_missing_documents("personal", None, docs)
    home = check_missing_documents("home", None, docs)
    assert personal.missing == []
    assert len(home.missing) == 1
    assert home.missing[0].document_type == "tax_return"
    business = check_missing_documents("business_loan", None, docs)
    types = {f.document_type for f in business.missing}
    assert "tax_return" in types
    assert "payslip" not in {f.document_type for f in business.missing}
    assert "payslip" not in DEFAULT_REQUIRED_DOCUMENTS["business"]
