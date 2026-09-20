from pathlib import Path

import pytest

from app.files.service import (
    MAX_ATTACHMENT_BYTES,
    AttachmentCandidate,
    AttachmentService,
    UnsupportedAttachmentError,
)


def test_attachment_service_extracts_text_from_plain_text(tmp_path: Path):
    service = AttachmentService(storage_root=tmp_path)
    candidate = AttachmentCandidate(
        file_name="notes.txt",
        mime_type="text/plain",
        content=b"Hello ObsyGPT\nThis is a document.",
    )

    result = service.prepare(candidate)

    assert result.safe_file_name.endswith("notes.txt")
    assert result.size_bytes == 33
    assert result.artifact_type == "text_extraction"
    assert result.extracted_text == "Hello ObsyGPT\nThis is a document."
    assert result.storage_path.endswith(result.safe_file_name)


def test_attachment_service_extracts_text_from_csv(tmp_path: Path):
    service = AttachmentService(storage_root=tmp_path)
    candidate = AttachmentCandidate(
        file_name="data.csv",
        mime_type="text/csv",
        content=b"name,score\nAda,10\nGrace,9",
    )

    result = service.prepare(candidate)

    assert result.artifact_type == "text_extraction"
    assert "Ada,10" in result.extracted_text


def test_attachment_service_returns_image_artifact_metadata(tmp_path: Path):
    service = AttachmentService(storage_root=tmp_path)
    candidate = AttachmentCandidate(
        file_name="diagram.png",
        mime_type="image/png",
        content=b"\x89PNG\r\n",
    )

    result = service.prepare(candidate)

    assert result.artifact_type == "image_attachment"
    assert result.extracted_text == "Image attachment ready for a vision-capable model: diagram.png"


def test_attachment_service_returns_pdf_artifact_metadata(tmp_path: Path):
    service = AttachmentService(storage_root=tmp_path)
    candidate = AttachmentCandidate(
        file_name="paper.pdf",
        mime_type="application/pdf",
        content=b"%PDF-1.7",
    )

    result = service.prepare(candidate)

    assert result.artifact_type == "pdf_attachment"
    assert result.extracted_text == "PDF attachment stored for extraction: paper.pdf"


def test_attachment_service_extracts_pdf_text_when_extractor_succeeds(tmp_path: Path):
    service = AttachmentService(storage_root=tmp_path, pdf_text_extractor=lambda content: "Extracted PDF text")
    candidate = AttachmentCandidate(
        file_name="paper.pdf",
        mime_type="application/pdf",
        content=b"%PDF-1.7",
    )

    result = service.prepare(candidate)

    assert result.artifact_type == "pdf_extraction"
    assert result.extracted_text == "Extracted PDF text"


def test_attachment_service_falls_back_when_pdf_extractor_returns_no_text(tmp_path: Path):
    service = AttachmentService(storage_root=tmp_path, pdf_text_extractor=lambda content: "   ")
    candidate = AttachmentCandidate(
        file_name="paper.pdf",
        mime_type="application/pdf",
        content=b"%PDF-1.7",
    )

    result = service.prepare(candidate)

    assert result.artifact_type == "pdf_attachment"
    assert result.extracted_text == "PDF attachment stored for extraction: paper.pdf"


def test_attachment_service_rejects_unsupported_mime_type(tmp_path: Path):
    service = AttachmentService(storage_root=tmp_path)
    candidate = AttachmentCandidate(
        file_name="archive.zip",
        mime_type="application/zip",
        content=b"zip",
    )

    with pytest.raises(UnsupportedAttachmentError, match="Unsupported attachment type"):
        service.prepare(candidate)


def test_attachment_service_rejects_oversized_files(tmp_path: Path):
    service = AttachmentService(storage_root=tmp_path)
    candidate = AttachmentCandidate(
        file_name="huge.txt",
        mime_type="text/plain",
        content=b"x" * (MAX_ATTACHMENT_BYTES + 1),
    )

    with pytest.raises(ValueError, match="Attachment exceeds"):
        service.prepare(candidate)
