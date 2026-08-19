"""extraction/prompts.py
Document-type-specific extraction prompts for the Grok multimodal model.

Each prompt function returns the *user-turn* message content (string).
The system turn is shared across all document types and is defined in
SYSTEM_PROMPT.

Design notes
------------
- Prompts request STRUCTURED JSON ONLY so the response parser has a
  predictable surface to parse.
- The JSON envelope requested from the model is:
    {
      "fields": [
        {
          "field_name":  <string>,
          "value":       <any>,
          "confidence":  <float 0-1>,
          "page":        <int or null>,
          "bbox":        [x, y, w, h] or null
        },
        ...
      ]
    }
- Bbox is requested only as "if visible in the response"; the citation
  module will omit it when the model returns null.
- Prompts never invent values; they instruct the model to use null + low
  confidence when a field is absent or illegible.
"""

from __future__ import annotations

SYSTEM_PROMPT: str = (
    "You are a precise document field extractor for a loan-processing system. "
    "Your task is to extract structured data from financial and identity documents. "
    "Rules:\n"
    "1. Return ONLY valid JSON — no prose, no markdown fences.\n"
    "2. Use the exact JSON envelope: {\"fields\": [...]}\n"
    "3. Each item in 'fields' must have: field_name, value, confidence (0-1), "
    "page (integer, 1-indexed), bbox ([x,y,w,h] normalised 0-1 or null).\n"
    "4. If a field is absent or illegible, set value=null and confidence<=0.3.\n"
    "5. Do NOT fabricate values. Do NOT fabricate bbox coordinates.\n"
    "6. confidence must reflect your true certainty — never inflate it.\n"
    "7. Dates: ISO 8601 (YYYY-MM-DD). Numbers: plain numeric, no currency symbols.\n"
    "8. Keep your thinking process (within <think>...</think> tags) extremely concise (fewer than 50 words)."
)

_JSON_REMINDER: str = (
    "\n\nRespond with ONLY valid JSON matching this schema:\n"
    "{\n"
    "  \"fields\": [\n"
    "    {\n"
    "      \"field_name\": \"<snake_case_name>\",\n"
    "      \"value\": <extracted_value_or_null>,\n"
    "      \"confidence\": <0.0-1.0>,\n"
    "      \"page\": <integer_or_null>,\n"
    "      \"bbox\": [x, y, width, height] or null\n"
    "    }\n"
    "  ]\n"
    "}"
)


def payslip_prompt(doc_id: str) -> str:
    """Prompt for payslip / salary-slip documents."""
    return (
        f"This is a payslip (doc_id={doc_id!r}). Extract the following fields:\n"
        "- employer_name          (string)\n"
        "- employee_name          (string, may also be labelled 'applicant_name')\n"
        "- gross_monthly_income   (number, in local currency units)\n"
        "- net_monthly_income     (number)\n"
        "- pay_period_start       (date YYYY-MM-DD)\n"
        "- pay_period_end         (date YYYY-MM-DD)\n"
        "- designation            (string, job title)\n"
        "- employee_id            (string)\n"
        "- pan_number             (string, if present)\n"
        "- provident_fund         (number, if present)\n"
        "Extract only fields that are actually present. "
        "If a field is missing or illegible, include it with value=null and confidence<=0.3."
        + _JSON_REMINDER
    )


def bank_statement_prompt(doc_id: str) -> str:
    """Prompt for bank statement documents."""
    return (
        f"This is a bank statement (doc_id={doc_id!r}). Extract the following fields:\n"
        "- account_holder_name    (string)\n"
        "- account_number         (string, may be partially masked — include as-is)\n"
        "- bank_name              (string)\n"
        "- statement_period_start (date YYYY-MM-DD)\n"
        "- statement_period_end   (date YYYY-MM-DD)\n"
        "- opening_balance        (number)\n"
        "- closing_balance        (number)\n"
        "- avg_monthly_deposit    (number, average monthly credit amount over the period)\n"
        "- avg_monthly_withdrawal (number, average monthly debit amount over the period)\n"
        "- total_credits          (number, sum of all credits in the statement period)\n"
        "- total_debits           (number, sum of all debits in the statement period)\n"
        "- ifsc_code              (string, if present)\n"
        "- cibil_score            (number 300-900, CIBIL/credit score if printed on the statement)\n"
        "Extract only fields that are actually present. "
        "If a field is missing or illegible, include it with value=null and confidence<=0.3."
        + _JSON_REMINDER
    )


