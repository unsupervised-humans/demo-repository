"""
Document Normalization.

No LLM is used here. This module is responsible for:
  - PDF / image / file-extension / file-size validation
  - page counting
  - unique doc_id assignment
  - basic file metadata
  - graceful handling of corrupted/unsupported files

This runs BEFORE classification. Output feeds the Classification Agent.
"""

from __future__ import annotations

import io
import logging
from typing import Optional

from .models.document import (
    IngestionStatus,
    NormalizedDocument,
    RawFile,
    generate_doc_id,
)

logger = logging.getLogger(__name__)

# --- Configuration -----------------------------------------------------

SUPPORTED_EXTENSIONS = {".pdf", ".jpg", ".jpeg", ".png"}
SUPPORTED_MIME_TYPES = {
    "application/pdf",
    "image/jpeg",
    "image/png",
}
MAX_FILE_SIZE_BYTES = 15 * 1024 * 1024  # 15 MB, adjust as needed


class Normalizer:
    """Validates and normalizes raw uploaded files."""

    def __init__(
        self,
        max_file_size_bytes: int = MAX_FILE_SIZE_BYTES,
        supported_extensions: Optional[set] = None,
    ) -> None:
        self.max_file_size_bytes = max_file_size_bytes
        self.supported_extensions = supported_extensions or SUPPORTED_EXTENSIONS

    def normalize(self, raw: RawFile) -> NormalizedDocument:
        """Run the full normalization pipeline on a single raw file."""
        doc_id = generate_doc_id()

        # 1. Empty file check
        if not raw.file_bytes:
            return self._fail(doc_id, raw, IngestionStatus.EMPTY, "File is empty")

        # 2. Size check
        size = len(raw.file_bytes)
        if size > self.max_file_size_bytes:
            return self._fail(
                doc_id,
                raw,
                IngestionStatus.TOO_LARGE,
                f"File size {size} exceeds max {self.max_file_size_bytes}",
            )

        # 3. Extension check
        ext = self._extract_extension(raw.file_name)
        if ext not in self.supported_extensions:
            return self._fail(
                doc_id,
                raw,
                IngestionStatus.UNSUPPORTED_FORMAT,
                f"Unsupported extension: {ext}",
            )

        # 4. Mime detection / validation
        mime_type = self._detect_mime_type(raw, ext)
        if mime_type not in SUPPORTED_MIME_TYPES:
            return self._fail(
                doc_id,
                raw,
                IngestionStatus.UNSUPPORTED_FORMAT,
                f"Unsupported or unverifiable mime type: {mime_type}",
            )

        # 5. Corruption check + page count
        try:
            page_count = self._count_pages(raw.file_bytes, mime_type)
        except Exception as exc:  # noqa: BLE001 - want to catch any parser failure
            logger.warning("Failed to parse %s: %s", raw.file_name, exc)
            return self._fail(
                doc_id, raw, IngestionStatus.CORRUPTED, f"Could not parse file: {exc}"
            )

        return NormalizedDocument(
            doc_id=doc_id,
            file_name=raw.file_name,
            mime_type=mime_type,
            page_count=page_count,
            file_size_bytes=size,
            status=IngestionStatus.OK,
            content_ref=raw.file_bytes,
        )

    # --- helpers ---------------------------------------------------

    def _fail(
        self,
        doc_id: str,
        raw: RawFile,
        status: IngestionStatus,
        error: str,
    ) -> NormalizedDocument:
        logger.info("Normalization failed for %s: %s", raw.file_name, error)
        return NormalizedDocument(
            doc_id=doc_id,
            file_name=raw.file_name,
            mime_type=raw.mime_type or "application/octet-stream",
            page_count=0,
            file_size_bytes=len(raw.file_bytes),
            status=status,
            error=error,
        )

    def _extract_extension(self, file_name: str) -> str:
        if "." not in file_name:
            return ""
        return "." + file_name.rsplit(".", 1)[-1].lower()

    def _detect_mime_type(self, raw: RawFile, ext: str) -> str:
        """Detect mime type from magic bytes, falling back to extension."""
        head = raw.file_bytes[:8]

        if head.startswith(b"%PDF-"):
            return "application/pdf"
        if head.startswith(b"\xff\xd8\xff"):
            return "image/jpeg"
        if head.startswith(b"\x89PNG\r\n\x1a\n"):
            return "image/png"

        # Fall back to extension-based guess; will be rejected downstream
        # if it doesn't match a supported mime type.
        ext_map = {
            ".pdf": "application/pdf",
            ".jpg": "image/jpeg",
            ".jpeg": "image/jpeg",
            ".png": "image/png",
        }
        return ext_map.get(ext, raw.mime_type or "application/octet-stream")

    def _count_pages(self, file_bytes: bytes, mime_type: str) -> int:
        """Count pages. Images are always 1 page. PDFs are parsed."""
        if mime_type in ("image/jpeg", "image/png"):
            return 1

        if mime_type == "application/pdf":
            return self._count_pdf_pages(file_bytes)

        raise ValueError(f"Cannot count pages for mime type: {mime_type}")

    def _count_pdf_pages(self, file_bytes: bytes) -> int:
        """Count PDF pages using pypdf if available, else a regex fallback."""
        if not file_bytes.startswith(b"%PDF-"):
            raise ValueError("Invalid PDF header")
        try:
            from pypdf import PdfReader  # type: ignore


            reader = PdfReader(io.BytesIO(file_bytes))
            if len(reader.pages) == 0:
                raise ValueError("PDF has zero pages")
            return len(reader.pages)
        except (ImportError, Exception):
            # Fallback: count "/Type /Page" occurrences minus "/Type /Pages" parent node.
            count = file_bytes.count(b"/Type/Page") + file_bytes.count(b"/Type /Page")
            pages_root = file_bytes.count(b"/Type/Pages") + file_bytes.count(b"/Type /Pages")
            real_count = count - pages_root
            if real_count <= 0:
                real_count = count if count > 0 else 1
            return real_count

