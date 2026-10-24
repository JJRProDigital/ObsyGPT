from unittest.mock import patch

from app.memory.semantic import store


class FakeCursor:
    def __init__(self, rows, rowcount=0):
        self.rows = rows
        self.rowcount = rowcount
        self.executed = []

    def execute(self, query, params=()):
        placeholders = query.count("%s")
        if placeholders != len(params):
            raise ValueError(
                f"placeholder/param mismatch: query has {placeholders} placeholders but {len(params)} params were bound"
            )
        self.executed.append((query, params))

    def fetchone(self):
        return self.rows[0] if self.rows else None

    def fetchall(self):
        return list(self.rows)

    def __enter__(self):
        return self

    def __exit__(self, *args):
        return False


class FakeConnection:
    def __init__(self, rows=None, rowcount=0):
        self.cursor_obj = FakeCursor(rows or [], rowcount=rowcount)

    def cursor(self):
        return self.cursor_obj

    def __enter__(self):
        return self

    def __exit__(self, *args):
        return False


def test_vector_literal_formats_floats():
    assert store.vector_literal([0.1, -0.25, 2.0]) == "[0.100000,-0.250000,2.000000]"


def test_search_message_chunks_filters_by_user_and_threshold():
    conn = FakeConnection([(b"texto", 0.91, 7, "Chat IA", "2026-10-01T10:00:00+00:00")])
    with patch.object(store, "connect", return_value=conn):
        hits = store.search_message_chunks(user_id=3, query_vector_literal="[0.1,0.2]", project_id=None, k=5, threshold=0.35)
    assert hits[0]["text"] == "texto"
    assert hits[0]["score"] == 0.91
    assert hits[0]["title"] == "Chat IA"
    query, params = conn.cursor_obj.executed[0]
    assert "<=>" in query and "%s::vector" in query
    assert params[0] == "[0.1,0.2]" and params[1] == 3


def test_search_memory_vectors_returns_hits():
    conn = FakeConnection([(b"Preferes respuestas breves", 0.88, "2026-09-30T08:00:00+00:00")])
    with patch.object(store, "connect", return_value=conn):
        hits = store.search_memory_vectors(user_id=3, query_vector_literal="[0.4]", k=3, threshold=0.35)
    assert hits[0]["score"] == 0.88
    assert "memories" in conn.cursor_obj.executed[0][0]


def test_purge_other_model_embeddings_deletes_and_returns_rowcount():
    conn = FakeConnection(rowcount=7)
    with patch.object(store, "connect", return_value=conn):
        deleted = store.purge_other_model_embeddings("model-b")
    assert deleted == 7
    query, params = conn.cursor_obj.executed[0]
    assert "DELETE FROM message_embeddings" in query and "IS DISTINCT FROM" in query
    assert params == ("model-b",)


def test_search_message_chunks_filters_by_model_when_set():
    conn = FakeConnection()
    with patch.object(store, "connect", return_value=conn):
        store.search_message_chunks(user_id=3, query_vector_literal="[0.1]", project_id=None, k=5, threshold=0.35, model="model-b")
    query, params = conn.cursor_obj.executed[0]
    assert "me.model = %s" in query
    assert params[-1] == 5 and params[-2] == "model-b"

    conn_no_model = FakeConnection()
    with patch.object(store, "connect", return_value=conn_no_model):
        store.search_message_chunks(user_id=3, query_vector_literal="[0.1]", project_id=None, k=5, threshold=0.35)
    assert "me.model = %s" not in conn_no_model.cursor_obj.executed[0][0]
