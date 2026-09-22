"""Conversation, folder, and message persistence plus their HTTP endpoints."""

from datetime import datetime
from typing import Annotated, Literal

from fastapi import APIRouter, HTTPException, Request
from pydantic import BaseModel, Field, field_validator

from .. import db as app_db
from ..auth import routes as auth


router = APIRouter()


class ConversationUpdateRequest(BaseModel):
    title: str = Field(min_length=1, max_length=120)


class FolderPayload(BaseModel):
    name: str = Field(min_length=1, max_length=100)

    @field_validator("name")
    @classmethod
    def strip_name(cls, value: str) -> str:
        stripped = value.strip()
        if not stripped:
            raise ValueError("Folder name is required.")
        return stripped


class ConversationFolderPayload(BaseModel):
    folder_id: int | None = Field(default=None, ge=1)


class MessageEditPayload(BaseModel):
    content: str = Field(min_length=1, max_length=100000)


def create_conversation(user_id: int):
    with app_db.connect() as connection:
        with connection.cursor() as cursor:
            cursor.execute(
                """
                INSERT INTO conversations (user_id)
                VALUES (%s)
                RETURNING id, title, created_at;
                """,
                (user_id,),
            )
            return cursor.fetchone()


def delete_conversation(conversation_id: int, user_id: int) -> bool:
    with app_db.connect() as connection:
        with connection.cursor() as cursor:
            cursor.execute(
                """
                DELETE FROM conversations
                WHERE id = %s AND user_id = %s;
                """,
                (conversation_id, user_id),
            )
            return cursor.rowcount > 0


def update_conversation_title(conversation_id: int, user_id: int, title: str):  # noqa: ANN201
    with app_db.connect() as connection:
        with connection.cursor() as cursor:
            cursor.execute(
                """
                UPDATE conversations
                SET title = %s
                WHERE id = %s AND user_id = %s
                RETURNING id, title, created_at;
                """,
                (title, conversation_id, user_id),
            )
            row = cursor.fetchone()
            if not row:
                return None
            columns = [column.name for column in cursor.description]
            return dict(zip(columns, row))


def get_conversation(conversation_id: int, user_id: int):
    with app_db.connect() as connection:
        with connection.cursor() as cursor:
            cursor.execute(
                """
                SELECT id, title, created_at
                FROM conversations
                WHERE id = %s AND user_id = %s;
                """,
                (conversation_id, user_id),
            )
            return cursor.fetchone()


def get_conversations(user_id: int):
    with app_db.connect() as connection:
        with connection.cursor() as cursor:
            cursor.execute(
                """
                SELECT id, title, created_at, chat_number, folder_id
                FROM (
                    SELECT id, title, created_at, folder_id,
                           ROW_NUMBER() OVER (ORDER BY created_at, id) AS chat_number
                    FROM conversations
                    WHERE user_id = %s
                ) AS numbered_conversations
                ORDER BY folder_id NULLS LAST, created_at DESC, id DESC;
                """,
                (user_id,),
            )
            return cursor.fetchall()


def list_chat_folders(user_id: int) -> list[dict]:
    with app_db.connect() as connection:
        with connection.cursor() as cursor:
            cursor.execute(
                """
                SELECT f.id, f.name,
                       (SELECT COUNT(*) FROM conversations c WHERE c.folder_id = f.id) AS conversation_count
                FROM chat_folders f
                WHERE f.user_id = %s
                ORDER BY f.created_at, f.id;
                """,
                (user_id,),
            )
            columns = [column.name for column in cursor.description]
            return [dict(zip(columns, row)) for row in cursor.fetchall()]


def create_chat_folder(user_id: int, name: str) -> dict:
    with app_db.connect() as connection:
        with connection.cursor() as cursor:
            cursor.execute(
                """
                INSERT INTO chat_folders (user_id, name)
                VALUES (%s, %s)
                RETURNING id, name, created_at;
                """,
                (user_id, name),
            )
            row = cursor.fetchone()
            return {"id": row[0], "name": row[1], "conversation_count": 0}


def rename_chat_folder(folder_id: int, user_id: int, name: str) -> dict | None:
    with app_db.connect() as connection:
        with connection.cursor() as cursor:
            cursor.execute(
                """
                UPDATE chat_folders
                SET name = %s
                WHERE id = %s AND user_id = %s
                RETURNING id, name;
                """,
                (name, folder_id, user_id),
            )
            row = cursor.fetchone()
            if not row:
                return None
            return {"id": row[0], "name": row[1]}


def delete_chat_folder(folder_id: int, user_id: int) -> bool:
    with app_db.connect() as connection:
        with connection.cursor() as cursor:
            cursor.execute(
                "DELETE FROM chat_folders WHERE id = %s AND user_id = %s;",
                (folder_id, user_id),
            )
            return cursor.rowcount > 0


def move_conversation_to_folder(conversation_id: int, user_id: int, folder_id: int | None) -> dict | None:
    if folder_id is not None:
        with app_db.connect() as connection:
            with connection.cursor() as cursor:
                cursor.execute("SELECT id FROM chat_folders WHERE id = %s AND user_id = %s;", (folder_id, user_id))
                if not cursor.fetchone():
                    return None
    with app_db.connect() as connection:
        with connection.cursor() as cursor:
            cursor.execute(
                """
                UPDATE conversations
                SET folder_id = %s
                WHERE id = %s AND user_id = %s
                RETURNING id, folder_id;
                """,
                (folder_id, conversation_id, user_id),
            )
            row = cursor.fetchone()
            if not row:
                return None
            return {"id": row[0], "folder_id": row[1]}


