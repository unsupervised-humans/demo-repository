"""
Document Classification Agent.

Uses the shared Groq LLM API client to determine document type
for a normalized document. This is Harris's only LLM-touching component.

Does NOT extract financial fields -- classification only.

Multi-section support
---------------------
When a single uploaded PDF contains multiple logical sections (payslip +
bank statement + KYC + applicant form), the classifier:
1. Returns document_type = "combined_loan_package" with high confidence.
2. Calls detect_sections() to identify which section types are present.
   The section list is stored in ClassificationResult.detected_sections and
   forwarded to the extraction node so it can issue a single all-sections prompt.
"""

from __future__ import annotations

import json
import logging
from typing import Any, List, Optional


from shared.llm_client import GrokClient, LLMClientError, get_default_client
from shared.prompts import DOCUMENT_CLASSIFICATION_PROMPT, SECTION_DETECTION_PROMPT

from .models.document import ClassificationResult, DocumentType, NormalizedDocument

logger = logging.getLogger(__name__)

LOW_CONFIDENCE_THRESHOLD = 0.55

VALID_TYPES = {t.value for t in DocumentType}

# Aliases the LLM might return even with an updated prompt
_TYPE_ALIASES: dict[str, str] = {
    "paystub": "payslip",
    "salary_slip": "payslip",
    "pay_slip": "payslip",
    "w2": "tax_return",
    "itr": "tax_return",
    "id_card": "identity_document",
    "aadhaar": "identity_document",
    "pan_card": "identity_document",
    "passport": "identity_document",
    "kyc": "identity_document",
    "kyc_id": "identity_document",
    "utility_bill": "address_proof",
    "employment_letter": "employment_proof",
    "offer_letter": "employment_proof",
    "combined": "combined_loan_package",
    "multi_section": "combined_loan_package",
    "loan_package": "combined_loan_package",
}

# Valid section types that can appear inside a combined_loan_package
VALID_SECTION_TYPES = {
    "application_form", "payslip", "bank_statement", "identity_document",
    "address_proof", "employment_proof", "tax_return",
}

# Aliases for section types
_SECTION_ALIASES: dict[str, str] = {
    "kyc": "identity_document",
    "kyc_id": "identity_document",
    "id_card": "identity_document",
    "paystub": "payslip",
    "salary_slip": "payslip",
    "pay_slip": "payslip",
    "itr": "tax_return",
    "utility_bill": "address_proof",
    "employment_letter": "employment_proof",
    "offer_letter": "employment_proof",
}


