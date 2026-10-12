"""API key lifecycle and bearer authentication for the OpenAI-compatible endpoint."""

import hashlib
import secrets

from ..db import connect

KEY_PREFIX = "ogpt-"


class KeyAuthError(RuntimeError):
    """Raised when a request carries no valid, non-revoked API key."""


def generate_key() -> tuple[str, str, str]:
    key = KEY_PREFIX + secrets.token_urlsafe(32)
    key_hash = hashlib.sha256(key.encode()).hexdigest()
    prefix = key[len(KEY_PREFIX):][:8]
    return key, key_hash, prefix


def create_api_key(user_id: int, name: str) -> dict:
    key, key_hash, prefix = generate_key()
    with connect() as connection:
        with connection.cursor() as cursor:
            cursor.execute(
                """
                INSERT INTO api_keys (user_id, key_hash, prefix, name)
                VALUES (%s, %s, %s, %s)
                RETURNING id, created_at;
                """,
                (user_id, key_hash, prefix, name),
            )
            row = cursor.fetchone()
            columns = [column.name for column in cursor.description]
    created = dict(zip(columns, row))
    return {
        "id": created["id"],
        "name": name,
        "prefix": prefix,
        "created_at": created["created_at"],
        "key": key,
    }


def list_api_keys(user_id: int) -> list[dict]:
    with connect() as connection:
        with connection.cursor() as cursor:
            cursor.execute(
                """
                SELECT id, name, prefix, created_at, last_used_at, revoked_at
                FROM api_keys
                WHERE user_id = %s
                ORDER BY created_at DESC, id DESC;
                """,
                (user_id,),
            )
            columns = [column.name for column in cursor.description]
            return [dict(zip(columns, row)) for row in cursor.fetchall()]


def revoke_api_key(user_id: int, key_id: int) -> bool:
    with connect() as connection:
        with connection.cursor() as cursor:
            cursor.execute(
                """
                UPDATE api_keys
                SET revoked_at = now()
                WHERE id = %s AND user_id = %s AND revoked_at IS NULL;
                """,
                (key_id, user_id),
            )
            return cursor.rowcount > 0


def authenticate_key(authorization_header: str | None) -> int:
    if not authorization_header or not authorization_header.strip():
        raise KeyAuthError("Missing Authorization header.")
    parts = authorization_header.split(" ")
    if len(parts) != 2 or parts[0] != "Bearer" or not parts[1]:
        raise KeyAuthError("Invalid Authorization header. Expected format: 'Bearer ogpt-<key>'.")
    token = parts[1]
    if not token.startswith(KEY_PREFIX):
        raise KeyAuthError("Invalid API key. Keys must start with 'ogpt-'.")
    key_hash = hashlib.sha256(token.encode()).hexdigest()
    with connect() as connection:
        with connection.cursor() as cursor:
            cursor.execute(
                """
                SELECT user_id FROM api_keys
                WHERE key_hash = %s AND revoked_at IS NULL;
                """,
                (key_hash,),
            )
            row = cursor.fetchone()
    if row is None:
        raise KeyAuthError("Invalid or revoked API key.")
    user_id = int(row[0])
    try:
        with connect() as connection:
            with connection.cursor() as cursor:
                cursor.execute(
                    "UPDATE api_keys SET last_used_at = now() WHERE key_hash = %s;",
                    (key_hash,),
                )
    except Exception:  # noqa: BLE001 - usage tracking must never fail authentication
        pass
    return user_id