def update_user_message(message_id: int, conversation_id: int, user_id: int, content: str) -> bool:
    with app_db.connect() as connection:
        with connection.cursor() as cursor:
            cursor.execute(
                """
                UPDATE messages m
                SET content = %s
                FROM conversations c
                WHERE m.id = %s
                  AND m.conversation_id = c.id
                  AND m.conversation_id = %s
                  AND c.user_id = %s
                  AND m.role = 'user'
                ;
                """,
                (content, message_id, conversation_id, user_id),
            )
            return cursor.rowcount > 0


def save_message(conversation_id: int, role: str, content: str) -> int:
    with app_db.connect() as connection:
        with connection.cursor() as cursor:
            cursor.execute(
                """
                INSERT INTO messages (conversation_id, role, content)
                VALUES (%s, %s, %s)
                RETURNING id;
                """,
                (conversation_id, role, content),
            )
            return cursor.fetchone()[0]


def get_messages(conversation_id: int):
    with app_db.connect() as connection:
        with connection.cursor() as cursor:
            cursor.execute(
                """
                SELECT id, role, content, created_at
                FROM messages
                WHERE conversation_id = %s
                ORDER BY created_at, id;
                """,
                (conversation_id,),
            )
            return cursor.fetchall()


def serialize_datetime(value: datetime) -> str:
    return value.isoformat()


def build_conversation_label(chat_number: int, created_at: datetime) -> str:
    formatted_time = created_at.astimezone().strftime("%m/%d/%Y %I:%M %p")
    formatted_time = formatted_time.replace(" 0", " ").lower()
    return f"Chat {chat_number} - {formatted_time}"


# ---------- endpoints ----------


@router.get("/conversations")
def list_conversations(request: Request):
    user_id = auth.require_user(request)
    conversations = [
        {
            "id": row[0],
            "title": row[1],
            "created_at": serialize_datetime(row[2]),
            "chat_number": row[3],
            "folder_id": row[4],
            "label": (row[1] or "").strip() or build_conversation_label(row[3], row[2]),
        }
        for row in get_conversations(user_id)
    ]
    return {"conversations": conversations}


@router.post("/conversations")
def new_conversation(request: Request):
    user_id = auth.require_user(request)
    conversation = create_conversation(user_id)
    return {"conversation": {"id": conversation[0], "title": conversation[1], "created_at": serialize_datetime(conversation[2])}}


@router.delete("/conversations/{conversation_id}")
def remove_conversation(conversation_id: int, request: Request):
    user_id = auth.require_user(request)
    if not delete_conversation(conversation_id, user_id):
        raise HTTPException(status_code=404, detail="Conversation not found.")
    return {"removed": True, "conversation_id": conversation_id}


@router.patch("/conversations/{conversation_id}")
def rename_conversation(conversation_id: int, data: ConversationUpdateRequest, request: Request):
    user_id = auth.require_user(request)
    title = data.title.strip()
    if not title:
        raise HTTPException(status_code=400, detail="Conversation title is required.")
    conversation = update_conversation_title(conversation_id, user_id, title)
    if not conversation:
        raise HTTPException(status_code=404, detail="Conversation not found.")
    return {"conversation": {**conversation, "created_at": serialize_datetime(conversation["created_at"])}}


@router.get("/folders")
def get_folders(request: Request):
    user_id = auth.require_user(request)
    return {"folders": list_chat_folders(user_id)}


@router.post("/folders")
def post_folder(payload: FolderPayload, request: Request):
    user_id = auth.require_user(request)
    return {"folder": create_chat_folder(user_id, payload.name.strip())}


@router.patch("/folders/{folder_id}")
def patch_folder(folder_id: int, payload: FolderPayload, request: Request):
    user_id = auth.require_user(request)
    folder = rename_chat_folder(folder_id, user_id, payload.name.strip())
    if not folder:
        raise HTTPException(status_code=404, detail="Folder not found.")
    return {"folder": folder}


@router.delete("/folders/{folder_id}")
def remove_folder(folder_id: int, request: Request):
    user_id = auth.require_user(request)
    if not delete_chat_folder(folder_id, user_id):
        raise HTTPException(status_code=404, detail="Folder not found.")
    return {"id": folder_id, "deleted": True}


@router.put("/conversations/{conversation_id}/folder")
def set_conversation_folder(conversation_id: int, payload: ConversationFolderPayload, request: Request):
    user_id = auth.require_user(request)
    result = move_conversation_to_folder(conversation_id, user_id, payload.folder_id)
    if not result:
        raise HTTPException(status_code=404, detail="Conversation or folder not found.")
    return result


@router.patch("/conversations/{conversation_id}/messages/{message_id}")
def edit_message(conversation_id: int, message_id: int, payload: MessageEditPayload, request: Request):
    user_id = auth.require_user(request)
    if not update_user_message(message_id, conversation_id, user_id, payload.content):
        raise HTTPException(status_code=404, detail="Message not found or not editable.")
    return {"message_id": message_id, "updated": True}


@router.get("/conversations/{conversation_id}/messages")
def list_messages(conversation_id: int, request: Request):
    user_id = auth.require_user(request)
    conversation = get_conversation(conversation_id, user_id)
    if not conversation:
        raise HTTPException(status_code=404, detail="Conversation not found.")

    messages = [
        {"id": row[0], "role": row[1], "content": row[2], "created_at": serialize_datetime(row[3])}
        for row in get_messages(conversation_id)
    ]
    return {
        "conversation": {"id": conversation[0], "title": conversation[1], "created_at": serialize_datetime(conversation[2])},
        "messages": messages,
    }
