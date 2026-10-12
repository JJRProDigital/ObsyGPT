"""Registration gating: only admins create accounts once bootstrapped."""

import pytest
from fastapi import HTTPException

from app.admin import users as admin_users
from app.auth import routes as auth_routes


class FakeRequest:
    def __init__(self, user_id=None, role=None):
        self.session = {"user_id": user_id, "role": role} if user_id is not None else {}
        self.client = type("Client", (), {"host": "testclient"})()


def test_registration_status_reports_open_when_no_users(monkeypatch):
    monkeypatch.setattr(auth_routes, "has_any_user", lambda: False)
    assert auth_routes.registration_status() == {"open": True}


def test_registration_status_reports_closed_when_users_exist(monkeypatch):
    monkeypatch.setattr(auth_routes, "has_any_user", lambda: True)
    assert auth_routes.registration_status() == {"open": False}


def test_register_requires_admin_once_bootstrapped(monkeypatch):
    data = auth_routes.RegisterRequest(username="new", email="new@example.com", password="passw0rd1", confirm_password="passw0rd1")
    monkeypatch.setattr(auth_routes, "has_any_user", lambda: True)
    monkeypatch.setattr(auth_routes, "get_user_role", lambda user_id: "user")

    with pytest.raises(HTTPException) as error:
        auth_routes.register(data, FakeRequest(user_id=2, role="user"))
    assert error.value.status_code == 403


def test_register_allows_admin_to_create_accounts(monkeypatch):
    data = auth_routes.RegisterRequest(username="new", email="new@example.com", password="passw0rd1", confirm_password="passw0rd1")
    monkeypatch.setattr(auth_routes, "has_any_user", lambda: True)
    monkeypatch.setattr(auth_routes, "get_user_role", lambda user_id: "admin")
    monkeypatch.setattr(auth_routes, "create_user", lambda username, email, password: (7, username, email, "user"))

    result = auth_routes.register(data, FakeRequest(user_id=1, role="admin"))

    assert result["user"]["id"] == 7


def test_register_stays_open_on_empty_instance(monkeypatch):
    data = auth_routes.RegisterRequest(username="first", email="first@example.com", password="passw0rd1", confirm_password="passw0rd1")
    monkeypatch.setattr(auth_routes, "has_any_user", lambda: False)
    monkeypatch.setattr(auth_routes, "create_user", lambda username, email, password: (1, username, email, "admin"))

    result = auth_routes.register(data, FakeRequest())

    assert result["user"]["role"] == "admin"


def test_admin_create_user_inserts_chosen_role(monkeypatch):
    monkeypatch.setattr("app.auth.routes.require_admin", lambda request: 1)
    monkeypatch.setattr(admin_users.auth, "get_user_by_username", lambda username: None)
    monkeypatch.setattr(admin_users.auth, "get_user_by_email", lambda email: None)
    captured = {}

    def fake_execute_returning(query, params):
        captured["params"] = params
        return {"id": 9, "username": params[0], "email": params[1], "role": params[3], "created_at": "now"}

    monkeypatch.setattr(admin_users.queries, "execute_returning", fake_execute_returning)
    monkeypatch.setattr(admin_users.audit_module.AuditStore, "add_log", lambda self, **kwargs: None)

    payload = admin_users.UserCreatePayload(username="NewUser", email="NEW@example.com", password="passw0rd1", role="admin")
    result = admin_users.admin_create_user(payload, FakeRequest(user_id=1, role="admin"))

    assert result["user"]["role"] == "admin"
    assert captured["params"][0] == "NewUser"
    assert captured["params"][1] == "new@example.com"


def test_admin_create_user_rejects_duplicates(monkeypatch):
    monkeypatch.setattr("app.auth.routes.require_admin", lambda request: 1)
    monkeypatch.setattr(admin_users.auth, "get_user_by_username", lambda username: {"id": 3})

    payload = admin_users.UserCreatePayload(username="taken", email="taken@example.com", password="passw0rd1")

    with pytest.raises(HTTPException) as error:
        admin_users.admin_create_user(payload, FakeRequest(user_id=1, role="admin"))
    assert error.value.status_code == 409


def test_admin_create_user_enforces_password_policy(monkeypatch):
    monkeypatch.setattr("app.auth.routes.require_admin", lambda request: 1)
    monkeypatch.setattr(admin_users.auth, "get_user_by_username", lambda username: None)
    monkeypatch.setattr(admin_users.auth, "get_user_by_email", lambda email: None)

    payload = admin_users.UserCreatePayload(username="weak", email="weak@example.com", password="solo-letras")

    with pytest.raises(HTTPException) as error:
        admin_users.admin_create_user(payload, FakeRequest(user_id=1, role="admin"))
    assert error.value.status_code == 400
