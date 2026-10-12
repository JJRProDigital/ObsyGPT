"""Attachment helpers for chat context building."""

from base64 import b64encode
from pathlib import Path

from fastapi import HTTPException

from .. import db as app_db
from ..files import AttachmentRecord, build_attachment_context  # noqa: F401 - re-exported for consumers
from ..files.service import IMAGE_MIME_TYPES


def get_attachment_records(user_id: int, attachment_ids: list[int]) -> list[AttachmentRecord]:
    if not attachment_ids:
        return []

    with app_db.connect() as connection:
        with connection.cursor() as cursor:
            cursor.execute(
                """
                SELECT
                    a.id,
                    a.file_name,
                    a.mime_type,
                    a.storage_path,
                    a.size_bytes,
                    ar.artifact_type,
                    ar.content
                FROM attachments a
                LEFT JOIN LATERAL (
                    SELECT artifact_type, content
                    FROM artifacts
                    WHERE attachment_id = a.id
                    ORDER BY created_at DESC, id DESC
                    LIMIT 1
                ) ar ON true
                WHERE a.user_id = %s AND a.id = ANY(%s)
                ORDER BY a.created_at, a.id;
                """,
                (user_id, attachment_ids),
            )
            rows = cursor.fetchall()

    return [
        AttachmentRecord(
            id=row[0],
            file_name=row[1],
            mime_type=row[2],
            storage_path=row[3],
            size_bytes=row[4],
            artifact_type=row[5],
            artifact_content=row[6],
        )
        for row in rows
    ]


def ensure_requested_attachments_available(attachment_ids: list[int], attachments: list[AttachmentRecord]) -> None:
    requested_ids = set(attachment_ids)
    if not requested_ids:
        return

    available_ids = {attachment.id for attachment in attachments}
    if requested_ids - available_ids:
        raise HTTPException(status_code=404, detail="One or more attachments were not found.")


def attachment_data_url(attachment: AttachmentRecord) -> str | None:
    """Encodes a stored image attachment as a data URL; None when missing or too large."""
    max_bytes = 4 * 1024 * 1024
    if attachment.mime_type not in IMAGE_MIME_TYPES or attachment.size_bytes > max_bytes:
        return None
    path = Path(attachment.storage_path)
    if not path.exists():
        return None
    encoded = b64encode(path.read_bytes()).decode("ascii")
    return f"data:{attachment.mime_type};base64,{encoded}"
