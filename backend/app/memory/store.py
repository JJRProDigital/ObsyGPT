"""Persistent user memories and habits: storage."""

import re
from datetime import datetime, timezone

from ..db import connect


MAX_MEMORIES_PER_USER = 200
MEMORY_KINDS = {"memory", "habit"}
SUGGESTION_STATUSES = {"pending", "accepted", "dismissed"}
MAX_PENDING_SUGGESTIONS = 5


def _normalize_content(text: str) -> str:
    return re.sub(r"\s+", " ", text.strip().lower())


def list_memories(user_id: int, kind: str | None = None, limit: int = 100, project_id: int | None = None) -> list[dict]:
    query = "SELECT id, kind, content, created_at, updated_at FROM memories WHERE user_id = %s"
    params: list = [user_id]
    if project_id is not None:
        query += " AND project_id = %s"
        params.append(project_id)
    elif kind in MEMORY_KINDS:
        query += " AND kind = %s"
        params.append(kind)
    query += " ORDER BY updated_at DESC, id DESC LIMIT %s;"
    params.append(max(1, min(limit, 200)))

    with connect() as connection:
        with connection.cursor() as cursor:
            cursor.execute(query, params)
            columns = [column.name for column in cursor.description]
            rows = cursor.fetchall()

    memories = []
    for row in rows:
        item = dict(zip(columns, row))
        item["created_at"] = item["created_at"].isoformat() if isinstance(item["created_at"], datetime) else item["created_at"]
        item["updated_at"] = item["updated_at"].isoformat() if isinstance(item["updated_at"], datetime) else item["updated_at"]
        memories.append(item)
    return memories


def create_memory(user_id: int, content: str, kind: str = "memory", project_id: int | None = None) -> dict:
    with connect() as connection:
        with connection.cursor() as cursor:
            cursor.execute("SELECT COUNT(*) FROM memories WHERE user_id = %s;", (user_id,))
            if cursor.fetchone()[0] >= MAX_MEMORIES_PER_USER:
                raise ValueError(f"Memory limit reached ({MAX_MEMORIES_PER_USER} entries).")
            cursor.execute(
                """
                INSERT INTO memories (user_id, kind, content, project_id)
                VALUES (%s, %s, %s, %s)
                RETURNING id, kind, content, created_at, updated_at;
                """,
                (user_id, kind if kind in MEMORY_KINDS else "memory", content, project_id),
            )
            columns = [column.name for column in cursor.description]
            row = cursor.fetchone()

    memory = dict(zip(columns, row))
    memory["created_at"] = memory["created_at"].isoformat() if isinstance(memory["created_at"], datetime) else memory["created_at"]
    memory["updated_at"] = memory["updated_at"].isoformat() if isinstance(memory["updated_at"], datetime) else memory["updated_at"]
    return memory


def delete_memory(user_id: int, memory_id: int) -> bool:
    with connect() as connection:
        with connection.cursor() as cursor:
            cursor.execute("DELETE FROM memories WHERE id = %s AND user_id = %s;", (memory_id, user_id))
            return cursor.rowcount > 0


def delete_all_habits(user_id: int) -> int:
    with connect() as connection:
        with connection.cursor() as cursor:
            cursor.execute("DELETE FROM memories WHERE user_id = %s AND kind = 'habit';", (user_id,))
            return cursor.rowcount


def touch_memory(memory_id: int) -> None:
    with connect() as connection:
        with connection.cursor() as cursor:
            cursor.execute(
                "UPDATE memories SET updated_at = %s WHERE id = %s;",
                (datetime.now(timezone.utc), memory_id),
            )


def list_habit_suggestions(user_id: int, status: str = "pending", limit: int = 20) -> list[dict]:
    if status not in SUGGESTION_STATUSES:
        raise ValueError(f"status must be one of: {', '.join(sorted(SUGGESTION_STATUSES))}.")
    with connect() as connection:
        with connection.cursor() as cursor:
            cursor.execute(
                """
                SELECT id, content, evidence, source, status, conversation_id, created_at
                FROM habit_suggestions
                WHERE user_id = %s AND status = %s
                ORDER BY created_at DESC, id DESC
                LIMIT %s;
                """,
                (user_id, status, max(1, min(limit, 100))),
            )
            columns = [column.name for column in cursor.description]
            rows = cursor.fetchall()

    suggestions = []
    for row in rows:
        item = dict(zip(columns, row))
        item["created_at"] = item["created_at"].isoformat() if isinstance(item["created_at"], datetime) else item["created_at"]
        suggestions.append(item)
    return suggestions


def create_habit_suggestion(
    user_id: int,
    content: str,
    evidence: str = "",
    source: str = "model",
    conversation_id: int | None = None,
) -> dict | None:
    """Stores a pending habit suggestion unless it duplicates a habit or any previous suggestion."""
    normalized = _normalize_content(content)
    if not normalized:
        return None

    with connect() as connection:
        with connection.cursor() as cursor:
            cursor.execute("SELECT COUNT(*) FROM habit_suggestions WHERE user_id = %s AND status = 'pending';", (user_id,))
            if cursor.fetchone()[0] >= MAX_PENDING_SUGGESTIONS:
                return None

            cursor.execute("SELECT content FROM memories WHERE user_id = %s AND kind = 'habit';", (user_id,))
            habits = { _normalize_content(row[0]) for row in cursor.fetchall() }
            cursor.execute("SELECT content FROM habit_suggestions WHERE user_id = %s;", (user_id,))
            habits.update(_normalize_content(row[0]) for row in cursor.fetchall())
            if normalized in habits:
                return None

            cursor.execute(
                """
                INSERT INTO habit_suggestions (user_id, content, evidence, source, conversation_id)
                VALUES (%s, %s, %s, %s, %s)
                RETURNING id, content, evidence, source, status, conversation_id, created_at;
                """,
                (user_id, content.strip()[:400], evidence.strip()[:400], source, conversation_id),
            )
            columns = [column.name for column in cursor.description]
            row = cursor.fetchone()

    suggestion = dict(zip(columns, row))
    suggestion["created_at"] = suggestion["created_at"].isoformat() if isinstance(suggestion["created_at"], datetime) else suggestion["created_at"]
    return suggestion


def decide_habit_suggestion(user_id: int, suggestion_id: int, decision: str) -> dict | None:
    """Accepts (copies into habits) or dismisses a pending suggestion. Returns the updated row."""
    if decision not in {"accept", "dismiss"}:
        raise ValueError("decision must be 'accept' or 'dismiss'.")
    with connect() as connection:
        with connection.cursor() as cursor:
            cursor.execute(
                "SELECT content FROM habit_suggestions WHERE id = %s AND user_id = %s AND status = 'pending';",
                (suggestion_id, user_id),
            )
            row = cursor.fetchone()
            if not row:
                return None
            status = "accepted" if decision == "accept" else "dismissed"
            cursor.execute(
                "UPDATE habit_suggestions SET status = %s, decided_at = %s WHERE id = %s;",
                (status, datetime.now(timezone.utc), suggestion_id),
            )

    if decision == "accept":
        create_memory(user_id, row[0], kind="habit")
    return {"id": suggestion_id, "status": status, "content": row[0]}
