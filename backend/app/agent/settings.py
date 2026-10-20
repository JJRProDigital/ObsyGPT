"""Loads agent execution settings (guardrails) from the database."""

import json

from .guardrails import GuardrailConfig


def load_guardrail_config() -> GuardrailConfig:
    """Reads the admin-configured guardrail limits from app_settings.

    Falls back to defaults on any failure (missing table, DB down, bad JSON)
    so a settings problem can never take the agent loop down.
    """
    value = None
    try:
        from ..db import connect

        with connect() as connection:
            with connection.cursor() as cursor:
                cursor.execute("SELECT value FROM app_settings WHERE key = 'guardrails';")
                row = cursor.fetchone()
        value = row[0] if row else None
    except Exception:  # noqa: BLE001 - settings are best-effort
        return GuardrailConfig()

    if isinstance(value, str):
        try:
            value = json.loads(value)
        except json.JSONDecodeError:
            return GuardrailConfig()
    if not isinstance(value, dict):
        return GuardrailConfig()
    return GuardrailConfig.from_settings(value)
