from unittest.mock import patch

from app.admin.settings import get_reindex_status, trigger_reindex
from app.memory.semantic import reindex
from app.memory.semantic.embeddings import EmbeddingError


def test_start_reindex_refuses_when_running(monkeypatch):
    monkeypatch.setattr(reindex, "reindex_status", lambda: {"running": True})
    assert reindex.start_reindex() is False


def test_status_defaults(monkeypatch):
    monkeypatch.setattr(reindex, "load_embedding_config", lambda: {}, raising=False)

    class FakeQueries:
        @staticmethod
        def fetch_one(query, params):
            return None

    monkeypatch.setattr(reindex, "fetch_one", FakeQueries.fetch_one)
    status = reindex.reindex_status()
    assert status == {"running": False, "processed": 0, "total": 0, "error": None}


def test_run_reindex_processes_and_finishes():
    messages = [{"user_id": 1, "conversation_id": 2, "message_id": 3, "project_id": None, "content": "texto"}]
    memories = [{"id": 9, "user_id": 1, "content": "recuerdo"}]
    indexed = []

    class FakeService:
        model_id = "fake-model"

        def embed_passages(self, texts, kind="passage"):
            return [[0.1] for _ in texts]

    class FakeStore:
        def __init__(self):
            self.calls = []

        def purge_other_model_embeddings(self, model):
            self.calls.append(("purge", model))
            return 0

        def count_missing_index(self, model):
            self.calls.append(("count", model))
            return len(messages) + len(memories)

        def list_missing_messages(self, model, limit=50, exclude_message_ids=None):
            return messages if not indexed else []

        def list_missing_memories(self, model, exclude_memory_ids=None):
            return memories if not indexed else []

        def fetch_message_for_indexing(self, conversation_id, message_id):
            return {**messages[0], "role": "user"}

        def get_memory_for_indexing(self, memory_id):
            return memories[0]

        def save_message_embeddings(self, **kwargs):
            indexed.append(kwargs)

        def save_memory_embedding(self, **kwargs):
            indexed.append(kwargs)

    fake_store = FakeStore()

    with patch.object(reindex, "get_embedding_service", lambda: FakeService()), \
         patch.object(reindex, "_store", fake_store), \
         patch.object(reindex, "_set_status") as status_calls, \
         patch.object(reindex, "fetch_one", return_value=None):
        reindex.run_reindex()

    assert len(indexed) == 2
    assert indexed[0]["model"] == "fake-model"
    assert status_calls.call_args[0][0]["running"] is False
    assert fake_store.calls[0] == ("purge", "fake-model")
    assert fake_store.calls[1] == ("count", "fake-model")


def test_clear_stale_reindex_resets_status(monkeypatch):
    written = []
    monkeypatch.setattr(reindex, "_set_status", lambda status: written.append(status))
    reindex.clear_stale_reindex()
    assert written == [{"running": False, "processed": 0, "total": 0, "error": None}]


def test_clear_stale_reindex_swallows_errors(monkeypatch):
    def broken_set_status(status):
        raise RuntimeError("db down")

    monkeypatch.setattr(reindex, "_set_status", broken_set_status)
    reindex.clear_stale_reindex()


def test_real_route_functions_exercise_real_reindex_module(monkeypatch):
    monkeypatch.setattr("app.auth.routes.require_admin", lambda request: 1)
    captured = {}

    class FakeAuditStore:
        def add_log(self, actor_user_id, action, target_type, target_id, metadata):
            captured.update({"actor_user_id": actor_user_id, "action": action, "target_type": target_type, "target_id": target_id, "metadata": metadata})

    monkeypatch.setattr("app.audit.AuditStore", FakeAuditStore)

    class FakeService:
        model_id = "fake-model"

        def embed_passages(self, texts, kind="passage"):
            return [[0.1] for _ in texts]

    class FakeStore:
        def count_missing_index(self, model):
            return 0

        def list_missing_messages(self, model, limit=50, exclude_message_ids=None):
            return []

        def list_missing_memories(self, model, exclude_memory_ids=None):
            return []

    statuses = []

    class FakeThread:
        def __init__(self, target=None, daemon=False, name=None):
            self.target = target

        def start(self):
            self.target()

    class FakeThreading:
        Thread = FakeThread

    monkeypatch.setattr(reindex, "fetch_one", lambda query, params: None)
    monkeypatch.setattr(reindex, "get_embedding_service", lambda: FakeService())
    monkeypatch.setattr(reindex, "_store", FakeStore())
    monkeypatch.setattr(reindex, "_set_status", lambda status: statuses.append(status))
    monkeypatch.setattr(reindex, "threading", FakeThreading)

    class FakeRequest:
        session = {"user_id": 1, "role": "admin"}

    result = trigger_reindex(FakeRequest())

    assert result == {"reindex": {"running": False, "processed": 0, "total": 0, "error": None}}
    assert statuses[0] == {"running": True, "processed": 0, "total": 0, "error": None}
    assert statuses[-1]["running"] is False
    assert captured == {
        "actor_user_id": 1,
        "action": "embeddings.reindex_started",
        "target_type": "settings",
        "target_id": None,
        "metadata": {},
    }
    assert get_reindex_status(FakeRequest()) == {"reindex": {"running": False, "processed": 0, "total": 0, "error": None}}


