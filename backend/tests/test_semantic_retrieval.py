from unittest.mock import patch

from app.memory.semantic import retrieval


class FakeService:
    model_id = "fake-model"

    def embed_query(self, text):
        return [0.1, 0.2]


def test_search_semantic_merges_and_sorts_sources():
    with (
        patch.object(retrieval, "get_embedding_service", lambda: FakeService()),
        patch.object(retrieval.semantic_store, "search_memory_vectors", return_value=[{"text": "memoria", "score": 0.8, "when": "2026-10-01"}]),
        patch.object(retrieval.semantic_store, "search_message_chunks", return_value=[{"text": "mensaje", "score": 0.9, "conversation_id": 1, "title": "Chat", "when": "2026-10-02"}]),
    ):
        hits = retrieval.search_semantic(user_id=1, query="postgres")
    assert hits[0]["source"] == "conversación" and hits[0]["score"] == 0.9
    assert hits[1]["source"] == "memoria"


def test_search_semantic_passes_current_model_to_message_search():
    with (
        patch.object(retrieval, "get_embedding_service", lambda: FakeService()),
        patch.object(retrieval.semantic_store, "search_memory_vectors", return_value=[]),
        patch.object(retrieval.semantic_store, "search_message_chunks", return_value=[]) as fake_search,
    ):
        retrieval.search_semantic(user_id=1, query="postgres")
    assert fake_search.call_args.kwargs["model"] == "fake-model"


def test_build_block_empty_without_hits():
    with (
        patch.object(retrieval, "get_embedding_service", lambda: FakeService()),
        patch.object(retrieval.semantic_store, "search_memory_vectors", return_value=[]),
        patch.object(retrieval.semantic_store, "search_message_chunks", return_value=[]),
    ):
        assert retrieval.build_semantic_context_block(user_id=1, query="x") == ""


def test_build_block_degrades_on_error():
    with patch.object(retrieval, "get_embedding_service", side_effect=RuntimeError("boom")):
        assert retrieval.build_semantic_context_block(user_id=1, query="x") == ""


def test_build_block_formats_hits():
    hits = [{"text": "Contenido relevante", "score": 0.9, "source": "conversación", "conversation_id": 4, "title": "Chat IA", "when": "2026-10-01T10:00:00"}]
    with (
        patch.object(retrieval, "search_semantic", return_value=hits),
    ):
        block = retrieval.build_semantic_context_block(user_id=1, query="x")
    assert block.startswith("RECUERDOS RELEVANTES")
    assert "Chat IA" in block and "Contenido relevante" in block


def test_search_semantic_dedupes_identical_hits():
    with (
        patch.object(retrieval, "get_embedding_service", lambda: FakeService()),
        patch.object(retrieval.semantic_store, "search_memory_vectors", return_value=[]),
        patch.object(retrieval.semantic_store, "search_message_chunks", return_value=[
            {"text": "Hola, en que puedo ayudarte hoy?", "score": 0.6, "conversation_id": 1, "title": "A", "when": "2026-10-07"},
            {"text": "Hola, en que puedo ayudarte hoy?", "score": 0.59, "conversation_id": 2, "title": "B", "when": "2026-10-07"},
            {"text": "voy a preparar una charla sobre perros", "score": 0.58, "conversation_id": 3, "title": "C", "when": "2026-10-07"},
        ]),
    ):
        hits = retrieval.search_semantic(user_id=1, query="hola")
    assert len(hits) == 2
    assert hits[0]["text"].startswith("Hola")
    assert hits[1]["text"].startswith("voy a preparar")