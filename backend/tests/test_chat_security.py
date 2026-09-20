import pytest
from fastapi import HTTPException
from pydantic import ValidationError

from app.chat.routes import ConversationUpdateRequest, delete_conversation, ensure_requested_attachments_available, update_conversation_title
from app.files.context import AttachmentRecord


def test_requested_attachments_allows_empty_request():
    ensure_requested_attachments_available([], [])


def test_requested_attachments_allows_all_available_records():
    records = [AttachmentRecord(id=1, file_name="a.txt", mime_type="text/plain", storage_path="a.txt", size_bytes=1)]

    ensure_requested_attachments_available([1], records)


def test_requested_attachments_rejects_missing_or_unauthorized_records():
    records = [AttachmentRecord(id=1, file_name="a.txt", mime_type="text/plain", storage_path="a.txt", size_bytes=1)]

    with pytest.raises(HTTPException) as error:
        ensure_requested_attachments_available([1, 2], records)

    assert error.value.status_code == 404
    assert error.value.detail == "One or more attachments were not found."


def test_requested_attachments_handles_duplicate_ids():
    records = [AttachmentRecord(id=1, file_name="a.txt", mime_type="text/plain", storage_path="a.txt", size_bytes=1)]

    ensure_requested_attachments_available([1, 1], records)


def test_delete_conversation_returns_true_when_owned_conversation_is_deleted(monkeypatch):
    class FakeCursor:
        rowcount = 1

        def __enter__(self):
            return self

        def __exit__(self, exc_type, exc, traceback):
            return False

        def execute(self, query, params):
            assert "DELETE FROM conversations" in query
            assert params == (5, 9)

    class FakeConnection:
        def __enter__(self):
            return self

        def __exit__(self, exc_type, exc, traceback):
            return False

        def cursor(self):
            return FakeCursor()

    monkeypatch.setattr("app.chat.routes.connect", lambda: FakeConnection())

    assert delete_conversation(conversation_id=5, user_id=9) is True


def test_delete_conversation_returns_false_when_no_owned_row_is_deleted(monkeypatch):
    class FakeCursor:
        rowcount = 0

        def __enter__(self):
            return self

        def __exit__(self, exc_type, exc, traceback):
            return False

        def execute(self, query, params):
            pass

    class FakeConnection:
        def __enter__(self):
            return self

        def __exit__(self, exc_type, exc, traceback):
            return False

        def cursor(self):
            return FakeCursor()

    monkeypatch.setattr("app.chat.routes.connect", lambda: FakeConnection())

    assert delete_conversation(conversation_id=5, user_id=9) is False


def test_update_conversation_title_returns_updated_owned_conversation(monkeypatch):
    class FakeCursor:
        description = [type("Column", (), {"name": name}) for name in ["id", "title", "created_at"]]

        def __enter__(self):
            return self

        def __exit__(self, exc_type, exc, traceback):
            return False

        def execute(self, query, params):
            assert "UPDATE conversations" in query
            assert params == ("New title", 5, 9)

        def fetchone(self):
            return (5, "New title", "created")

    class FakeConnection:
        def __enter__(self):
            return self

        def __exit__(self, exc_type, exc, traceback):
            return False

        def cursor(self):
            return FakeCursor()

    monkeypatch.setattr("app.chat.routes.connect", lambda: FakeConnection())

    assert update_conversation_title(5, 9, "New title") == {"id": 5, "title": "New title", "created_at": "created"}


def test_conversation_update_rejects_overlong_title():
    with pytest.raises(ValidationError):
        ConversationUpdateRequest(title="x" * 121)
