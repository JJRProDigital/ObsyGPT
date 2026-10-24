import pytest
from fastapi import HTTPException

from app.auth.routes import get_session, require_admin, validate_password_policy


class FakeRequest:
    def __init__(self, session):
        self.session = session


def test_require_admin_allows_admin_session(monkeypatch):
    monkeypatch.setattr("app.auth.routes.get_user_role", lambda user_id: "admin")
    request = FakeRequest({"user_id": 1, "username": "admin", "role": "admin"})

    assert require_admin(request) == 1


def test_require_admin_rejects_non_admin_session(monkeypatch):
    monkeypatch.setattr("app.auth.routes.get_user_role", lambda user_id: "user")
    request = FakeRequest({"user_id": 2, "username": "user", "role": "user"})

    with pytest.raises(HTTPException) as error:
        require_admin(request)

    assert error.value.status_code == 403
    assert error.value.detail == "Admin access is required."


def test_require_admin_rejects_missing_session():
    request = FakeRequest({})

    with pytest.raises(HTTPException) as error:
        require_admin(request)

    assert error.value.status_code == 401


def test_require_admin_uses_current_database_role(monkeypatch):
    monkeypatch.setattr("app.auth.routes.get_user_role", lambda user_id: "user", raising=False)
    request = FakeRequest({"user_id": 1, "username": "admin", "role": "admin"})

    with pytest.raises(HTTPException) as error:
        require_admin(request)

    assert error.value.status_code == 403


def test_get_session_uses_current_database_role(monkeypatch):
    monkeypatch.setattr("app.auth.routes.get_user_role", lambda user_id: "user")
    request = FakeRequest({"user_id": 1, "username": "admin", "role": "admin"})

    session = get_session(request)

    assert session["user"]["role"] == "user"
    assert request.session["role"] == "user"


def test_get_session_clears_session_when_user_no_longer_exists(monkeypatch):
    monkeypatch.setattr("app.auth.routes.get_user_role", lambda user_id: None)
    request = FakeRequest({"user_id": 99, "username": "deleted", "role": "admin"})

    session = get_session(request)

    assert session == {"logged_in": False, "user": None}
    assert request.session == {}


def test_validate_password_policy_accepts_strong_password():
    validate_password_policy("Password123!")


def test_validate_password_policy_rejects_short_password():
    with pytest.raises(HTTPException) as error:
        validate_password_policy("short1!")

    assert error.value.status_code == 400
    assert "at least 8 characters" in error.value.detail


def test_validate_password_policy_rejects_password_without_number():
    with pytest.raises(HTTPException) as error:
        validate_password_policy("Password!")

    assert "one number" in error.value.detail
