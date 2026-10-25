import pytest
from fastapi import HTTPException

from app.memory.context import build_memory_context, format_memory_block
from app.memory.routes import MemoryPayload, add_memory, get_memories, remove_memory
from app.memory.store import MEMORY_KINDS


class FakeRequest:
    session = {"user_id": 2, "role": "user"}


def test_format_memory_block_lists_items():
    block = format_memory_block([{"content": "Prefiere respuestas breves"}, {"content": "Trabaja en ObsyGPT"}], "Titulo")

    assert block.startswith("## Titulo")
    assert "- Prefiere respuestas breves" in block
    assert "- Trabaja en ObsyGPT" in block


def test_format_memory_block_truncates_long_items():
    block = format_memory_block([{"content": "x" * 500}], "Titulo")

    assert "..." in block
    assert len(block) < 400


def test_build_memory_context_combines_memories_and_habits(monkeypatch):
    monkeypatch.setattr(
        "app.memory.context.list_memories",
        lambda user_id, kind=None, limit=30: (
            [{"content": "usuario trabaja en obsygpt"}] if kind == "memory" else [{"content": "responde en espanol"}]
        ),
    )

    context = build_memory_context(2)

    assert "Memorias persistentes" in context
    assert "Habitos y preferencias" in context
    assert "usuario trabaja en obsygpt" in context
    assert "responde en espanol" in context


def test_build_memory_context_empty_when_no_data(monkeypatch):
    monkeypatch.setattr("app.memory.context.list_memories", lambda user_id, kind=None, limit=30: [])

    assert build_memory_context(2) == ""


def test_build_memory_context_tolerates_store_failure(monkeypatch):
    def boom(user_id, kind=None, limit=30):
        raise RuntimeError("db down")

    monkeypatch.setattr("app.memory.context.list_memories", boom)

    assert build_memory_context(2) == ""


def test_build_memory_context_includes_display_name(monkeypatch):
    monkeypatch.setattr(
        "app.memory.context.list_memories",
        lambda user_id, kind=None, limit=30: ([{"content": "dato"}] if kind == "memory" else []),
    )
    monkeypatch.setattr(
        "app.workspace.routes.get_user_preferences",
        lambda user_id: {"display_name": "Juanjo", "accent": "gold", "memory_max": 30, "tool_policies": {}},
    )

    context = build_memory_context(2)

    assert "El usuario se llama Juanjo" in context


def test_build_memory_context_respects_memory_max(monkeypatch):
    captured = {}

    def fake_list(user_id, kind=None, limit=30):
        captured[kind] = limit
        return []

    monkeypatch.setattr("app.memory.context.list_memories", fake_list)
    monkeypatch.setattr(
        "app.workspace.routes.get_user_preferences",
        lambda user_id: {"display_name": "", "accent": "gold", "memory_max": 7, "tool_policies": {}},
    )

    build_memory_context(2)

    assert captured == {"memory": 7, "habit": 7}


def test_reset_habits_removes_only_habits(monkeypatch):
    captured = {}
    monkeypatch.setattr("app.memory.routes.store.delete_all_habits", lambda user_id: 4)

    from app.memory.routes import reset_habits

    result = reset_habits(FakeRequest())

    assert result == {"removed": 4}


def test_memory_payload_validates_kind_and_content():
    payload = MemoryPayload(content="Prefiere formato markdown", kind="habit")

    assert payload.kind == "habit"

    with pytest.raises(Exception):
        MemoryPayload(content="x", kind="otro")
    with pytest.raises(Exception):
        MemoryPayload(content="   ", kind="memory")


def test_add_memory_creates_and_returns_memory(monkeypatch):
    captured = {}

    def fake_create(user_id, content, kind, project_id=None):
        captured.update({"user_id": user_id, "content": content, "kind": kind})
        return {"id": 1, "kind": kind, "content": content, "created_at": "t", "updated_at": "t"}

    monkeypatch.setattr("app.memory.routes.store.create_memory", fake_create)

    result = add_memory(MemoryPayload(content="dato"), FakeRequest())

    assert result["memory"]["id"] == 1
    assert captured == {"user_id": 2, "content": "dato", "kind": "memory"}


def test_add_memory_maps_limit_error_to_409(monkeypatch):
    monkeypatch.setattr(
        "app.memory.routes.store.create_memory",
        lambda user_id, content, kind, project_id=None: (_ for _ in ()).throw(ValueError("Memory limit reached (200 entries).")),
    )

    with pytest.raises(HTTPException) as error:
        add_memory(MemoryPayload(content="dato"), FakeRequest())

    assert error.value.status_code == 409


def test_get_memories_rejects_bad_kind():
    with pytest.raises(HTTPException) as error:
        get_memories(kind="mal", request=FakeRequest())

    assert error.value.status_code == 400


def test_remove_memory_404_when_not_owned(monkeypatch):
    monkeypatch.setattr("app.memory.routes.store.delete_memory", lambda user_id, memory_id: False)

    with pytest.raises(HTTPException) as error:
        remove_memory(99, FakeRequest())

    assert error.value.status_code == 404


def test_memory_kinds_constant():
    assert MEMORY_KINDS == {"memory", "habit"}