class DocumentClassifier:
    """Classifies a normalized document into one of the supported types.

    For multi-section documents classified as ``combined_loan_package``,
    also detects the constituent section types via a follow-up LLM call.
    """

    def __init__(
        self,
        client: Optional[GrokClient] = None,
        low_confidence_threshold: float = LOW_CONFIDENCE_THRESHOLD,
    ) -> None:
        self._client = client
        self.low_confidence_threshold = low_confidence_threshold

    @property
    def client(self) -> Any:
        # Lazily resolve so unit tests can construct a DocumentClassifier
        # without GROQ_API_KEY being set, as long as they inject a client.
        if self._client is None:
            self._client = get_default_client()
        return self._client

    def classify(self, doc: NormalizedDocument) -> ClassificationResult:
        """Classify a single normalized document.

        Falls back to keyword heuristic if the LLM call fails or returns
        'unknown' — ensures extraction always has a meaningful document type
        even when the Groq API is rate-limited or unavailable.

        For ``combined_loan_package`` results, automatically follows up with
        ``detect_sections()`` to populate ``detected_sections``.
        """
        if doc.content_ref is None:
            logger.warning("No content to classify for %s", doc.doc_id)
            return ClassificationResult(
                document_type=DocumentType.UNKNOWN, confidence=0.0, low_confidence=True
            )

        classification = None
        try:
            result = self.client.chat.completions.create(
                model=self._get_model(),
                messages=self._build_classify_messages(doc),
                temperature=0,
                max_tokens=512,  # classification only needs a short response
            )
            raw_text = result.choices[0].message.content or ""
            classification = self._parse_result(raw_text)
        except (LLMClientError, Exception) as exc:
            logger.warning(
                "LLM classification failed for %s (%s) — using keyword fallback",
                doc.doc_id, exc,
            )

        # If LLM failed or returned unknown, apply keyword-based heuristic
        if classification is None or classification.document_type == DocumentType.UNKNOWN:
            heuristic = self._heuristic_classify(doc)
            if heuristic.document_type != DocumentType.UNKNOWN:
                logger.info(
                    "Heuristic classification for %s: %s (llm=%s)",
                    doc.doc_id, heuristic.document_type,
                    classification.document_type if classification else "N/A",
                )
                classification = heuristic
            elif classification is None:
                classification = ClassificationResult(
                    document_type=DocumentType.UNKNOWN, confidence=0.0, low_confidence=True
                )

        # For combined docs, detect sections with a follow-up call
        if classification.document_type == DocumentType.COMBINED_LOAN_PACKAGE:
            sections = self.detect_sections(doc)
            classification.detected_sections = sections
            logger.info(
                "Combined loan package detected in %s — sections: %s",
                doc.doc_id, sections,
            )

        return classification

    def detect_sections(self, doc: NormalizedDocument) -> List[str]:
        """Detect which section types are present inside a combined document.

        Returns a list of normalized section type strings (e.g.
        ``["payslip", "bank_statement", "identity_document"]``).
        Falls back to an empty list on error — the extraction node will
        use a generic all-sections prompt as fallback.
        """
        if doc.content_ref is None:
            return []

        try:
            result = self.client.chat.completions.create(
                model=self._get_model(),
                messages=self._build_section_messages(doc),
                temperature=0,
                max_tokens=4096,
            )
            raw_text = result.choices[0].message.content or ""
        except Exception as exc:
            logger.warning("Section detection failed for %s: %s", doc.doc_id, exc)
            return []

        return self._parse_sections(raw_text)

    # ── Private helpers ──────────────────────────────────────────────────────

    def _get_model(self) -> str:
        """Return the active model name from the LLM client."""
        try:
            from shared.llm_client import active_model
            return active_model
        except ImportError:
            return "openai/gpt-oss-20b"

    def _build_classify_messages(self, doc: NormalizedDocument) -> list:
        messages: list = [
            {"role": "system", "content": "You are a document classification assistant."}
        ]
        if doc.mime_type == "application/pdf":
            pdf_text = ""
            if doc.content_ref:
                try:
                    from io import BytesIO
                    from pdfminer.high_level import extract_text
                    pdf_text = extract_text(BytesIO(doc.content_ref)) or ""
                except Exception as exc:
                    logger.warning("Failed to extract text from PDF for classification: %s", exc)
            if pdf_text.strip():
                user_content = f"{DOCUMENT_CLASSIFICATION_PROMPT}\n\nHere is the text extracted from the PDF:\n{pdf_text}"
            else:
                user_content = DOCUMENT_CLASSIFICATION_PROMPT + f"\n\n(Filename: {doc.file_name})"
        else:
            import base64
            b64 = base64.b64encode(doc.content_ref).decode("ascii")
            mime = doc.mime_type or "image/jpeg"
            user_content = [
                {"type": "text", "text": DOCUMENT_CLASSIFICATION_PROMPT},
                {
                    "type": "image_url",
                    "image_url": {"url": f"data:{mime};base64,{b64}"},
                },
            ]
        messages.append({"role": "user", "content": user_content})
        return messages

    def _build_section_messages(self, doc: NormalizedDocument) -> list:
        messages: list = [
            {"role": "system", "content": "You are a document section analyzer."}
        ]
        mime = doc.mime_type or "application/pdf"
        if mime == "application/pdf":
            pdf_text = ""
            if doc.content_ref:
                try:
                    from io import BytesIO
                    from pdfminer.high_level import extract_text
                    pdf_text = extract_text(BytesIO(doc.content_ref)) or ""
                except Exception as exc:
                    logger.warning("Failed to extract text from PDF for section detection: %s", exc)
            if pdf_text.strip():
                user_content = f"{SECTION_DETECTION_PROMPT}\n\nHere is the text extracted from the PDF:\n{pdf_text}"
            else:
                user_content = SECTION_DETECTION_PROMPT + f"\n\n(Filename: {doc.file_name})"
        else:
            import base64
            b64 = base64.b64encode(doc.content_ref).decode("ascii")
            user_content = [
                {"type": "text", "text": SECTION_DETECTION_PROMPT},
                {
                    "type": "image_url",
                    "image_url": {"url": f"data:{mime};base64,{b64}"},
                },
            ]
        messages.append({"role": "user", "content": user_content})
        return messages

    def _parse_result(self, raw: str) -> ClassificationResult:
        """Parse LLM classification JSON response."""
        text = raw.strip()
        # Strip markdown fences
        if "```" in text:
            for part in text.split("```"):
                part = part.strip()
                if part.startswith("json"):
                    part = part[4:].strip()
                if part.startswith("{"):
                    text = part
                    break

        try:
            data = json.loads(text)
        except json.JSONDecodeError:
            # Try to extract first JSON object
            start = text.find("{")
            end = text.rfind("}") + 1
            if start != -1 and end > start:
                try:
                    data = json.loads(text[start:end])
                except json.JSONDecodeError:
                    logger.warning("Could not parse classification JSON: %r", raw[:200])
                    return ClassificationResult(
                        document_type=DocumentType.UNKNOWN, confidence=0.0, low_confidence=True
                    )
            else:
                return ClassificationResult(
                    document_type=DocumentType.UNKNOWN, confidence=0.0, low_confidence=True
                )

        raw_type = str(data.get("document_type", "unknown")).strip().lower()
        confidence = data.get("confidence", 0.0)

        try:
            confidence = float(confidence)
        except (TypeError, ValueError):
            confidence = 0.0

        # Apply alias normalization
        raw_type = _TYPE_ALIASES.get(raw_type, raw_type)

        if raw_type not in VALID_TYPES:
            logger.warning("LLM returned unrecognized document_type: %r", raw_type)
            raw_type = DocumentType.UNKNOWN.value
            confidence = min(confidence, 0.0)

        doc_type = DocumentType(raw_type)
        low_confidence = confidence < self.low_confidence_threshold

        if low_confidence and doc_type != DocumentType.UNKNOWN:
            logger.info(
                "Low-confidence classification (%.2f) for type %s", confidence, doc_type
            )

        return ClassificationResult(
            document_type=doc_type,
            confidence=confidence,
            low_confidence=low_confidence,
        )

    def _parse_sections(self, raw: str) -> List[str]:
        """Parse section detection JSON response."""
        text = raw.strip()
        if "```" in text:
            for part in text.split("```"):
                part = part.strip()
                if part.startswith("json"):
                    part = part[4:].strip()
                if part.startswith("{"):
                    text = part
                    break

        try:
            data = json.loads(text)
        except json.JSONDecodeError:
            start = text.find("{")
            end = text.rfind("}") + 1
            if start != -1 and end > start:
                try:
                    data = json.loads(text[start:end])
                except json.JSONDecodeError:
                    logger.warning("Could not parse section detection JSON: %r", raw[:200])
                    return []
            else:
                return []

        raw_sections = data.get("sections", [])
        if not isinstance(raw_sections, list):
            return []

        normalized: List[str] = []
        for s in raw_sections:
            s_lower = str(s).strip().lower()
            s_norm = _SECTION_ALIASES.get(s_lower, s_lower)
            if s_norm in VALID_SECTION_TYPES and s_norm not in normalized:
                normalized.append(s_norm)

        return normalized

    def _heuristic_classify(self, doc: NormalizedDocument) -> ClassificationResult:
        """Keyword-based fallback classifier using filename + OCR text.

        Used when the LLM fails (rate limit, timeout, JSON parse error) or
        returns 'unknown'. Covers the most common loan document types.
        """
        # Build search corpus: filename + OCR text (if available)
        corpus = (doc.file_name or "").lower()
        ocr_text = ""
        if doc.content_ref and doc.mime_type == "application/pdf":
            try:
                from io import BytesIO
                from pdfminer.high_level import extract_text
                ocr_text = (extract_text(BytesIO(doc.content_ref)) or "").lower()
            except Exception:
                pass
        elif doc.content_ref:
            try:
                ocr_text = doc.content_ref.decode("utf-8", errors="ignore").lower()
            except Exception:
                pass
        corpus = corpus + " " + ocr_text

        # Ordered by specificity — check most specific patterns first
        _KEYWORD_RULES: List[tuple] = [
            # (document_type_value, required_keywords, optional_boost_keywords)
            ("combined_loan_package", ["loan application", "payslip"], ["bank statement", "kyc"]),
            ("payslip", ["gross pay", "net pay"], ["employee", "salary", "payslip", "pay slip", "payroll"]),
            ("payslip", ["gross monthly", "net monthly"], ["employee", "employer"]),
            ("payslip", ["salary slip", "pay slip"], []),
            ("payslip", ["payslip"], []),
            ("bank_statement", ["opening balance", "closing balance"], ["account", "bank"]),
            ("bank_statement", ["bank statement"], []),
            ("bank_statement", ["account statement"], []),
            ("bank_statement", ["transaction", "debit", "credit"], ["account number", "ifsc"]),
            ("identity_document", ["aadhaar"], []),
            ("identity_document", ["pan card", "permanent account number"], []),
            ("identity_document", ["passport"], ["date of birth", "nationality"]),
            ("identity_document", ["driving licence", "driving license"], []),
            ("identity_document", ["voter id", "election card"], []),
            ("identity_document", ["date of birth", "id number"], ["identity", "kyc"]),
            ("tax_return", ["income tax", "itr"], []),
            ("tax_return", ["form 16", "tds certificate"], []),
            ("tax_return", ["assessment year", "taxable income"], []),
            ("address_proof", ["utility bill", "electricity bill", "water bill"], []),
            ("address_proof", ["rental agreement", "rent agreement"], []),
            ("employment_proof", ["offer letter", "appointment letter"], []),
            ("employment_proof", ["employment certificate", "experience letter"], []),
            ("application_form", ["loan application", "loan request"], []),
            ("application_form", ["loan amount requested", "requested amount"], []),
        ]

        for doc_type_val, required, _boost in _KEYWORD_RULES:
            if all(kw in corpus for kw in required):
                try:
                    doc_type = DocumentType(doc_type_val)
                    return ClassificationResult(
                        document_type=doc_type,
                        confidence=0.72,  # heuristic — below LLM confidence but above low threshold
                        low_confidence=False,
                    )
                except ValueError:
                    continue

        # Filename-based fallback
        name_lower = (doc.file_name or "").lower()
        filename_rules = [
            ("payslip", ["payslip", "salary", "paystub", "pay_slip"]),
            ("bank_statement", ["bank", "statement", "account"]),
            ("identity_document", ["aadhaar", "pan", "passport", "kyc", "id_card", "identity"]),
            ("tax_return", ["itr", "tax", "form16", "form_16"]),
            ("address_proof", ["address", "utility", "bill"]),
            ("employment_proof", ["employment", "offer", "appointment"]),
            ("application_form", ["application", "loan_form"]),
        ]
        for doc_type_val, keywords in filename_rules:
            if any(kw in name_lower for kw in keywords):
                try:
                    doc_type = DocumentType(doc_type_val)
                    return ClassificationResult(
                        document_type=doc_type,
                        confidence=0.60,
                        low_confidence=False,
                    )
                except ValueError:
                    continue

        return ClassificationResult(
            document_type=DocumentType.UNKNOWN, confidence=0.0, low_confidence=True
        )
