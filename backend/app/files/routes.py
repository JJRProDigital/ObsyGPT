from pathlib import Path

from fastapi import APIRouter, File, HTTPException, Request, UploadFile

from ..auth.routes import require_user
from ..db import connect
from .service import AttachmentCandidate, AttachmentService, UnsupportedAttachmentError


router = APIRouter(prefix="/api", tags=["files"])


def insert_attachment(user_id: int, prepared, message_id: int | None = None):  # noqa: ANN001, ANN201
    with connect() as connection:
        with connection.cursor() as cursor:
            cursor.execute(
                """
                INSERT INTO attachments (user_id, message_id, file_name, mime_type, storage_path, size_bytes)
                VALUES (%s, %s, %s, %s, %s, %s)
                RETURNING id, file_name, mime_type, storage_path, size_bytes, created_at;
                """,
                (
                    user_id,
                    message_id,
                    prepared.original_file_name,
                    prepared.mime_type,
                    prepared.storage_path,
                    prepared.size_bytes,
                ),
            )
            attachment_columns = [column.name for column in cursor.description]
            attachment = dict(zip(attachment_columns, cursor.fetchone()))

            cursor.execute(
                """
                INSERT INTO artifacts (attachment_id, artifact_type, title, content)
                VALUES (%s, %s, %s, %s)
                RETURNING id, attachment_id, artifact_type, title, content, created_at;
                """,
                (attachment["id"], prepared.artifact_type, prepared.original_file_name, prepared.extracted_text),
            )
            artifact_columns = [column.name for column in cursor.description]
            artifact = dict(zip(artifact_columns, cursor.fetchone()))

    return attachment, artifact


@router.post("/attachments")
async def upload_attachment(request: Request, file: UploadFile = File(...)):
    user_id = require_user(request)
    content = await file.read()

    try:
        prepared = AttachmentService().prepare(
            AttachmentCandidate(
                file_name=file.filename or "attachment",
                mime_type=file.content_type or "application/octet-stream",
                content=content,
            )
        )
    except UnsupportedAttachmentError as error:
        raise HTTPException(status_code=415, detail=str(error)) from error
    except ValueError as error:
        raise HTTPException(status_code=400, detail=str(error)) from error

    attachment, artifact = insert_attachment(user_id, prepared)
    return {"attachment": attachment, "artifact": artifact}


@router.get("/attachments")
def list_attachments(request: Request):
    user_id = require_user(request)
    with connect() as connection:
        with connection.cursor() as cursor:
            cursor.execute(
                """
                SELECT id, file_name, mime_type, storage_path, size_bytes, created_at
                FROM attachments
                WHERE user_id = %s
                ORDER BY created_at DESC, id DESC;
                """,
                (user_id,),
            )
            columns = [column.name for column in cursor.description]
            attachments = [dict(zip(columns, row)) for row in cursor.fetchall()]

    return {"attachments": attachments}


def remove_storage_file(storage_path: str | None, storage_root: Path) -> bool:
    """Deletes the stored file only when it lives inside the uploads root (never arbitrary paths)."""
    if not storage_path:
        return False
    try:
        target = Path(storage_path).resolve()
        if not target.is_relative_to(storage_root.resolve()):
            return False
        if target.exists() and target.is_file():
            target.unlink()
            return True
    except OSError:
        return False
    return False


@router.delete("/attachments/{attachment_id}")
def delete_attachment(attachment_id: int, request: Request):
    """Deletes an upload: DB rows (artifacts and project links cascade) plus the stored file."""
    user_id = require_user(request)
    with connect() as connection:
        with connection.cursor() as cursor:
            cursor.execute(
                "SELECT id, storage_path FROM attachments WHERE id = %s AND user_id = %s;",
                (attachment_id, user_id),
            )
            row = cursor.fetchone()
            if not row:
                raise HTTPException(status_code=404, detail="Attachment not found.")
            cursor.execute("DELETE FROM attachments WHERE id = %s AND user_id = %s;", (attachment_id, user_id))

    storage_root = AttachmentService().storage_root
    file_removed = remove_storage_file(row[1], storage_root)
    return {"removed": True, "attachment_id": attachment_id, "file_removed": file_removed}
