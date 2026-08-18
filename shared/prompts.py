"""
shared/prompts.py
-----------------
Shared LLM prompts across ingestion, extraction, and orchestrator modules.
"""

DOCUMENT_CLASSIFICATION_PROMPT = (
    "You are a document classifier for a loan processing system. "
    "Analyze the provided document and determine its document type.\n\n"
    "Valid document types:\n"
    "  - payslip: Salary slip, pay stub, salary statement\n"
    "  - bank_statement: Bank account statement, passbook summary\n"
    "  - tax_return: ITR form, income tax return, Form 16\n"
    "  - identity_document: Aadhaar, PAN card, Passport, Driving Licence, Voter ID\n"
    "  - address_proof: Utility bill, rental agreement, ration card\n"
    "  - employment_proof: Employment letter, offer letter, experience certificate\n"
    "  - combined_loan_package: A SINGLE PDF/file that contains MULTIPLE sections "
    "(e.g., applicant form + payslip + bank statement + KYC all merged together)\n"
    "  - unknown: Cannot determine type\n\n"
    "IMPORTANT: If the document contains two or more distinct section types "
    "(like both a payslip AND a bank statement), classify it as 'combined_loan_package'.\n\n"
    "Return ONLY a JSON object with the following fields:\n"
    "{\n"
    '  "document_type": "<payslip|bank_statement|tax_return|identity_document|address_proof|employment_proof|combined_loan_package|unknown>",\n'
    '  "confidence": <float between 0.0 and 1.0>,\n'
    '  "reasoning": "<brief explanation>"\n'
    "}"
)

SECTION_DETECTION_PROMPT = (
    "You are analyzing a combined loan document that contains multiple sections.\n"
    "Identify ALL distinct document sections present in this file.\n\n"
    "Possible section types:\n"
    "  - application_form: Applicant personal and financial details form\n"
    "  - payslip: Salary/pay slip section\n"
    "  - bank_statement: Bank account statement section\n"
    "  - identity_document: KYC / identity document section (Aadhaar, PAN, etc.)\n"
    "  - address_proof: Address proof section\n"
    "  - employment_proof: Employment letter / certificate section\n"
    "  - tax_return: Income tax return section\n\n"
    "Return ONLY a JSON object:\n"
    "{\n"
    '  "sections": ["<type1>", "<type2>", ...],\n'
    '  "confidence": <float 0.0-1.0>\n'
    "}"
)
