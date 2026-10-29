"""Persistence for event triggers."""

import json
import secrets

from ..db import connect

TRIGGER_TYPES = {"interval", "change_detection", "webhook"}
NOTIFY_CHANNELS = {"", "telegram"}

MAX_ACTIVE_TRIGGERS = 10


def count_active_triggers(user_id: int) -> int:
    with connect() as connection:
        with connection.cursor() as cursor:
            cursor.execute("SELECT COUNT(*) FROM event_triggers WHERE user_id = %s AND enabled = true;", (user_id,))
            return int(cursor.fetchone()[0])


def create_trigger(
    user_id: int,
    agent_id: int,
    name: str,
    trigger_type: str,
    config: dict,
    goal_template: str,
    notify_channel: str = "",
    notify_chat_id: int | None = None,
    cooldown_seconds: int = 0,
    readonly: bool = True,
) -> dict:
    if trigger_type not in TRIGGER_TYPES:
        raise ValueError(f"Unknown trigger type: {trigger_type}")
    if notify_channel not in NOTIFY_CHANNELS:
        raise ValueError(f"Unknown notify channel: {notify_channel}")
    webhook_secret = secrets.token_urlsafe(32) if trigger_type == "webhook" else None
    with connect() as connection:
        with connection.cursor() as cursor:
            cursor.execute(
                """
                INSERT INTO event_triggers (
                    user_id, agent_id, name, trigger_type, config, goal_template,
                    notify_channel, notify_chat_id, cooldown_seconds, readonly, webhook_secret
                )
                VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
                RETURNING id;
                """,
                (
                    user_id, agent_id, name, trigger_type,
                    json.dumps(config, ensure_ascii=False), goal_template,
                    notify_channel, notify_chat_id, cooldown_seconds, readonly, webhook_secret,
                ),
            )
            trigger_id = cursor.fetchone()[0]
    return get_trigger(trigger_id, user_id)


def _columns(cursor):
    return [column.name for column in cursor.description]


_TRIGGER_QUERY = (
    "SELECT id, user_id, agent_id, name, trigger_type, config, goal_template, notify_channel, "
    "notify_chat_id, cooldown_seconds, readonly, enabled, webhook_secret, last_fired_at, last_snapshot, created_at "
    "FROM event_triggers WHERE id = %s;"
)


def _row_to_trigger(cursor, row) -> dict:
    trigger = dict(zip(_columns(cursor), row))
    trigger["config"] = json.loads(trigger.get("config") or "{}")
    return trigger


def get_trigger(trigger_id: int, user_id: int | None = None) -> dict | None:
    with connect() as connection:
        with connection.cursor() as cursor:
            cursor.execute(_TRIGGER_QUERY, (trigger_id,))
            row = cursor.fetchone()
            if not row:
                return None
            trigger = _row_to_trigger(cursor, row)
    if user_id is not None and trigger["user_id"] != user_id:
        return None
    return trigger


def list_triggers(user_id: int) -> list[dict]:
    with connect() as connection:
        with connection.cursor() as cursor:
            cursor.execute(
                "SELECT id, user_id, agent_id, name, trigger_type, config, goal_template, notify_channel, "
                "notify_chat_id, cooldown_seconds, readonly, enabled, webhook_secret, last_fired_at, last_snapshot, created_at "
                "FROM event_triggers WHERE user_id = %s ORDER BY id DESC;",
                (user_id,),
            )
            return [_row_to_trigger(cursor, row) for row in cursor.fetchall()]


def list_enabled_triggers() -> list[dict]:
    with connect() as connection:
        with connection.cursor() as cursor:
            cursor.execute(
                "SELECT id, user_id, agent_id, name, trigger_type, config, goal_template, notify_channel, "
                "notify_chat_id, cooldown_seconds, readonly, enabled, webhook_secret, last_fired_at, last_snapshot, created_at "
                "FROM event_triggers WHERE enabled = true ORDER BY id;"
            )
            return [_row_to_trigger(cursor, row) for row in cursor.fetchall()]


def set_trigger_enabled(trigger_id: int, user_id: int, enabled: bool) -> dict | None:
    with connect() as connection:
        with connection.cursor() as cursor:
            cursor.execute(
                "UPDATE event_triggers SET enabled = %s WHERE id = %s AND user_id = %s RETURNING id;",
                (enabled, trigger_id, user_id),
            )
            if not cursor.fetchone():
                return None
    return get_trigger(trigger_id, user_id)


def delete_trigger(trigger_id: int, user_id: int) -> bool:
    with connect() as connection:
        with connection.cursor() as cursor:
            cursor.execute("DELETE FROM event_triggers WHERE id = %s AND user_id = %s RETURNING id;", (trigger_id, user_id))
            return cursor.fetchone() is not None


def mark_fired(trigger_id: int, snapshot: str | None) -> None:
    with connect() as connection:
        with connection.cursor() as cursor:
            cursor.execute(
                "UPDATE event_triggers SET last_fired_at = CURRENT_TIMESTAMP, last_snapshot = %s WHERE id = %s;",
                (snapshot, trigger_id),
            )


def record_proactive_delivery(agent_id: int, chat_id: int, content: str, task_id: int) -> None:
    """Registers a synthetic inbound row so the Telegram watcher delivers the
    task result proactively to the chat (reuses the outcome pipeline)."""
    from ..telegram import store as tg_store

    tg_store.record_inbound(agent_id, chat_id, message_id=None, sender_tg_id=None, content=content, task_id=task_id)
