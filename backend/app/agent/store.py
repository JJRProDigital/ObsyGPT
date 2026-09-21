"""Persistence helpers for the agent loop: tool permissions, approvals, run state."""

import json

from ..db import connect
from ..providers import ChatMessage


def get_agent_tool_permissions(agent_id: int | None) -> dict[str, bool]:
    if agent_id is None:
        return {}
    with connect() as connection:
        with connection.cursor() as cursor:
            cursor.execute(
                "SELECT tool_name, allowed FROM agent_tool_permissions WHERE agent_id = %s;",
                (agent_id,),
            )
            return {row[0]: bool(row[1]) for row in cursor.fetchall()}


def create_tool_approval(
    agent_run_id: int,
    user_id: int,
    conversation_id: int | None,
    tool_name: str,
    args: dict,
    task_id: int | None = None,
) -> int:
    with connect() as connection:
        with connection.cursor() as cursor:
            cursor.execute(
                """
                INSERT INTO tool_approvals (agent_run_id, user_id, conversation_id, tool_name, args, task_id)
                VALUES (%s, %s, %s, %s, %s, %s)
                RETURNING id;
                """,
                (agent_run_id, user_id, conversation_id, tool_name, json.dumps(args, default=str), task_id),
            )
            return cursor.fetchone()[0]


def list_pending_task_approvals(user_id: int, task_id: int) -> list[dict]:
    with connect() as connection:
        with connection.cursor() as cursor:
            cursor.execute(
                """
                SELECT id, agent_run_id, conversation_id, task_id, tool_name, args, created_at
                FROM tool_approvals
                WHERE user_id = %s AND task_id = %s AND status = 'pending'
                ORDER BY id;
                """,
                (user_id, task_id),
            )
            columns = [column.name for column in cursor.description]
            return [dict(zip(columns, row)) for row in cursor.fetchall()]


def list_pending_approvals_by_user(user_id: int, task_only: bool = False) -> list[dict]:
    query = """
        SELECT id, agent_run_id, conversation_id, task_id, tool_name, args, created_at
        FROM tool_approvals
        WHERE user_id = %s AND status = 'pending'
    """
    if task_only:
        query += " AND task_id IS NOT NULL"
    query += " ORDER BY id;"
    with connect() as connection:
        with connection.cursor() as cursor:
            cursor.execute(query, (user_id,))
            columns = [column.name for column in cursor.description]
            return [dict(zip(columns, row)) for row in cursor.fetchall()]


def list_pending_approvals(user_id: int, conversation_id: int) -> list[dict]:
    with connect() as connection:
        with connection.cursor() as cursor:
            cursor.execute(
                """
                SELECT id, agent_run_id, conversation_id, tool_name, args, created_at
                FROM tool_approvals
                WHERE user_id = %s AND conversation_id = %s AND status = 'pending'
                ORDER BY id;
                """,
                (user_id, conversation_id),
            )
            columns = [column.name for column in cursor.description]
            return [dict(zip(columns, row)) for row in cursor.fetchall()]


def decide_approval(approval_id: int, user_id: int, status: str) -> dict | None:
    if status not in {"approved", "denied"}:
        return None
    with connect() as connection:
        with connection.cursor() as cursor:
            cursor.execute(
                """
                UPDATE tool_approvals
                SET status = %s, decided_at = CURRENT_TIMESTAMP
                WHERE id = %s AND user_id = %s AND status = 'pending'
                RETURNING id, agent_run_id, user_id, conversation_id, tool_name, args;
                """,
                (status, approval_id, user_id),
            )
            row = cursor.fetchone()
            if not row:
                return None
            columns = [column.name for column in cursor.description]
            result = dict(zip(columns, row))
    if isinstance(result.get("args"), str):
        try:
            result["args"] = json.loads(result["args"])
        except json.JSONDecodeError:
            result["args"] = {}
    return result


def save_run_state(agent_run_id: int, messages: list[ChatMessage], iterations: int, tool_call_count: int, thought_text: str) -> None:
    payload = json.dumps([{"role": message.role, "content": message.content} for message in messages])
    with connect() as connection:
        with connection.cursor() as cursor:
            cursor.execute(
                """
                INSERT INTO agent_run_state (agent_run_id, messages, iterations, tool_call_count, thought_text, updated_at)
                VALUES (%s, %s, %s, %s, %s, CURRENT_TIMESTAMP)
                ON CONFLICT (agent_run_id) DO UPDATE SET
                    messages = EXCLUDED.messages,
                    iterations = EXCLUDED.iterations,
                    tool_call_count = EXCLUDED.tool_call_count,
                    thought_text = EXCLUDED.thought_text,
                    updated_at = CURRENT_TIMESTAMP;
                """,
                (agent_run_id, payload, iterations, tool_call_count, thought_text),
            )


def load_run_state(agent_run_id: int) -> dict | None:
    with connect() as connection:
        with connection.cursor() as cursor:
            cursor.execute(
                """
                SELECT agent_run_id, messages, iterations, tool_call_count, thought_text
                FROM agent_run_state
                WHERE agent_run_id = %s;
                """,
                (agent_run_id,),
            )
            row = cursor.fetchone()
            if not row:
                return None
            columns = [column.name for column in cursor.description]
            state = dict(zip(columns, row))
    if isinstance(state.get("messages"), str):
        try:
            state["messages"] = json.loads(state["messages"])
        except json.JSONDecodeError:
            state["messages"] = []
    return state


def set_run_status(agent_run_id: int, status: str) -> None:
    with connect() as connection:
        with connection.cursor() as cursor:
            cursor.execute("UPDATE agent_runs SET status = %s WHERE id = %s;", (status, agent_run_id))


def get_run_config(agent_run_id: int) -> dict | None:
    with connect() as connection:
        with connection.cursor() as cursor:
            cursor.execute(
                """
                SELECT
                    ar.id AS run_id,
                    ar.conversation_id,
                    ar.user_id,
                    a.id AS agent_id,
                    a.system_prompt,
                    p.provider_type,
                    p.base_url,
                    p.api_key_env,
                    m.model_name,
                    a.temperature
                FROM agent_runs ar
                JOIN agents a ON a.id = ar.agent_id
                JOIN providers p ON p.id = a.provider_id
                JOIN models m ON m.id = a.model_id
                WHERE ar.id = %s;
                """,
                (agent_run_id,),
            )
            row = cursor.fetchone()
            if not row:
                return None
            columns = [column.name for column in cursor.description]
            return dict(zip(columns, row))
