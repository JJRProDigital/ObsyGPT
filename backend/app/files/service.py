import re
from dataclasses import dataclass
from io import BytesIO
from pathlib import Path
from typing import Callable
from uuid import uuid4


MAX_ATTACHMENT_BYTES = 10 * 1024 * 1024

TEXT_MIME_TYPES = {
    "text/plain",
    "text/markdown",
    "text/csv",
    "application/csv",
}

IMAGE_MIME_TYPES = {
    "image/png",
    "image/jpeg",
    "image/webp",
    "image/gif",
}

PDF_MIME_TYPES = {"application/pdf"}

SUPPORTED_MIME_TYPES = TEXT_MIME_TYPES | IMAGE_MIME_TYPES | PDF_MIME_TYPES


class UnsupportedAttachmentError(ValueError):
    pass


@dataclass(frozen=True)
class AttachmentCandidate:
    file_name: str
    mime_type: str
    content: bytes


@dataclass(frozen=True)
class PreparedAttachment:
    original_file_name: str
    safe_file_name: str
    mime_type: str
    storage_path: str
    size_bytes: int
    artifact_type: str
    extracted_text: str


class AttachmentService:
    def __init__(self, storage_root: Path | str = "uploads", pdf_text_extractor: Callable[[bytes], str] | None = None):
        self.storage_root = Path(storage_root)
        self.pdf_text_extractor = pdf_text_extractor or extract_pdf_text

    def prepare(self, candidate: AttachmentCandidate) -> PreparedAttachment:
        self.validate(candidate)
        self.storage_root.mkdir(parents=True, exist_ok=True)

        safe_file_name = self.build_safe_file_name(candidate.file_name)
        storage_path = self.storage_root / safe_file_name
        storage_path.write_bytes(candidate.content)

        artifact_type, extracted_text = self.extract(candidate)

        return PreparedAttachment(
            original_file_name=candidate.file_name,
            safe_file_name=safe_file_name,
            mime_type=candidate.mime_type,
            storage_path=str(storage_path),
            size_bytes=len(candidate.content),
            artifact_type=artifact_type,
            extracted_text=extracted_text,
        )

    def validate(self, candidate: AttachmentCandidate) -> None:
        if candidate.mime_type not in SUPPORTED_MIME_TYPES:
            raise UnsupportedAttachmentError(f"Unsupported attachment type: {candidate.mime_type}")
        if len(candidate.content) > MAX_ATTACHMENT_BYTES:
            raise ValueError(f"Attachment exceeds {MAX_ATTACHMENT_BYTES} bytes.")
        if not candidate.file_name.strip():
            raise ValueError("Attachment file name is required.")

    def build_safe_file_name(self, file_name: str) -> str:
        clean_name = re.sub(r"[^A-Za-z0-9._-]+", "-", Path(file_name).name).strip("-._")
        if not clean_name:
            clean_name = "attachment"
        return f"{uuid4().hex}-{clean_name}"

    def extract(self, candidate: AttachmentCandidate) -> tuple[str, str]:
        if candidate.mime_type in TEXT_MIME_TYPES:
            return "text_extraction", candidate.content.decode("utf-8", errors="replace").strip()

        if candidate.mime_type in IMAGE_MIME_TYPES:
            return "image_attachment", f"Image attachment ready for a vision-capable model: {candidate.file_name}"

        if candidate.mime_type in PDF_MIME_TYPES:
            text = self.pdf_text_extractor(candidate.content).strip()
            if text:
                return "pdf_extraction", text[:12000]
            return "pdf_attachment", f"PDF attachment stored for extraction: {candidate.file_name}"

        raise UnsupportedAttachmentError(f"Unsupported attachment type: {candidate.mime_type}")


def extract_pdf_text(content: bytes) -> str:
    try:
        from pypdf import PdfReader
    except Exception:
        return ""

    try:
        reader = PdfReader(BytesIO(content))
        return "\n".join((page.extract_text() or "").strip() for page in reader.pages).strip()
    except Exception:
        return ""
