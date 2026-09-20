from datetime import datetime, timezone

from ..db import connect


class TraceStore:
    def create_run(
        self,
        user_id: int,
        conversation_id: int,
        message_id: int | None,
        agent_id: int | None,
        workflow_id: int | None = None,
        parent_run_id: int | None = None,
    ) -> int:
        with connect() as connection:
            with connection.cursor() as cursor:
                cursor.execute(
                    """
                    INSERT INTO agent_runs (user_id, conversation_id, message_id, agent_id, workflow_id, parent_run_id, status)
                    VALUES (%s, %s, %s, %s, %s, %s, 'running')
                    RETURNING id;
                    """,
                    (user_id, conversation_id, message_id, agent_id, workflow_id, parent_run_id),
                )
                return cursor.fetchone()[0]

    def add_event(self, agent_run_id: int, event_type: str, title: str, content: str = "") -> None:
        with connect() as connection:
            with connection.cursor() as cursor:
                cursor.execute(
                    """
                    INSERT INTO agent_events (agent_run_id, event_type, title, content)
                    VALUES (%s, %s, %s, %s);
                    """,
                    (agent_run_id, event_type, title, content),
                )

    def complete_run(self, agent_run_id: int, final_response: str) -> None:
        with connect() as connection:
            with connection.cursor() as cursor:
                cursor.execute(
                    """
                    UPDATE agent_runs
                    SET status = 'completed', final_response = %s, completed_at = %s
                    WHERE id = %s;
                    """,
                    (final_response, datetime.now(timezone.utc), agent_run_id),
                )

    def fail_run(self, agent_run_id: int, error_message: str) -> None:
        with connect() as connection:
            with connection.cursor() as cursor:
                cursor.execute(
                    """
                    UPDATE agent_runs
                    SET status = 'failed', final_response = %s, completed_at = %s
                    WHERE id = %s;
                    """,
                    (error_message, datetime.now(timezone.utc), agent_run_id),
                )

    def pause_run(self, agent_run_id: int, note: str = "") -> None:
        with connect() as connection:
            with connection.cursor() as cursor:
                cursor.execute(
                    """
                    UPDATE agent_runs
                    SET status = 'awaiting_approval', final_response = %s
                    WHERE id = %s;
                    """,
                    (note, agent_run_id),
                )

    def add_source(self, agent_run_id: int, url: str, title: str, snippet: str) -> None:
        with connect() as connection:
            with connection.cursor() as cursor:
                cursor.execute(
                    """
                    INSERT INTO sources (agent_run_id, url, title, snippet)
                    VALUES (%s, %s, %s, %s);
                    """,
                    (agent_run_id, url, title, snippet[:1000]),
                )

    def add_tool_call(
        self,
        agent_run_id: int,
        skill_name: str,
        input_summary: str,
        output_summary: str,
        status: str,
    ) -> None:
        with connect() as connection:
            with connection.cursor() as cursor:
                cursor.execute(
                    """
                    INSERT INTO tool_calls (agent_run_id, skill_name, input_summary, output_summary, status)
                    VALUES (%s, %s, %s, %s, %s);
                    """,
                    (agent_run_id, skill_name, input_summary[:1000], output_summary[:1000], status),
                )

    def add_mcp_call(
        self,
        agent_run_id: int | None,
        mcp_server_id: int,
        tool_name: str,
        input_summary: str,
        output_summary: str,
        status: str,
    ) -> None:
        with connect() as connection:
            with connection.cursor() as cursor:
                cursor.execute(
                    """
                    INSERT INTO mcp_calls (agent_run_id, mcp_server_id, tool_name, input_summary, output_summary, status)
                    VALUES (%s, %s, %s, %s, %s, %s);
                    """,
                    (agent_run_id, mcp_server_id, tool_name, input_summary[:1000], output_summary[:1000], status),
                )
