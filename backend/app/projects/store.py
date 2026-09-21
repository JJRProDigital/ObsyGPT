"""Persistence for projects: CRUD plus conversation/attachment links."""

from datetime import datetime

from ..db import connect


def _iso(value):
    return value.isoformat() if isinstance(value, datetime) else value


def create_project(user_id: int, name: str, description: str = "", instructions: str = "", folder_path: str | None = None) -> dict:
    with connect() as connection:
        with connection.cursor() as cursor:
            cursor.execute(
                """
                INSERT INTO projects (user_id, name, description, instructions, folder_path)
                VALUES (%s, %s, %s, %s, %s)
                RETURNING id, name, description, instructions, folder_path, archived, created_at, updated_at;
                """,
                (user_id, name, description, instructions, folder_path),
            )
            columns = [column.name for column in cursor.description]
            project = dict(zip(columns, cursor.fetchone()))
    project["created_at"] = _iso(project.get("created_at"))
    project["updated_at"] = _iso(project.get("updated_at"))
    return project


def list_projects(user_id: int, include_archived: bool = False) -> list[dict]:
    with connect() as connection:
        with connection.cursor() as cursor:
            cursor.execute(
                """
                SELECT p.id, p.name, p.description, p.instructions, p.folder_path, p.archived, p.created_at, p.updated_at,
                       (SELECT COUNT(*) FROM project_conversations pc WHERE pc.project_id = p.id) AS conversation_count,
                       (SELECT COUNT(*) FROM project_attachments pa WHERE pa.project_id = p.id) AS attachment_count,
                       (SELECT COUNT(*) FROM tasks t WHERE t.project_id = p.id AND t.status NOT IN ('completed','failed','cancelled')) AS active_task_count
                FROM projects p
                WHERE p.user_id = %s AND (%s OR p.archived = false)
                ORDER BY p.updated_at DESC, p.id DESC;
                """,
                (user_id, include_archived),
            )
            columns = [column.name for column in cursor.description]
            projects = [dict(zip(columns, row)) for row in cursor.fetchall()]
    for project in projects:
        project["created_at"] = _iso(project.get("created_at"))
        project["updated_at"] = _iso(project.get("updated_at"))
    return projects


def get_project(project_id: int, user_id: int, include_archived: bool = True) -> dict | None:
    with connect() as connection:
        with connection.cursor() as cursor:
            cursor.execute(
                "SELECT id, user_id, name, description, instructions, folder_path, archived, created_at, updated_at FROM projects WHERE id = %s AND user_id = %s AND (%s OR archived = false);",
                (project_id, user_id, include_archived),
            )
            row = cursor.fetchone()
            if not row:
                return None
            columns = [column.name for column in cursor.description]
            project = dict(zip(columns, row))
    project["created_at"] = _iso(project.get("created_at"))
    project["updated_at"] = _iso(project.get("updated_at"))
    return project


def update_project(project_id: int, user_id: int, name: str | None = None, description: str | None = None, instructions: str | None = None, folder_path: str | None = None, archived: bool | None = None) -> dict | None:
    with connect() as connection:
        with connection.cursor() as cursor:
            cursor.execute(
                """
                UPDATE projects
                SET name = COALESCE(%s, name),
                    description = COALESCE(%s, description),
                    instructions = COALESCE(%s, instructions),
                    folder_path = COALESCE(%s, folder_path),
                    archived = COALESCE(%s, archived),
                    updated_at = CURRENT_TIMESTAMP
                WHERE id = %s AND user_id = %s
                RETURNING id, name, description, instructions, folder_path, archived, created_at, updated_at;
                """,
                (name, description, instructions, folder_path, archived, project_id, user_id),
            )
            row = cursor.fetchone()
            if not row:
                return None
            columns = [column.name for column in cursor.description]
            project = dict(zip(columns, row))
    project["created_at"] = _iso(project.get("created_at"))
    project["updated_at"] = _iso(project.get("updated_at"))
    return project


def set_project_folder(project_id: int, user_id: int, folder_path: str | None) -> dict | None:
    """Sets or clears (None) the project working folder explicitly, bypassing COALESCE."""
    with connect() as connection:
        with connection.cursor() as cursor:
            cursor.execute(
                """
                UPDATE projects
                SET folder_path = %s, updated_at = CURRENT_TIMESTAMP
                WHERE id = %s AND user_id = %s
                RETURNING id, name, description, instructions, folder_path, archived, created_at, updated_at;
                """,
                (folder_path, project_id, user_id),
            )
            row = cursor.fetchone()
            if not row:
                return None
            columns = [column.name for column in cursor.description]
            project = dict(zip(columns, row))
    project["created_at"] = _iso(project.get("created_at"))
    project["updated_at"] = _iso(project.get("updated_at"))
    return project


def delete_project(project_id: int, user_id: int) -> bool:
    with connect() as connection:
        with connection.cursor() as cursor:
            cursor.execute("DELETE FROM projects WHERE id = %s AND user_id = %s;", (project_id, user_id))
            return cursor.rowcount > 0


