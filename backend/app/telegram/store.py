"""Persistence for the Telegram gateway: agent bot config and message log."""

from ..db import connect


def list_telegram_agents() -> list[dict]:
    """Agents with a Telegram bot configured (enabled or not) for gateway reconciliation."""
    with connect() as connection:
        with connection.cursor() as cursor:
            cursor.execute(
                """
                SELECT id, name, telegram_enabled, telegram_bot_token, telegram_allowlist
                FROM agents
                WHERE telegram_bot_token IS NOT NULL;
                """
            )
            columns = [column.name for column in cursor.description]
            return [dict(zip(columns, row)) for row in cursor.fetchall()]


def set_agent_telegram_config(agent_id: int, *, enabled: bool, encrypted_token: str | None, token_cleared: bool, allowlist: str) -> dict:
    """Upserts the Telegram configuration of an agent. encrypted_token None keeps the stored one."""
    from ..connectors.crypto import encrypt_credential

    with connect() as connection:
        with connection.cursor() as cursor:
            if token_cleared:
                cursor.execute(
                    "UPDATE agents SET telegram_enabled = %s, telegram_bot_token = NULL, telegram_allowlist = %s WHERE id = %s;",
                    (enabled, allowlist, agent_id),
                )
            elif encrypted_token is not None:
                cursor.execute(
                    "UPDATE agents SET telegram_enabled = %s, telegram_bot_token = %s, telegram_allowlist = %s WHERE id = %s;",
                    (enabled, encrypt_credential(encrypted_token), allowlist, agent_id),
                )
            else:
                cursor.execute(
                    "UPDATE agents SET telegram_enabled = %s, telegram_allowlist = %s WHERE id = %s;",
                    (enabled, allowlist, agent_id),
                )
            return get_agent_telegram_config(agent_id, connection=connection)


def get_agent_telegram_config(agent_id: int, connection=None) -> dict | None:
    query = (
        "SELECT id, name, telegram_enabled, telegram_bot_token, telegram_allowlist FROM agents WHERE id = %s;"
    )
    if connection is not None:
        with connection.cursor() as cursor:
            cursor.execute(query, (agent_id,))
            row = cursor.fetchone()
            columns = [column.name for column in cursor.description] if cursor.description else []
            return dict(zip(columns, row)) if row else None
    with connect() as connection:
        with connection.cursor() as cursor:
            cursor.execute(query, (agent_id,))
            row = cursor.fetchone()
            columns = [column.name for column in cursor.description] if cursor.description else []
            return dict(zip(columns, row)) if row else None


def get_agent_bot_token(agent_id: int) -> str | None:
    """Decrypted bot token, or None when the agent has none stored."""
    from ..connectors.crypto import decrypt_credential

    config = get_agent_telegram_config(agent_id)
    if not config or not config.get("telegram_bot_token"):
        return None
    return decrypt_credential(config["telegram_bot_token"])


def resolve_allowlisted_user(raw_allowlist: str, telegram_user_id: int) -> str | None:
    """Returns the ObsyGPT username mapped to a Telegram user id, or None when not allowlisted."""
    from .gateway import parse_allowlist

    return parse_allowlist(raw_allowlist).get(telegram_user_id)


def resolve_user_id_by_username(username: str) -> int | None:
    with connect() as connection:
        with connection.cursor() as cursor:
            cursor.execute("SELECT id FROM users WHERE username = %s;", (username,))
            row = cursor.fetchone()
            return int(row[0]) if row else None


def record_inbound(agent_id: int, chat_id: int, message_id: int | None, sender_tg_id: int | None, content: str, task_id: int | None = None, via_voice: bool = False) -> int | None:
    """Stores an inbound Telegram message; returns the row id, or None when already processed (dedupe)."""
    with connect() as connection:
        with connection.cursor() as cursor:
            cursor.execute(
                """
                INSERT INTO telegram_messages (agent_id, chat_id, message_id, direction, sender_tg_id, content, task_id, delivered, via_voice)
                VALUES (%s, %s, %s, 'inbound', %s, %s, %s, false, %s)
                ON CONFLICT DO NOTHING
                RETURNING id;
                """,
                (agent_id, chat_id, message_id, sender_tg_id, content, task_id, via_voice),
            )
            row = cursor.fetchone()
            return int(row[0]) if row else None


def attach_task(inbound_row_id: int, task_id: int) -> None:
    with connect() as connection:
        with connection.cursor() as cursor:
            cursor.execute("UPDATE telegram_messages SET task_id = %s WHERE id = %s;", (task_id, inbound_row_id))


def record_outbound(agent_id: int, chat_id: int, content: str) -> None:
    with connect() as connection:
        with connection.cursor() as cursor:
            cursor.execute(
                "INSERT INTO telegram_messages (agent_id, chat_id, direction, content) VALUES (%s, %s, 'outbound', %s);",
                (agent_id, chat_id, content),
            )


def recent_history(agent_id: int, chat_id: int, limit: int = 8) -> list[dict]:
    with connect() as connection:
        with connection.cursor() as cursor:
            cursor.execute(
                """
                SELECT direction, content FROM telegram_messages
                WHERE agent_id = %s AND chat_id = %s
                ORDER BY id DESC LIMIT %s;
                """,
                (agent_id, chat_id, limit),
            )
            rows = [{"direction": row[0], "content": row[1]} for row in cursor.fetchall()]
    return list(reversed(rows))


def pending_deliveries() -> list[dict]:
    """Inbound rows whose linked task changed state and still needs a Telegram notification."""
    with connect() as connection:
        with connection.cursor() as cursor:
            cursor.execute(
                """
                SELECT tm.id, tm.agent_id, tm.chat_id, tm.task_id, tm.notified_status, tm.via_voice,
                       t.status AS task_status, t.result, t.error, t.user_id
                FROM telegram_messages tm
                LEFT JOIN tasks t ON t.id = tm.task_id
                WHERE tm.direction = 'inbound' AND tm.delivered = false;
                """
            )
            columns = [column.name for column in cursor.description]
            return [dict(zip(columns, row)) for row in cursor.fetchall()]


def mark_notified(row_id: int, notified_status: str, delivered: bool = False) -> None:
    with connect() as connection:
        with connection.cursor() as cursor:
            cursor.execute(
                "UPDATE telegram_messages SET notified_status = %s, delivered = %s WHERE id = %s;",
                (notified_status, delivered, row_id),
            )
