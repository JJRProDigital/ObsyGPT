from pathlib import Path

import pytest
from fastapi import HTTPException

from app.workspace import routes as workspace_routes


class FakeRequest:
    session = {"user_id": 2, "role": "user"}


def test_validate_workspace_accepts_existing_absolute_dir(tmp_path: Path):
    resolved = workspace_routes.validate_workspace_path(str(tmp_path))

    assert resolved == tmp_path.resolve()


def test_validate_workspace_rejects_relative_path():
    with pytest.raises(HTTPException) as error:
        workspace_routes.validate_workspace_path("carpeta/relativa")

    assert error.value.status_code == 400


def test_validate_workspace_rejects_missing_path(tmp_path: Path):
    with pytest.raises(HTTPException) as error:
        workspace_routes.validate_workspace_path(str(tmp_path / "no-existe"))

    assert error.value.status_code == 400


def test_validate_workspace_rejects_file(tmp_path: Path):
    file_path = tmp_path / "archivo.txt"
    file_path.write_text("x", encoding="utf-8")

    with pytest.raises(HTTPException) as error:
        workspace_routes.validate_workspace_path(str(file_path))

    assert error.value.status_code == 400


def test_get_user_workspace_falls_back_to_default(monkeypatch, tmp_path: Path):
    monkeypatch.setattr(workspace_routes, "get_user_setting", lambda user_id, key: None)
    monkeypatch.setattr(workspace_routes, "default_workspace_root", lambda: tmp_path)

    assert workspace_routes.get_user_workspace(2) == tmp_path


def test_get_user_workspace_uses_stored_path(monkeypatch, tmp_path: Path):
    monkeypatch.setattr(workspace_routes, "get_user_setting", lambda user_id, key: str(tmp_path) if key == "workspace_root" else None)

    assert workspace_routes.get_user_workspace(2) == tmp_path.resolve()


def test_set_workspace_updates_recent_list(monkeypatch, tmp_path: Path):
    stored = {}
    monkeypatch.setattr(workspace_routes, "get_user_setting", lambda user_id, key: stored.get(key))
    monkeypatch.setattr(workspace_routes, "set_user_setting", lambda user_id, key, value: stored.update({key: value}))
    monkeypatch.setattr(workspace_routes, "get_user_workspace", lambda user_id: tmp_path)
    monkeypatch.setattr(workspace_routes, "default_workspace_root", lambda: tmp_path)

    result = workspace_routes.set_workspace(workspace_routes.WorkspacePayload(path=str(tmp_path)), FakeRequest())

    assert result["workspace"] == str(tmp_path.resolve())
    assert stored["recent_workspaces"][0] == str(tmp_path.resolve())

    other = tmp_path / "otra"
    other.mkdir()
    workspace_routes.set_workspace(workspace_routes.WorkspacePayload(path=str(other)), FakeRequest())

    assert stored["recent_workspaces"][0] == str(other.resolve())
    assert str(tmp_path.resolve()) in stored["recent_workspaces"]
