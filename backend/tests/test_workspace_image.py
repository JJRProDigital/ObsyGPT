"""Tests for serving agent-generated workspace images (app.files.routes)."""

from pathlib import Path

import pytest
from fastapi import HTTPException

from app.files import routes as files_routes


@pytest.fixture()
def workspace(tmp_path, monkeypatch):
    root = tmp_path / "workspace"
    (root / "flow-images").mkdir(parents=True)
    (root / "flow-images" / "cat.jpg").write_bytes(b"\xff\xd8fake")
    (root / "flow-images" / "notes.txt").write_text("hola")
    monkeypatch.setattr(files_routes, "get_user_workspace", lambda user_id: root)
    return root


def test_resolve_workspace_image_serves_files_inside_workspace(workspace):
    target = files_routes.resolve_workspace_image(1, str(workspace / "flow-images" / "cat.jpg"))
    assert target.name == "cat.jpg"


def test_resolve_workspace_image_rejects_outside_paths(workspace):
    with pytest.raises(HTTPException) as error:
        files_routes.resolve_workspace_image(1, "C:/Windows/system.ini")
    assert error.value.status_code == 403


def test_resolve_workspace_image_rejects_traversal(workspace):
    with pytest.raises(HTTPException) as error:
        files_routes.resolve_workspace_image(1, str(workspace / "flow-images" / ".." / ".." / "secrets.png"))
    assert error.value.status_code == 403


def test_resolve_workspace_image_rejects_non_images(workspace):
    with pytest.raises(HTTPException) as error:
        files_routes.resolve_workspace_image(1, str(workspace / "flow-images" / "notes.txt"))
    assert error.value.status_code == 404


def test_resolve_workspace_image_rejects_missing_files(workspace):
    with pytest.raises(HTTPException) as error:
        files_routes.resolve_workspace_image(1, str(workspace / "flow-images" / "nope.jpg"))
    assert error.value.status_code == 404
