import pytest
from fastapi import HTTPException

from app.projects import routes as project_routes


class FakeRequest:
    session = {"user_id": 2, "role": "user"}


def test_slugify_strips_accents_and_symbols():
    assert project_routes._slugify("Informe Q3: análisis & ventas") == "informe-q3-analisis-ventas"
    assert project_routes._slugify("  Proyecto///raro  ") == "proyecto-raro"
    assert project_routes._slugify("español") == "espanol"


def test_enable_workspace_creates_folder_and_assigns(monkeypatch, tmp_path):
    created = {}
    monkeypatch.setattr(project_routes.store, "get_project", lambda project_id, user_id, include_archived=False: {"id": 5, "name": "Informe Q3", "folder_path": None})
    monkeypatch.setattr(project_routes.store, "get_project_detail", lambda project_id, user_id: {"id": 5, "name": "Informe Q3", "folder_path": str(tmp_path / "projects" / "informe-q3-5")})
    monkeypatch.setattr(project_routes.store, "set_project_folder", lambda project_id, user_id, path: created.update({"path": path}))
    monkeypatch.setattr("app.workspace.routes.get_user_workspace", lambda user_id: str(tmp_path))

    result = project_routes.enable_project_workspace(5, FakeRequest())

    assert created["path"].startswith(str(tmp_path / "projects"))
    assert created["path"].endswith("informe-q3-5")
    assert result["workspace"] == created["path"]


def test_enable_workspace_rejects_unknown_project(monkeypatch):
    monkeypatch.setattr(project_routes.store, "get_project", lambda project_id, user_id, include_archived=False: None)
    with pytest.raises(HTTPException) as error:
        project_routes.enable_project_workspace(99, FakeRequest())
    assert error.value.status_code == 404


def test_list_files_requires_folder(monkeypatch):
    monkeypatch.setattr(project_routes.store, "get_project", lambda project_id, user_id, include_archived=False: {"id": 5, "name": "x", "folder_path": None})
    result = project_routes.list_project_files(5, FakeRequest())
    assert result == {"folder": None, "subpath": "", "parent": None, "entries": []}


def test_list_files_jails_subpath(monkeypatch, tmp_path):
    root = tmp_path / "proj"
    (root / "docs").mkdir(parents=True)
    (root / "docs" / "a.txt").write_text("hola", encoding="utf-8")
    (root / "b.txt").write_text("mundo", encoding="utf-8")
    outside = tmp_path / "fuera.txt"
    outside.write_text("secreto", encoding="utf-8")

    monkeypatch.setattr(project_routes.store, "get_project", lambda project_id, user_id, include_archived=False: {"id": 5, "name": "x", "folder_path": str(root)})

    listing = project_routes.list_project_files(5, FakeRequest())
    names = [entry["name"] for entry in listing["entries"]]
    assert names == ["docs", "b.txt"]
    assert listing["entries"][0]["is_dir"] is True

    nested = project_routes.list_project_files(5, FakeRequest(), subpath="docs")
    assert nested["subpath"] == "docs"
    assert nested["parent"] is None
    assert [entry["name"] for entry in nested["entries"]] == ["a.txt"]

    with pytest.raises(HTTPException) as error:
        project_routes.list_project_files(5, FakeRequest(), subpath="../fuera.txt")
    assert error.value.status_code == 400


def test_unlink_workspace_requires_linked_folder(monkeypatch):
    monkeypatch.setattr(project_routes.store, "get_project", lambda project_id, user_id, include_archived=False: {"id": 5, "name": "x", "folder_path": None})
    with pytest.raises(HTTPException) as error:
        project_routes.unlink_project_workspace(5, FakeRequest())
    assert error.value.status_code == 400


def test_delete_project_file_removes_file_and_empty_dir(monkeypatch, tmp_path):
    root = tmp_path / "proj"
    (root / "docs").mkdir(parents=True)
    (root / "b.txt").write_text("hola", encoding="utf-8")
    monkeypatch.setattr(project_routes.store, "get_project", lambda project_id, user_id, include_archived=False: {"id": 5, "name": "x", "folder_path": str(root)})

    removed = project_routes.delete_project_file(5, FakeRequest(), path="b.txt")
    assert removed == {"removed": True, "name": "b.txt", "kind": "file"}
    assert not (root / "b.txt").exists()

    removed_dir = project_routes.delete_project_file(5, FakeRequest(), path="docs")
    assert removed_dir["kind"] == "folder"
    assert not (root / "docs").exists()


def test_delete_project_file_rejects_escape_and_non_empty_dir(monkeypatch, tmp_path):
    root = tmp_path / "proj"
    (root / "docs" / "keep.txt").mkdir(parents=True)
    (root / "keep.txt").write_text("x", encoding="utf-8")
    outside = tmp_path / "fuera.txt"
    outside.write_text("x", encoding="utf-8")
    monkeypatch.setattr(project_routes.store, "get_project", lambda project_id, user_id, include_archived=False: {"id": 5, "name": "x", "folder_path": str(root)})

    with pytest.raises(HTTPException) as error:
        project_routes.delete_project_file(5, FakeRequest(), path="../fuera.txt")
    assert error.value.status_code == 400

    with pytest.raises(HTTPException) as error:
        project_routes.delete_project_file(5, FakeRequest(), path="docs")
    assert error.value.status_code == 400
    assert (root / "docs" / "keep.txt").exists()

    with pytest.raises(HTTPException) as error:
        project_routes.delete_project_file(5, FakeRequest(), path="no-existe.txt")
    assert error.value.status_code == 404


def test_delete_project_removes_managed_folder_but_not_custom(monkeypatch, tmp_path):
    managed_root = tmp_path / "projects"
    managed = managed_root / "mi-proy-5"
    managed.mkdir(parents=True)
    (managed / "datos.txt").write_text("x", encoding="utf-8")
    custom = tmp_path / "otra-carpeta"
    custom.mkdir()
    (custom / "inalterable.txt").write_text("x", encoding="utf-8")

    monkeypatch.setattr(project_routes.store, "get_project", lambda project_id, user_id, include_archived=False: {"id": 5, "name": "x", "folder_path": str(managed)})
    monkeypatch.setattr(project_routes.store, "delete_project", lambda project_id, user_id: True)
    monkeypatch.setattr("app.workspace.routes.get_user_workspace", lambda user_id: str(tmp_path))

    result = project_routes.delete_project(5, FakeRequest())
    assert result["workspace_removed"] is True
    assert not managed.exists()

    monkeypatch.setattr(project_routes.store, "get_project", lambda project_id, user_id, include_archived=False: {"id": 6, "name": "x", "folder_path": str(custom)})
    result_custom = project_routes.delete_project(6, FakeRequest())
    assert result_custom["workspace_removed"] is False
    assert (custom / "inalterable.txt").exists()

    monkeypatch.setattr(project_routes.store, "get_project", lambda project_id, user_id, include_archived=False: {"id": 7, "name": "x", "folder_path": None})
    result_none = project_routes.delete_project(7, FakeRequest())
    assert result_none["workspace_removed"] is False
