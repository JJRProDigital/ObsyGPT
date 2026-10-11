from pathlib import Path

from app.files.context import AttachmentRecord, build_attachment_context


def test_build_attachment_context_reads_text_attachment(tmp_path: Path):
    text_file = tmp_path / "notes.txt"
    text_file.write_text("Important project notes", encoding="utf-8")

    context = build_attachment_context(
        [
            AttachmentRecord(
                id=1,
                file_name="notes.txt",
                mime_type="text/plain",
                storage_path=str(text_file),
                size_bytes=23,
            )
        ]
    )

    assert "Attached file: notes.txt" in context
    assert "Important project notes" in context


def test_build_attachment_context_describes_image_attachment(tmp_path: Path):
    image_file = tmp_path / "diagram.png"
    image_file.write_bytes(b"png")

    context = build_attachment_context(
        [
            AttachmentRecord(
                id=2,
                file_name="diagram.png",
                mime_type="image/png",
                storage_path=str(image_file),
                size_bytes=3,
            )
        ]
    )

    assert "Attached image: diagram.png" in context
    assert "vision-capable model" in context


def test_build_attachment_context_describes_pdf_attachment(tmp_path: Path):
    pdf_file = tmp_path / "paper.pdf"
    pdf_file.write_bytes(b"%PDF")

    context = build_attachment_context(
        [
            AttachmentRecord(
                id=3,
                file_name="paper.pdf",
                mime_type="application/pdf",
                storage_path=str(pdf_file),
                size_bytes=4,
            )
        ]
    )

    assert "Attached PDF: paper.pdf" in context
    assert "PDF extraction" in context


def test_build_attachment_context_uses_pdf_extraction_artifact(tmp_path: Path):
    pdf_file = tmp_path / "paper.pdf"
    pdf_file.write_bytes(b"%PDF")

    context = build_attachment_context(
        [
            AttachmentRecord(
                id=3,
                file_name="paper.pdf",
                mime_type="application/pdf",
                storage_path=str(pdf_file),
                size_bytes=4,
                artifact_type="pdf_extraction",
                artifact_content="Extracted PDF content for the model.",
            )
        ]
    )

    assert "Attached PDF text: paper.pdf" in context
    assert "Extracted PDF content for the model." in context


def test_build_attachment_context_limits_large_text(tmp_path: Path):
    text_file = tmp_path / "large.txt"
    text_file.write_text("x" * 15000, encoding="utf-8")

    context = build_attachment_context(
        [AttachmentRecord(id=4, file_name="large.txt", mime_type="text/plain", storage_path=str(text_file), size_bytes=15000)]
    )

    assert len(context) < 13000
    assert "truncated" in context