def kyc_id_prompt(doc_id: str) -> str:
    """Prompt for KYC / identity documents (Aadhaar, PAN, passport, driving licence)."""
    return (
        f"This is an identity / KYC document (doc_id={doc_id!r}). Extract the following fields:\n"
        "- applicant_name         (string, full name exactly as printed)\n"
        "- date_of_birth          (date YYYY-MM-DD)\n"
        "- id_number              (string, document number / Aadhaar / PAN / passport number)\n"
        "- id_document_type       (string, e.g. 'aadhaar', 'pan', 'passport', 'driving_licence')\n"
        "- id_expiry_date         (date YYYY-MM-DD, null if the document type has no expiry)\n"
        "- address_line1          (string, if present)\n"
        "- address_city           (string, if present)\n"
        "- address_state          (string, if present)\n"
        "- address_pincode        (string, if present)\n"
        "- gender                 (string 'male'/'female'/'other', if present)\n"
        "Extract only fields that are actually present. "
        "If a field is missing or illegible, include it with value=null and confidence<=0.3."
        + _JSON_REMINDER
    )


def tax_return_prompt(doc_id: str) -> str:
    """Prompt for tax-return / ITR documents."""
    return (
        f"This is a tax return (ITR) document (doc_id={doc_id!r}). Extract the following fields:\n"
        "- applicant_name         (string)\n"
        "- pan_number             (string)\n"
        "- assessment_year        (string, e.g. '2025-26')\n"
        "- gross_total_income     (number)\n"
        "- taxable_income         (number)\n"
        "- tax_paid               (number)\n"
        "- tax_refund_due         (number, 0 if not applicable)\n"
        "- filing_date            (date YYYY-MM-DD, if present)\n"
        "- itr_form_type          (string, e.g. 'ITR-1', 'ITR-2')\n"
        "Extract only fields that are actually present. "
        "If a field is missing or illegible, include it with value=null and confidence<=0.3."
        + _JSON_REMINDER
    )


def address_proof_prompt(doc_id: str) -> str:
    """Prompt for address-proof documents (utility bill, rental agreement, etc.)."""
    return (
        f"This is an address-proof document (doc_id={doc_id!r}). Extract the following fields:\n"
        "- applicant_name         (string)\n"
        "- address_line1          (string)\n"
        "- address_line2          (string, if present)\n"
        "- address_city           (string)\n"
        "- address_state          (string)\n"
        "- address_pincode        (string)\n"
        "- document_date          (date YYYY-MM-DD, date of the document)\n"
        "- document_issuer        (string, e.g. utility company or landlord name)\n"
        "Extract only fields that are actually present. "
        "If a field is missing or illegible, include it with value=null and confidence<=0.3."
        + _JSON_REMINDER
    )


def employment_proof_prompt(doc_id: str) -> str:
    """Prompt for employment-proof documents (offer letter, employment certificate)."""
    return (
        f"This is an employment-proof document (doc_id={doc_id!r}). Extract the following fields:\n"
        "- employee_name          (string)\n"
        "- employer_name          (string)\n"
        "- designation            (string)\n"
        "- employment_start_date  (date YYYY-MM-DD)\n"
        "- employment_type        (string, e.g. 'permanent', 'contract', 'probation')\n"
        "- annual_ctc             (number, cost-to-company, if stated)\n"
        "- document_date          (date YYYY-MM-DD)\n"
        "- hr_contact             (string, if present)\n"
        "Extract only fields that are actually present. "
        "If a field is missing or illegible, include it with value=null and confidence<=0.3."
        + _JSON_REMINDER
    )


def other_document_prompt(doc_id: str, doc_type: str) -> str:
    """Generic extraction prompt for unrecognised document types."""
    return (
        f"This is a financial/identity document of type {doc_type!r} "
        f"(doc_id={doc_id!r}). "
        "Extract all key-value pairs that appear to be relevant to a loan application "
        "(names, dates, amounts, IDs, addresses, account numbers, income figures). "
        "Use descriptive snake_case field names. "
        "Extract only fields that are actually visible in the document. "
        "If a field is missing or illegible, include it with value=null and confidence<=0.3."
        + _JSON_REMINDER
    )


