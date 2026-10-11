from pathlib import Path

from app.files.routes import remove_storage_file


def test_remove_storage_file_deletes_inside_root(tmp_path):
    root = tmp_path / "uploads"
    root.mkdir()
    stored = root / "doc-abc.txt"
    stored.write_text("hola", encoding="utf-8")

    assert remove_storage_file(str(stored), root) is True
    assert not stored.exists()


def test_remove_storage_file_refuses_outside_root(tmp_path):
    root = tmp_path / "uploads"
    root.mkdir()
    outside = tmp_path / "secreto.txt"
    outside.write_text("no tocarme", encoding="utf-8")

    assert remove_storage_file(str(outside), root) is False
    assert outside.exists()

    assert remove_storage_file(str(tmp_path / ".." / "otro.txt"), root) is False


def test_remove_storage_file_tolerates_missing_and_none(tmp_path):
    root = tmp_path / "uploads"
    root.mkdir()
    assert remove_storage_file(None, root) is False
    assert remove_storage_file("", root) is False
    assert remove_storage_file(str(root / "no-existe.txt"), root) is False
