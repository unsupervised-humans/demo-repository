"""extraction/ocr_fallback.py
OCR / text fallback for scanned documents.

Strategy
--------
1. If the document file path ends with a recognised text extension
   (.txt, .md, .csv) just read the file directly.
2. If it is a PDF, try to extract embedded text with pdfminer.six.
3. If it is an image (PNG, JPG, TIFF, BMP, WEBP) try pytesseract OCR.
4. If any dependency is missing, log a warning and return None so the
   caller falls back to passing the raw file as a base64 image to Grok.

None is returned whenever text extraction is impossible or yields less
than MIN_TEXT_CHARS characters (heuristic for a blank/scanned page).

The caller (extractor.py) decides whether the extracted text or a
base64-encoded image is sent to the model.
"""

from __future__ import annotations

import logging
from pathlib import Path
from typing import Optional

logger = logging.getLogger(__name__)

MIN_TEXT_CHARS = 50  # below this we treat the file as image-only


def extract_text(file_path: str | Path) -> Optional[str]:
    """Attempt to extract plain text from *file_path*.

    Parameters
    ----------
    file_path : str | Path
        Absolute or relative path to the document file.

    Returns
    -------
    str | None
        Extracted text, or None if text extraction failed or the
        document is effectively blank.
    """
    path = Path(file_path)
    suffix = path.suffix.lower()

    if not path.exists():
        logger.warning("OCR fallback: file not found: %s", path)
        return None

    # ── plain text ────────────────────────────────────────────────────────────
    if suffix in {".txt", ".md", ".csv"}:
        try:
            text = path.read_text(encoding="utf-8", errors="replace")
            return text if len(text) >= MIN_TEXT_CHARS else None
        except OSError as exc:
            logger.warning("OCR fallback: could not read text file %s: %s", path, exc)
            return None

    # ── PDF embedded text ─────────────────────────────────────────────────────
    if suffix == ".pdf":
        return _pdf_text(path)

    # ── image OCR ─────────────────────────────────────────────────────────────
    if suffix in {".png", ".jpg", ".jpeg", ".tiff", ".tif", ".bmp", ".webp"}:
        return _image_ocr(path)

    logger.debug("OCR fallback: unsupported file type %s — skipping", suffix)
    return None


# -- PDF helpers ---------------------------------------------------------------

def _pdf_text(path: Path) -> Optional[str]:
    """Extract embedded text from a PDF.

    Strategy:
    1. PyMuPDF (fitz) -- best layout preservation for structured docs.
    2. pdfminer.six -- fallback if PyMuPDF is not installed.
    """
    # --- PyMuPDF (preferred) ---
    try:
        import fitz  # type: ignore  # PyMuPDF

        doc = fitz.open(str(path))
        pages_text: list[str] = []
        for page in doc:
            pages_text.append(page.get_text("text"))
        doc.close()
        text = "\n".join(pages_text).strip()
        if text and len(text) >= MIN_TEXT_CHARS:
            return text
        logger.debug("OCR fallback: PyMuPDF extracted too little text from %s", path)
        # Fall through to pdfminer
    except ImportError:
        logger.debug(
            "PyMuPDF (fitz) not installed; trying pdfminer.six. "
            "Install with: pip install pymupdf"
        )
    except Exception as exc:  # noqa: BLE001
        logger.warning("OCR fallback: PyMuPDF failed for %s: %s", path, exc)

    # --- pdfminer.six (fallback) ---
    try:
        from pdfminer.high_level import extract_text as pdfminer_extract  # type: ignore
        text = pdfminer_extract(str(path))
        if text and len(text.strip()) >= MIN_TEXT_CHARS:
            return text.strip()
        logger.debug("OCR fallback: PDF has no embedded text or too short: %s", path)
        return None
    except ImportError:
        logger.warning(
            "pdfminer.six not installed; cannot extract PDF text. "
            "Install with: pip install pdfminer.six"
        )
        return None
    except Exception as exc:  # noqa: BLE001
        logger.warning("OCR fallback: pdfminer failed for %s: %s", path, exc)
        return None


# ── Image OCR helpers ─────────────────────────────────────────────────────────

def _image_ocr(path: Path) -> Optional[str]:
    """Extract text from an image using pytesseract."""
    try:
        from PIL import Image  # type: ignore
        import pytesseract  # type: ignore

        img = Image.open(path)
        text = pytesseract.image_to_string(img)
        if text and len(text.strip()) >= MIN_TEXT_CHARS:
            return text.strip()
        logger.debug("OCR fallback: Tesseract returned too little text for %s", path)
        return None
    except ImportError:
        logger.warning(
            "pytesseract or Pillow not installed; cannot OCR image. "
            "Install with: pip install pytesseract Pillow  (and install Tesseract binary)"
        )
        return None
    except Exception as exc:  # noqa: BLE001
        logger.warning("OCR fallback: pytesseract failed for %s: %s", path, exc)
        return None


# ── Base64 image encoder (for multimodal API) ─────────────────────────────────

def encode_image_base64(file_path: str | Path) -> Optional[str]:
    """Return a base64-encoded string of the file's raw bytes.

    Used to pass images directly to the Grok multimodal endpoint when OCR
    text extraction is unavailable or insufficient.

    Returns None if the file cannot be read.
    """
    path = Path(file_path)
    if not path.exists():
        logger.warning("encode_image_base64: file not found: %s", path)
        return None
    try:
        import base64
        return base64.b64encode(path.read_bytes()).decode("ascii")
    except OSError as exc:
        logger.warning("encode_image_base64: could not read %s: %s", path, exc)
        return None


def get_image_mime_type(file_path: str | Path) -> str:
    """Return the MIME type for an image path (best-effort)."""
    suffix = Path(file_path).suffix.lower()
    mime_map = {
        ".jpg": "image/jpeg",
        ".jpeg": "image/jpeg",
        ".png": "image/png",
        ".gif": "image/gif",
        ".webp": "image/webp",
        ".tiff": "image/tiff",
        ".tif": "image/tiff",
        ".bmp": "image/bmp",
        ".pdf": "application/pdf",
    }
    return mime_map.get(suffix, "application/octet-stream")
