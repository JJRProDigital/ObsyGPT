from dataclasses import dataclass
from pathlib import Path

from .service import IMAGE_MIME_TYPES, PDF_MIME_TYPES, TEXT_MIME_TYPES


MAX_ATTACHMENT_CONTEXT_CHARS = 12000


@dataclass(frozen=True)
class AttachmentRecord:
    id: int
    file_name: str
    mime_type: str
    storage_path: str
    size_bytes: int
    artifact_type: str | None = None
    artifact_content: str | None = None


def build_attachment_context(attachments: list[AttachmentRecord], vision_supported: bool = False) -> str:
    blocks = []

    for attachment in attachments:
        if attachment.mime_type in TEXT_MIME_TYPES:
            blocks.append(build_text_block(attachment))
        elif attachment.mime_type in IMAGE_MIME_TYPES:
            blocks.append(build_image_block(attachment, vision_supported))
        elif attachment.mime_type in PDF_MIME_TYPES:
            if attachment.artifact_type == "pdf_extraction" and attachment.artifact_content:
                content = attachment.artifact_content[:MAX_ATTACHMENT_CONTEXT_CHARS]
                suffix = "\n[truncated]" if len(attachment.artifact_content) > MAX_ATTACHMENT_CONTEXT_CHARS else ""
                blocks.append(f"Attached PDF text: {attachment.file_name}\nContent:\n{content}{suffix}")
                continue
            blocks.append(
                f"Attached PDF: {attachment.file_name}\n"
                "PDF extraction is not fully enabled yet. Treat this as a stored PDF attachment and ask for extraction if text is required."
            )
        else:
            blocks.append(f"Attached file: {attachment.file_name}\nUnsupported MIME type for context: {attachment.mime_type}")

    return "\n\n".join(blocks)


def build_image_block(attachment: AttachmentRecord, vision_supported: bool) -> str:
    if vision_supported:
        return (
            f"Attached image: {attachment.file_name}\n"
            "The image is attached to this message. Describe only what you actually see in it."
        )
    return (
        f"Attached image: {attachment.file_name}\n"
        "IMPORTANT: the active model cannot see image content. Tell the user you cannot view this image "
        "and offer alternatives (a vision-capable model, or a text description from them). "
        "Do NOT invent, guess, or template a description of the image."
    )


def build_text_block(attachment: AttachmentRecord) -> str:
    path = Path(attachment.storage_path)
    content = path.read_text(encoding="utf-8", errors="replace") if path.exists() else ""
    truncated = len(content) > MAX_ATTACHMENT_CONTEXT_CHARS
    content = content[:MAX_ATTACHMENT_CONTEXT_CHARS]

    suffix = "\n[truncated]" if truncated else ""
    return f"Attached file: {attachment.file_name}\nMIME type: {attachment.mime_type}\nContent:\n{content}{suffix}"
