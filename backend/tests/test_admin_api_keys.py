import pytest
from fastapi import HTTPException
from pydantic import ValidationError

from app.admin.api_keys import ApiKeyCreatePayload, create_api_key, list_api_keys, revoke_api_key


class FakeRequest:
    session = {"user_id": 1, "role": "admin"}


def _fake_audit_store(captured):
    class FakeAuditStore:
        def add_log(self, actor_user_id, action, target_type, target_id, metadata):
            captured.update(
                {
                    "actor_user_id": actor_user_id,
                    "action": action,
                    "target_type": target_type,
                    "target_id": target_id,
                    "metadata": metadata,
                }
            )

    return FakeAuditStore


def test_create_api_key_returns_plaintext_once_and_audits_prefix_only(monkeypatch):
    captured = {}
    calls = {}

    def fake_create(user_id, name):
        calls["args"] = (user_id, name)
        return {
            "id": 3,
            "name": name,
            "prefix": "ab12cd34",
            "created_at": "2026-10-07T10:00:00Z",
            "key": "ogpt-PLAINTEXT-SECRET",
        }

    monkeypatch.setattr("app.auth.routes.require_user", lambda request: 1)
    monkeypatch.setattr("app.v1.keys.create_api_key", fake_create)
    monkeypatch.setattr("app.audit.AuditStore", _fake_audit_store(captured))

    result = create_api_key(ApiKeyCreatePayload(name="  CI token  "), FakeRequest())

    assert calls["args"] == (1, "CI token")
    assert result == {
        "api_key": {
            "id": 3,
            "name": "CI token",
            "prefix": "ab12cd34",
            "created_at": "2026-10-07T10:00:00Z",
            "key": "ogpt-PLAINTEXT-SECRET",
        }
    }
    assert captured == {
        "actor_user_id": 1,
        "action": "api_key.created",
        "target_type": "api_key",
        "target_id": 3,
        "metadata": {"prefix": "ab12cd34", "name": "CI token"},
    }
    assert "ogpt-PLAINTEXT-SECRET" not in str(captured)


def test_list_api_keys_returns_keys_for_the_requesting_user(monkeypatch):
    captured = {}
    keys = [
        {
            "id": 9,
            "name": "n8n",
            "prefix": "ffee0011",
            "created_at": "2026-10-06T09:00:00Z",
            "last_used_at": None,
            "revoked_at": None,
        }
    ]

    def fake_list(user_id):
        captured["user_id"] = user_id
        return [dict(key) for key in keys]

    monkeypatch.setattr("app.auth.routes.require_user", lambda request: 7)
    monkeypatch.setattr("app.v1.keys.list_api_keys", fake_list)

    result = list_api_keys(FakeRequest())

    assert result == {"api_keys": keys}
    assert captured["user_id"] == 7


def test_revoke_api_key_revokes_own_key_and_audits(monkeypatch):
    captured = {}
    calls = {}

    def fake_revoke(user_id, key_id):
        calls["args"] = (user_id, key_id)
        return True

    monkeypatch.setattr("app.auth.routes.require_user", lambda request: 7)
    monkeypatch.setattr("app.v1.keys.revoke_api_key", fake_revoke)
    monkeypatch.setattr("app.audit.AuditStore", _fake_audit_store(captured))

    result = revoke_api_key(5, FakeRequest())

    assert result == {"revoked": True}
    assert calls["args"] == (7, 5)
    assert captured == {
        "actor_user_id": 7,
        "action": "api_key.revoked",
        "target_type": "api_key",
        "target_id": 5,
        "metadata": {},
    }


def test_revoke_api_key_raises_404_without_audit_when_key_missing(monkeypatch):
    captured = {}

    monkeypatch.setattr("app.auth.routes.require_user", lambda request: 7)
    monkeypatch.setattr("app.v1.keys.revoke_api_key", lambda user_id, key_id: False)
    monkeypatch.setattr("app.audit.AuditStore", _fake_audit_store(captured))

    with pytest.raises(HTTPException) as excinfo:
        revoke_api_key(999, FakeRequest())

    assert excinfo.value.status_code == 404
    assert captured == {}


def test_api_key_name_is_required_stripped_and_bounded():
    with pytest.raises(ValidationError):
        ApiKeyCreatePayload(name="")
    with pytest.raises(ValidationError):
        ApiKeyCreatePayload(name="   ")
    with pytest.raises(ValidationError):
        ApiKeyCreatePayload(name="x" * 101)

    assert ApiKeyCreatePayload(name="  CI token  ").name == "CI token"