def link_conversation(project_id: int, user_id: int, conversation_id: int) -> bool:
    with connect() as connection:
        with connection.cursor() as cursor:
            cursor.execute("SELECT 1 FROM projects WHERE id = %s AND user_id = %s;", (project_id, user_id))
            if not cursor.fetchone():
                return False
            cursor.execute("SELECT 1 FROM conversations WHERE id = %s AND user_id = %s;", (conversation_id, user_id))
            if not cursor.fetchone():
                return False
            cursor.execute(
                "INSERT INTO project_conversations (project_id, conversation_id) VALUES (%s, %s) ON CONFLICT DO NOTHING;",
                (project_id, conversation_id),
            )
            cursor.execute("UPDATE projects SET updated_at = CURRENT_TIMESTAMP WHERE id = %s;", (project_id,))
            return True


def unlink_conversation(project_id: int, user_id: int, conversation_id: int) -> bool:
    with connect() as connection:
        with connection.cursor() as cursor:
            cursor.execute("SELECT 1 FROM projects WHERE id = %s AND user_id = %s;", (project_id, user_id))
            if not cursor.fetchone():
                return False
            cursor.execute(
                "DELETE FROM project_conversations WHERE project_id = %s AND conversation_id = %s;",
                (project_id, conversation_id),
            )
            return True


def link_attachment(project_id: int, user_id: int, attachment_id: int) -> bool:
    with connect() as connection:
        with connection.cursor() as cursor:
            cursor.execute("SELECT 1 FROM projects WHERE id = %s AND user_id = %s;", (project_id, user_id))
            if not cursor.fetchone():
                return False
            cursor.execute("SELECT 1 FROM attachments WHERE id = %s AND user_id = %s;", (attachment_id, user_id))
            if not cursor.fetchone():
                return False
            cursor.execute(
                "INSERT INTO project_attachments (project_id, attachment_id) VALUES (%s, %s) ON CONFLICT DO NOTHING;",
                (project_id, attachment_id),
            )
            cursor.execute("UPDATE projects SET updated_at = CURRENT_TIMESTAMP WHERE id = %s;", (project_id,))
            return True


def unlink_attachment(project_id: int, user_id: int, attachment_id: int) -> bool:
    with connect() as connection:
        with connection.cursor() as cursor:
            cursor.execute("SELECT 1 FROM projects WHERE id = %s AND user_id = %s;", (project_id, user_id))
            if not cursor.fetchone():
                return False
            cursor.execute(
                "DELETE FROM project_attachments WHERE project_id = %s AND attachment_id = %s;",
                (project_id, attachment_id),
            )
            return True


def get_project_detail(project_id: int, user_id: int) -> dict | None:
    project = get_project(project_id, user_id)
    if not project:
        return None
    with connect() as connection:
        with connection.cursor() as cursor:
            cursor.execute(
                """
                SELECT c.id, c.title, c.created_at
                FROM project_conversations pc
                JOIN conversations c ON c.id = pc.conversation_id
                WHERE pc.project_id = %s
                ORDER BY c.created_at DESC;
                """,
                (project_id,),
            )
            columns = [column.name for column in cursor.description]
            conversations = [dict(zip(columns, row)) for row in cursor.fetchall()]
            cursor.execute(
                """
                SELECT a.id, a.file_name, a.mime_type, a.size_bytes
                FROM project_attachments pa
                JOIN attachments a ON a.id = pa.attachment_id
                WHERE pa.project_id = %s
                ORDER BY a.created_at DESC;
                """,
                (project_id,),
            )
            columns = [column.name for column in cursor.description]
            attachments = [dict(zip(columns, row)) for row in cursor.fetchall()]
    for conversation in conversations:
        conversation["created_at"] = _iso(conversation.get("created_at"))
    project["conversations"] = conversations
    project["attachments"] = attachments
    return project


def get_project_for_conversation(conversation_id: int, user_id: int) -> dict | None:
    """Returns the first project linked to a conversation, with instructions, folder and attachment ids."""
    with connect() as connection:
        with connection.cursor() as cursor:
            cursor.execute(
                """
                SELECT p.id, p.name, p.instructions, p.folder_path
                FROM project_conversations pc
                JOIN projects p ON p.id = pc.project_id
                WHERE pc.conversation_id = %s AND p.user_id = %s AND p.archived = false
                ORDER BY p.id
                LIMIT 1;
                """,
                (conversation_id, user_id),
            )
            row = cursor.fetchone()
            if not row:
                return None
            columns = [column.name for column in cursor.description]
            project = dict(zip(columns, row))
            cursor.execute(
                "SELECT attachment_id FROM project_attachments WHERE project_id = %s;",
                (project["id"],),
            )
            project["attachment_ids"] = [item[0] for item in cursor.fetchall()]
    return project


def create_project_conversation(project_id: int, user_id: int) -> dict | None:
    """Creates a brand-new conversation and links it to the project."""
    from ..chat.routes import create_conversation

    if not get_project(project_id, user_id):
        return None
    conversation = create_conversation(user_id)
    with connect() as connection:
        with connection.cursor() as cursor:
            cursor.execute(
                "INSERT INTO project_conversations (project_id, conversation_id) VALUES (%s, %s) ON CONFLICT DO NOTHING;",
                (project_id, conversation[0]),
            )
            cursor.execute("UPDATE projects SET updated_at = CURRENT_TIMESTAMP WHERE id = %s;", (project_id,))
    return {"id": conversation[0], "title": conversation[1], "created_at": _iso(conversation[2])}
