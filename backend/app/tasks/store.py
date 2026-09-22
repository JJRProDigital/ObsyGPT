"""Persistence for background tasks and their step history."""

from datetime import datetime, timezone

from ..db import connect


def _serialize(value) -> str | None:
    return value.isoformat() if isinstance(value, datetime) else value


def create_task(user_id: int, goal: str, mode: str = "act", scheduled_at=None, agent_id: int | None = None, project_id: int | None = None, recurrence: str | None = None, status: str = "pending") -> dict:
    with connect() as connection:
        with connection.cursor() as cursor:
            cursor.execute(
                """
                INSERT INTO tasks (user_id, goal, mode, status, scheduled_at, agent_id, project_id, recurrence)
                VALUES (%s, %s, %s, %s, %s, %s, %s, %s)
                RETURNING id, goal, mode, status, scheduled_at, attempts, agent_id, project_id, recurrence, result, error, created_at, updated_at;
                """,
                (user_id, goal, mode, status, scheduled_at, agent_id, project_id, recurrence),
            )
            columns = [column.name for column in cursor.description]
            return dict(zip(columns, cursor.fetchone()))


def list_tasks(user_id: int, project_id: int | None = None) -> list[dict]:
    query = "SELECT id, goal, mode, status, scheduled_at, attempts, agent_id, project_id, recurrence, last_occurrence_at, result, error, created_at, updated_at FROM tasks WHERE user_id = %s"
    params: list = [user_id]
    if project_id is not None:
        query += " AND project_id = %s"
        params.append(project_id)
    query += " ORDER BY created_at DESC, id DESC;"
    with connect() as connection:
        with connection.cursor() as cursor:
            cursor.execute(query, tuple(params))
            columns = [column.name for column in cursor.description]
            tasks = [dict(zip(columns, row)) for row in cursor.fetchall()]
    for task in tasks:
        for key in ("scheduled_at", "last_occurrence_at", "created_at", "updated_at"):
            task[key] = _serialize(task.get(key))
    return tasks


def get_task(task_id: int, user_id: int | None = None) -> dict | None:
    query = "SELECT id, user_id, goal, mode, status, scheduled_at, attempts, next_attempt_at, agent_id, project_id, recurrence, last_occurrence_at, result, error, created_at, updated_at FROM tasks WHERE id = %s"
    params: tuple = (task_id,)
    if user_id is not None:
        query += " AND user_id = %s"
        params = (task_id, user_id)
    query += ";"
    with connect() as connection:
        with connection.cursor() as cursor:
            cursor.execute(query, params)
            row = cursor.fetchone()
            if not row:
                return None
            columns = [column.name for column in cursor.description]
            task = dict(zip(columns, row))
    for key in ("scheduled_at", "last_occurrence_at", "created_at", "updated_at"):
        task[key] = _serialize(task.get(key))
    return task


def set_task_status(task_id: int, status: str, result: str | None = None, error: str | None = None) -> None:
    with connect() as connection:
        with connection.cursor() as cursor:
            cursor.execute(
                """
                UPDATE tasks
                SET status = %s,
                    result = COALESCE(%s, result),
                    error = COALESCE(%s, error),
                    updated_at = CURRENT_TIMESTAMP
                WHERE id = %s;
                """,
                (status, result, error, task_id),
            )


def update_task_fields(task_id: int, attempts: int | None = None, next_attempt_at=None) -> None:
    with connect() as connection:
        with connection.cursor() as cursor:
            cursor.execute(
                """
                UPDATE tasks
                SET attempts = COALESCE(%s, attempts),
                    next_attempt_at = COALESCE(%s, next_attempt_at),
                    updated_at = CURRENT_TIMESTAMP
                WHERE id = %s;
                """,
                (attempts, next_attempt_at, task_id),
            )


def record_event(task_id: int, event_type: str, title: str, content: str = "") -> None:
    with connect() as connection:
        with connection.cursor() as cursor:
            cursor.execute(
                "INSERT INTO task_events (task_id, event_type, title, content) VALUES (%s, %s, %s, %s);",
                (task_id, event_type, title, content),
            )


def list_events(task_id: int) -> list[dict]:
    with connect() as connection:
        with connection.cursor() as cursor:
            cursor.execute(
                "SELECT id, event_type, title, content, created_at FROM task_events WHERE task_id = %s ORDER BY id;",
                (task_id,),
            )
            columns = [column.name for column in cursor.description]
            events = [dict(zip(columns, row)) for row in cursor.fetchall()]
    for event in events:
        event["created_at"] = _serialize(event.get("created_at"))
    return events


def list_tasks_by_status(statuses: list[str]) -> list[dict]:
    with connect() as connection:
        with connection.cursor() as cursor:
            cursor.execute(
                "SELECT id, user_id, goal, mode, status, scheduled_at, attempts, next_attempt_at, agent_id FROM tasks WHERE status = ANY(%s) ORDER BY created_at, id;",
                (statuses,),
            )
            columns = [column.name for column in cursor.description]
            return [dict(zip(columns, row)) for row in cursor.fetchall()]


def delete_task(task_id: int) -> None:
    with connect() as connection:
        with connection.cursor() as cursor:
            cursor.execute("DELETE FROM tasks WHERE id = %s;", (task_id,))


def mark_last_occurrence(task_id: int) -> None:
    with connect() as connection:
        with connection.cursor() as cursor:
            cursor.execute(
                "UPDATE tasks SET last_occurrence_at = CURRENT_TIMESTAMP WHERE id = %s;",
                (task_id,),
            )


def get_tasks_settings() -> dict:
    with connect() as connection:
        with connection.cursor() as cursor:
            cursor.execute("SELECT value FROM app_settings WHERE key = 'tasks';")
            row = cursor.fetchone()
            if not row:
                return {"max_concurrent_tasks": 1, "auto_resume_tasks": True}
            value = row[0]
            return value if isinstance(value, dict) else {}


def now_utc() -> datetime:
    return datetime.now(timezone.utc)