def credit_report_prompt(doc_id: str) -> str:
    """Prompt for credit report / CIBIL report documents."""
    return (
        f"This is a credit report or CIBIL report (doc_id={doc_id!r}). Extract the following fields:\n"
        "- applicant_name          (string)\n"
        "- cibil_score             (number 300-900, the overall CIBIL / credit score)\n"
        "- credit_score            (number 300-900, alias for cibil_score if labelled differently)\n"
        "- report_date             (date YYYY-MM-DD)\n"
        "- total_outstanding_debt  (number, total outstanding balance across all accounts)\n"
        "- number_of_accounts      (number, total credit accounts)\n"
        "- number_of_active_accounts (number)\n"
        "- overdue_accounts        (number, accounts with overdue payments)\n"
        "- enquiries_last_6_months (number)\n"
        "- pan_number              (string, if present)\n"
        "Extract only fields that are actually present. "
        "If a field is missing or illegible, include it with value=null and confidence<=0.3."
        + _JSON_REMINDER
    )


def combined_loan_package_prompt(doc_id: str, sections: list[str] | None = None) -> str:
    """Prompt for combined multi-section loan documents.

    This handles PDFs that bundle multiple document types (applicant form,
    payslip, bank statement, KYC, employment letter) into a single file.
    Instructs the model to extract ALL relevant fields from ALL sections.
    """
    if sections:
        section_names = ", ".join(sections)
        section_note = (
            f"This combined document has been pre-identified as containing the following "
            f"sections: {section_names}.\n"
            f"Extract fields from EACH section that is present.\n\n"
        )
    else:
        section_note = (
            "This is a combined loan application package containing multiple sections.\n"
            "Extract fields from ALL sections present in the document.\n\n"
        )

    return (
        f"This is a combined multi-section loan document (doc_id={doc_id!r}).\n"
        + section_note
        + "Extract ALL of the following fields wherever they appear:\n\n"
        "--- APPLICANT / APPLICATION FORM fields ---\n"
        "- applicant_name          (string, full name)\n"
        "- application_date        (date YYYY-MM-DD)\n"
        "- loan_amount_requested   (number)\n"
        "- loan_type               (string, e.g. 'home', 'personal', 'auto')\n"
        "- loan_term               (number, in years)\n"
        "- declared_income         (number, monthly or annual)\n"
        "- no_of_dependents        (number)\n"
        "- self_employed           (boolean/string)\n"
        "- education               (string)\n\n"
        "--- PAYSLIP fields ---\n"
        "- employer_name           (string)\n"
        "- employee_name           (string)\n"
        "- gross_monthly_income    (number)\n"
        "- net_monthly_income      (number)\n"
        "- pay_period_start        (date YYYY-MM-DD)\n"
        "- pay_period_end          (date YYYY-MM-DD)\n"
        "- designation             (string)\n"
        "- employee_id             (string)\n\n"
        "--- BANK STATEMENT fields ---\n"
        "- account_holder_name     (string)\n"
        "- account_number          (string)\n"
        "- bank_name               (string)\n"
        "- statement_period_start  (date YYYY-MM-DD)\n"
        "- statement_period_end    (date YYYY-MM-DD)\n"
        "- opening_balance         (number)\n"
        "- closing_balance         (number)\n"
        "- avg_monthly_deposit     (number)\n"
        "- avg_monthly_withdrawal  (number)\n\n"
        "--- CREDIT / CIBIL REPORT fields (if present) ---\n"
        "- cibil_score             (number 300-900, CIBIL or credit score)\n"
        "- credit_score            (number 300-900, alias if labelled differently)\n"
        "- total_outstanding_debt  (number)\n"
        "- overdue_accounts        (number)\n\n"
        "--- KYC / IDENTITY DOCUMENT fields ---\n"
        "- id_number               (string)\n"
        "- id_document_type        (string)\n"
        "- id_expiry_date          (date YYYY-MM-DD)\n"
        "- address_line1           (string)\n"
        "- address_city            (string)\n"
        "- address_state           (string)\n"
        "- address_pincode         (string)\n\n"
        "--- EMPLOYMENT LETTER fields (if present) ---\n"
        "- employment_start_date   (date YYYY-MM-DD)\n"
        "- employment_type         (string)\n"
        "- annual_ctc              (number)\n\n"
        "--- TAX RETURN fields (if present) ---\n"
        "- assessment_year         (string)\n"
        "- gross_total_income      (number)\n"
        "- pan_number              (string)\n\n"
        "Extract only fields that are actually present in the document. "
        "If a field is missing or illegible, include it with value=null and confidence<=0.3."
        + _JSON_REMINDER
    )


