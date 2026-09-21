from datetime import datetime, timezone

import pytest

from fastapi import HTTPException
from pydantic import ValidationError

from app.chat import routes as chat_routes
from app.chat.routes import ConversationFolderPayload, FolderPayload, MessageEditPayload


class FakeRequest:
    session = {"user_id": 1}


def _now():
    return datetime.now(timezone.utc)


def test_list_conversations_prefers_custom_title_as_label(monkeypatch):
    rows = [
        (11, "Mi titulo custom", _now(), 3, 7),
        (12, "", _now(), 4, None),
    ]
    monkeypatch.setattr(chat_routes, "get_conversations", lambda user_id: rows)

    result = chat_routes.list_conversations(FakeRequest())

    labels = {conversation["id"]: conversation["label"] for conversation in result["conversations"]}
    assert labels[11] == "Mi titulo custom"
    assert labels[12].startswith("Chat 4 - ")
    assert result["conversations"][0]["folder_id"] == 7
    assert result["conversations"][1]["folder_id"] is None


def test_folder_crud_endpoints(monkeypatch):
    monkeypatch.setattr(chat_routes, "list_chat_folders", lambda user_id: [{"id": 1, "name": "Trabajo", "conversation_count": 2}])
    monkeypatch.setattr(chat_routes, "create_chat_folder", lambda user_id, name: {"id": 2, "name": name, "conversation_count": 0})
    monkeypatch.setattr(chat_routes, "rename_chat_folder", lambda folder_id, user_id, name: {"id": folder_id, "name": name})
    monkeypatch.setattr(chat_routes, "delete_chat_folder", lambda folder_id, user_id: True)

    assert chat_routes.get_folders(FakeRequest()) == {"folders": [{"id": 1, "name": "Trabajo", "conversation_count": 2}]}
    assert chat_routes.post_folder(FolderPayload(name="Personal"), FakeRequest()) == {"folder": {"id": 2, "name": "Personal", "conversation_count": 0}}
    assert chat_routes.patch_folder(1, FolderPayload(name="Nuevo"), FakeRequest()) == {"folder": {"id": 1, "name": "Nuevo"}}
    assert chat_routes.remove_folder(1, FakeRequest()) == {"id": 1, "deleted": True}


def test_remove_folder_returns_404_when_missing(monkeypatch):
    monkeypatch.setattr(chat_routes, "delete_chat_folder", lambda folder_id, user_id: False)
    with pytest.raises(HTTPException) as error:
        chat_routes.remove_folder(99, FakeRequest())
    assert error.value.status_code == 404


def test_move_conversation_updates_folder(monkeypatch):
    captured = {}

    def fake_move(conversation_id, user_id, folder_id):
        captured.update({"conversation_id": conversation_id, "folder_id": folder_id})
        return {"id": conversation_id, "folder_id": folder_id}

    monkeypatch.setattr(chat_routes, "move_conversation_to_folder", fake_move)
    result = chat_routes.set_conversation_folder(5, ConversationFolderPayload(folder_id=3), FakeRequest())

    assert result == {"id": 5, "folder_id": 3}
    assert captured == {"conversation_id": 5, "folder_id": 3}

    result_none = chat_routes.set_conversation_folder(5, ConversationFolderPayload(folder_id=None), FakeRequest())
    assert result_none == {"id": 5, "folder_id": None}


def test_move_conversation_404_when_folder_missing(monkeypatch):
    monkeypatch.setattr(chat_routes, "move_conversation_to_folder", lambda conversation_id, user_id, folder_id: None)
    with pytest.raises(HTTPException) as error:
        chat_routes.set_conversation_folder(5, ConversationFolderPayload(folder_id=3), FakeRequest())
    assert error.value.status_code == 404


def test_edit_message_endpoint(monkeypatch):
    monkeypatch.setattr(chat_routes, "update_user_message", lambda message_id, conversation_id, user_id, content: True)
    result = chat_routes.edit_message(4, 9, MessageEditPayload(content="editado"), FakeRequest())
    assert result == {"message_id": 9, "updated": True}

    monkeypatch.setattr(chat_routes, "update_user_message", lambda message_id, conversation_id, user_id, content: False)
    with pytest.raises(HTTPException) as error:
        chat_routes.edit_message(99, 4, MessageEditPayload(content="x"), FakeRequest())
    assert error.value.status_code == 404


def test_folder_payload_rejects_empty_name():
    with pytest.raises(ValidationError):
        FolderPayload(name="   ")


def test_message_edit_payload_rejects_empty():
    with pytest.raises(ValidationError):
        MessageEditPayload(content="")
