import hashlib
import types
from unittest.mock import patch

import pytest

from app.v1 import keys
from app.v1.keys import KeyAuthError


class FakeCursor:
    def __init__(self, rows=None, rowcount=0, columns=None):
        self.rows = rows or []
        self.rowcount = rowcount
        self.columns = columns or []
        self.executed = []
        self.description = None

    def execute(self, query, params=()):
        placeholders = query.count("%s")
        if placeholders != len(params):
            raise ValueError(
                f"placeholder/param mismatch: query has {placeholders} placeholders but {len(params)} params were bound"
            )
        self.executed.append((query, params))
        self.description = [types.SimpleNamespace(name=name) for name in self.columns]

    def fetchone(self):
        return self.rows[0] if self.rows else None

    def fetchall(self):
        return list(self.rows)

    def __enter__(self):
        return self

    def __exit__(self, *args):
        return False


class FakeConnection:
    def __init__(self, rows=None, rowcount=0, columns=None):
        self.cursor_obj = FakeCursor(rows=rows, rowcount=rowcount, columns=columns)

    def cursor(self):
        return self.cursor_obj

    def __enter__(self):
        return self

    def __exit__(self, *args):
        return False


def test_generate_key_format():
    key, key_hash, prefix = keys.generate_key()
    assert key.startswith("ogpt-")
    assert len(key) > len("ogpt-")
    assert key_hash == hashlib.sha256(key.encode()).hexdigest()
    assert prefix == key[len("ogpt-"):][:8]
    assert len(prefix) == 8


def test_create_api_key_returns_plaintext_once_and_stores_hash():
    conn = FakeConnection(rows=[(11, "2026-10-07T10:00:00+00:00")], columns=["id", "created_at"])
    with patch.object(keys, "connect", return_value=conn):
        result = keys.create_api_key(user_id=5, name="ci-token")
    assert set(result) == {"id", "name", "prefix", "created_at", "key"}
    assert result["id"] == 11
    assert result["name"] == "ci-token"
    assert result["created_at"] == "2026-10-07T10:00:00+00:00"
    key = result["key"]
    assert key.startswith("ogpt-")
    assert result["prefix"] == key[len("ogpt-"):][:8]
    query, params = conn.cursor_obj.executed[0]
    assert "INSERT INTO api_keys" in query
    assert "RETURNING id, created_at" in query
    assert params[0] == 5
    assert hashlib.sha256(key.encode()).hexdigest() in params
    assert key not in query
    assert key not in str(params)


def test_list_api_keys_returns_safe_columns_only():
    conn = FakeConnection(
        rows=[
            (1, "one", "abcd1234", "2026-10-01T10:00:00+00:00", "2026-10-06T10:00:00+00:00", None),
            (2, "old", "efef5678", "2026-09-01T10:00:00+00:00", None, "2026-09-15T10:00:00+00:00"),
        ],
        columns=["id", "name", "prefix", "created_at", "last_used_at", "revoked_at"],
    )
    with patch.object(keys, "connect", return_value=conn):
        result = keys.list_api_keys(user_id=5)
    assert [item["id"] for item in result] == [1, 2]
    assert set(result[0]) == {"id", "name", "prefix", "created_at", "last_used_at", "revoked_at"}
    query, params = conn.cursor_obj.executed[0]
    assert "key_hash" not in query
    assert "FROM api_keys" in query
    assert "user_id = %s" in query
    assert params == (5,)


def test_revoke_api_key_returns_true_when_row_updated():
    conn = FakeConnection(rowcount=1)
    with patch.object(keys, "connect", return_value=conn):
        assert keys.revoke_api_key(user_id=5, key_id=3) is True
    query, params = conn.cursor_obj.executed[0]
    assert "UPDATE api_keys" in query and "revoked_at" in query
    assert "revoked_at IS NULL" in query
    assert params == (3, 5)


def test_revoke_api_key_returns_false_when_no_row_updated():
    conn = FakeConnection(rowcount=0)
    with patch.object(keys, "connect", return_value=conn):
        assert keys.revoke_api_key(user_id=5, key_id=999) is False


def test_authenticate_key_happy_path_returns_user_id():
    key, _, _ = keys.generate_key()
    conn = FakeConnection(rows=[(5,)], columns=["user_id"])
    with patch.object(keys, "connect", side_effect=[conn, conn]):
        assert keys.authenticate_key(f"Bearer {key}") == 5
    select_query, select_params = conn.cursor_obj.executed[0]
    assert "SELECT user_id FROM api_keys" in select_query
    assert "key_hash = %s" in select_query
    assert "revoked_at IS NULL" in select_query
    assert select_params == (hashlib.sha256(key.encode()).hexdigest(),)
    update_query, update_params = conn.cursor_obj.executed[1]
    assert "last_used_at" in update_query
    assert update_params == (hashlib.sha256(key.encode()).hexdigest(),)


@pytest.mark.parametrize("header", [None, "", "   "])
def test_authenticate_key_missing_header(header):
    with pytest.raises(KeyAuthError, match="Missing Authorization header"):
        keys.authenticate_key(header)


@pytest.mark.parametrize(
    "header",
    [
        "Token ogpt-abc",
        "bearer ogpt-abc",
        "Bearer",
        "Bearer ",
        "Bearer ogpt-abc extra",
        "Bearer  ogpt-abc",
        "Bearer sk-123456",
    ],
)
def test_authenticate_key_malformed_header(header):
    with pytest.raises(KeyAuthError):
        keys.authenticate_key(header)


def test_authenticate_key_unknown_key_rejected_without_update():
    conn = FakeConnection()
    with patch.object(keys, "connect", return_value=conn):
        with pytest.raises(KeyAuthError, match="Invalid or revoked API key"):
            keys.authenticate_key("Bearer ogpt-unknownkey")
    assert len(conn.cursor_obj.executed) == 1
    assert "SELECT user_id" in conn.cursor_obj.executed[0][0]


def test_authenticate_key_revoked_behaves_like_unknown():
    conn = FakeConnection()
    with patch.object(keys, "connect", return_value=conn):
        with pytest.raises(KeyAuthError, match="Invalid or revoked API key"):
            keys.authenticate_key("Bearer ogpt-revokedkey")
    assert "revoked_at IS NULL" in conn.cursor_obj.executed[0][0]


def test_authenticate_key_last_used_update_failure_does_not_fail_auth():
    key, _, _ = keys.generate_key()
    conn = FakeConnection(rows=[(7,)], columns=["user_id"])
    with patch.object(keys, "connect", side_effect=[conn, RuntimeError("db down")]):
        assert keys.authenticate_key(f"Bearer {key}") == 7