def application_form_prompt(doc_id: str) -> str:
    """Prompt for loan application forms (the main applicant-filled form).

    Application forms typically contain a dedicated CIBIL / credit score
    section, personal details, income declaration, and loan requirements.
    """
    return (
        f"This is a loan application form (doc_id={doc_id!r}). Extract the following fields:\\n"
        "--- APPLICANT DETAILS ---\\n"
        "- applicant_name          (string, full name as written)\\n"
        "- date_of_birth           (date YYYY-MM-DD)\\n"
        "- pan_number              (string)\\n"
        "- mobile_number           (string)\\n"
        "- email                   (string)\\n"
        "- address_line1           (string)\\n"
        "- address_city            (string)\\n"
        "- address_state           (string)\\n"
        "- address_pincode         (string)\\n"
        "- education               (string, e.g. Graduate, Post Graduate)\\n"
        "- no_of_dependents        (number)\\n"
        "--- EMPLOYMENT & INCOME ---\\n"
        "- employment_type         (string, e.g. salaried, self_employed)\\n"
        "- employer_name           (string)\\n"
        "- designation             (string)\\n"
        "- annual_income           (number, annual gross income in INR)\\n"
        "- declared_income         (number, monthly or annual income declared)\\n"
        "--- LOAN DETAILS ---\\n"
        "- loan_amount_requested   (number, in INR)\\n"
        "- loan_type               (string, e.g. home, personal, auto)\\n"
        "- loan_term               (number, in years)\\n"
        "--- CREDIT / CIBIL SECTION ---\\n"
        "- cibil_score             (number 300-900, the CIBIL credit score shown in the application)\\n"
        "- credit_score            (number 300-900, use if labelled credit score instead of CIBIL)\\n"
        "Extract only fields that are actually present. "
        "If a field is missing or illegible, include it with value=null and confidence<=0.3."
        + _JSON_REMINDER
    )


# ── Router ─────────────────────────────────────────────────────────────────────

_PROMPT_MAP: dict[str, object] = {
    "payslip": payslip_prompt,
    "bank_statement": bank_statement_prompt,
    "kyc_id": kyc_id_prompt,
    "identity_document": kyc_id_prompt,   # alias
    "tax_return": tax_return_prompt,
    "address_proof": address_proof_prompt,
    "employment_proof": employment_proof_prompt,
    "combined_loan_package": combined_loan_package_prompt,
    "application_form": application_form_prompt,
    "credit_report": credit_report_prompt,
    "cibil_report": credit_report_prompt,   # alias
}


def get_prompt(doc_type: str, doc_id: str, detected_sections: list[str] | None = None) -> str:
    """Return the appropriate extraction prompt for *doc_type*.

    Falls back to the generic other_document_prompt for unknown types.

    Parameters
    ----------
    doc_type : str
        Document type from the schema enum (e.g. 'payslip', 'kyc_id').
    doc_id : str
        Document identifier, embedded in the prompt for traceability.
    detected_sections : list[str] | None
        For combined_loan_package documents, the list of section types
        detected by the classifier. Passed to the combined prompt.

    Returns
    -------
    str
        The user-turn prompt content to send to the model.
    """
    if doc_type == "combined_loan_package":
        return combined_loan_package_prompt(doc_id, sections=detected_sections)
    fn = _PROMPT_MAP.get(doc_type)
    if fn is not None:
        return fn(doc_id)  # type: ignore[operator]
    return other_document_prompt(doc_id, doc_type)