def test_run_reindex_terminates_when_all_items_unembeddable():
    message = {"user_id": 1, "conversation_id": 2, "message_id": 3, "project_id": None, "content": "texto"}
    memory = {"id": 9, "user_id": 1, "content": "recuerdo"}
    fetch_counts = {"messages": 0, "memories": 0}
    exclude_seen = {"messages": "not-called", "memories": "not-called"}

    class BrokenService:
        model_id = "fake-model"

        def embed_passages(self, texts, kind="passage"):
            raise EmbeddingError("endpoint down")

    class FakeStore:
        def count_missing_index(self, model):
            return 2

        def list_missing_messages(self, model, limit=50, exclude_message_ids=None):
            fetch_counts["messages"] += 1
            if fetch_counts["messages"] == 2:
                exclude_seen["messages"] = exclude_message_ids
            return [message] if fetch_counts["messages"] == 1 else []

        def list_missing_memories(self, model, exclude_memory_ids=None):
            fetch_counts["memories"] += 1
            if fetch_counts["memories"] == 2:
                exclude_seen["memories"] = exclude_memory_ids
            return [memory] if fetch_counts["memories"] == 1 else []

        def fetch_message_for_indexing(self, conversation_id, message_id):
            return {**message, "role": "user"}

        def get_memory_for_indexing(self, memory_id):
            return memory

        def save_message_embeddings(self, **kwargs):
            raise AssertionError("no save expected: every item is unembeddable")

        def save_memory_embedding(self, **kwargs):
            raise AssertionError("no save expected: every item is unembeddable")

    statuses = []

    with patch.object(reindex, "get_embedding_service", lambda: BrokenService()), \
         patch.object(reindex, "_store", FakeStore()), \
         patch.object(reindex, "_set_status", lambda status: statuses.append(status)), \
         patch.object(reindex, "fetch_one", return_value=None):
        reindex.run_reindex()

    assert exclude_seen["messages"] == [3]
    assert exclude_seen["memories"] == [9]
    assert statuses[-1] == {"running": False, "processed": 0, "total": 2, "error": None}


def test_run_reindex_counts_only_real_saves():
    records = [
        {"user_id": 1, "conversation_id": 2, "message_id": 3, "project_id": None, "content": "texto"},
        {"user_id": 1, "conversation_id": 2, "message_id": 4, "project_id": None, "content": ""},
    ]

    class FakeService:
        model_id = "fake-model"

        def embed_passages(self, texts, kind="passage"):
            return [[0.1] for _ in texts]

    class FakeStore:
        def __init__(self):
            self.saved_message_ids = []

        def count_missing_index(self, model):
            return len(records)

        def list_missing_messages(self, model, limit=50, exclude_message_ids=None):
            gone = set(self.saved_message_ids) | set(exclude_message_ids or [])
            return [record for record in records if record["message_id"] not in gone]

        def list_missing_memories(self, model, exclude_memory_ids=None):
            return []

        def fetch_message_for_indexing(self, conversation_id, message_id):
            record = next(r for r in records if r["message_id"] == message_id)
            return {**record, "role": "user"}

        def get_memory_for_indexing(self, memory_id):
            return None

        def save_message_embeddings(self, **kwargs):
            self.saved_message_ids.append(kwargs["message_id"])

        def save_memory_embedding(self, **kwargs):
            raise AssertionError("no memory expected in this test")

    fake_store = FakeStore()
    statuses = []

    with patch.object(reindex, "get_embedding_service", lambda: FakeService()), \
         patch.object(reindex, "_store", fake_store), \
         patch.object(reindex, "_set_status", lambda status: statuses.append(status)), \
         patch.object(reindex, "fetch_one", return_value=None):
        reindex.run_reindex()

    assert fake_store.saved_message_ids == [3]
    assert statuses[-1] == {"running": False, "processed": 1, "total": 2, "error": None}
