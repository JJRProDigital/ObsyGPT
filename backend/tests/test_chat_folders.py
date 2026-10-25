from datetime import datetime, timezone

import pytest

from fastapi import HTTPException
from pydantic import ValidationError

from app.chat import conversations as chat_conversations
from app.chat.conversations import ConversationFolderPayload, FolderPayload, MessageEditPayload


class FakeRequest:
    session = {"user_id": 1}


def _now():
    return datetime.now(timezone.utc)


def test_list_conversations_prefers_custom_title_as_label(monkeypatch):
    rows = [
        (11, "Mi titulo custom", _now(), 3, 7),
        (12, "", _now(), 4, None),
    ]
    monkeypatch.setattr(chat_conversations, "get_conversations", lambda user_id: rows)

    result = chat_conversations.list_conversations(FakeRequest())

    labels = {conversation["id"]: conversation["label"] for conversation in result["conversations"]}
    assert labels[11] == "Mi titulo custom"
    assert labels[12].startswith("Chat 4 - ")
    assert result["conversations"][0]["folder_id"] == 7
    assert result["conversations"][1]["folder_id"] is None


def test_folder_crud_endpoints(monkeypatch):
    monkeypatch.setattr(chat_conversations, "list_chat_folders", lambda user_id: [{"id": 1, "name": "Trabajo", "conversation_count": 2}])
    monkeypatch.setattr(chat_conversations, "create_chat_folder", lambda user_id, name: {"id": 2, "name": name, "conversation_count": 0})
    monkeypatch.setattr(chat_conversations, "rename_chat_folder", lambda folder_id, user_id, name: {"id": folder_id, "name": name})
    monkeypatch.setattr(chat_conversations, "delete_chat_folder", lambda folder_id, user_id: True)

    assert chat_conversations.get_folders(FakeRequest()) == {"folders": [{"id": 1, "name": "Trabajo", "conversation_count": 2}]}
    assert chat_conversations.post_folder(FolderPayload(name="Personal"), FakeRequest()) == {"folder": {"id": 2, "name": "Personal", "conversation_count": 0}}
    assert chat_conversations.patch_folder(1, FolderPayload(name="Nuevo"), FakeRequest()) == {"folder": {"id": 1, "name": "Nuevo"}}
    assert chat_conversations.remove_folder(1, FakeRequest()) == {"id": 1, "deleted": True}


def test_remove_folder_returns_404_when_missing(monkeypatch):
    monkeypatch.setattr(chat_conversations, "delete_chat_folder", lambda folder_id, user_id: False)
    with pytest.raises(HTTPException) as error:
        chat_conversations.remove_folder(99, FakeRequest())
    assert error.value.status_code == 404


def test_move_conversation_updates_folder(monkeypatch):
    captured = {}

    def fake_move(conversation_id, user_id, folder_id):
        captured.update({"conversation_id": conversation_id, "folder_id": folder_id})
        return {"id": conversation_id, "folder_id": folder_id}

    monkeypatch.setattr(chat_conversations, "move_conversation_to_folder", fake_move)
    result = chat_conversations.set_conversation_folder(5, ConversationFolderPayload(folder_id=3), FakeRequest())

    assert result == {"id": 5, "folder_id": 3}
    assert captured == {"conversation_id": 5, "folder_id": 3}

    result_none = chat_conversations.set_conversation_folder(5, ConversationFolderPayload(folder_id=None), FakeRequest())
    assert result_none == {"id": 5, "folder_id": None}


def test_move_conversation_404_when_folder_missing(monkeypatch):
    monkeypatch.setattr(chat_conversations, "move_conversation_to_folder", lambda conversation_id, user_id, folder_id: None)
    with pytest.raises(HTTPException) as error:
        chat_conversations.set_conversation_folder(5, ConversationFolderPayload(folder_id=3), FakeRequest())
    assert error.value.status_code == 404


def test_edit_message_endpoint(monkeypatch):
    monkeypatch.setattr(chat_conversations, "update_user_message", lambda message_id, conversation_id, user_id, content: True)
    result = chat_conversations.edit_message(4, 9, MessageEditPayload(content="editado"), FakeRequest())
    assert result == {"message_id": 9, "updated": True}

    monkeypatch.setattr(chat_conversations, "update_user_message", lambda message_id, conversation_id, user_id, content: False)
    with pytest.raises(HTTPException) as error:
        chat_conversations.edit_message(99, 4, MessageEditPayload(content="x"), FakeRequest())
    assert error.value.status_code == 404


def test_folder_payload_rejects_empty_name():
    with pytest.raises(ValidationError):
        FolderPayload(name="   ")


def test_message_edit_payload_rejects_empty():
    with pytest.raises(ValidationError):
        MessageEditPayload(content="")
