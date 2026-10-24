from app.memory.semantic import indexer
from app.memory.semantic.embeddings import EmbeddingError


def test_chunk_text_short_message_single_chunk():
    assert indexer.chunk_text("hola mundo") == ["hola mundo"]


def test_chunk_text_long_message_splits_by_paragraph():
    text = "párrafo uno\n\n" + "x" * 900 + "\n\npárrafo tres"
    chunks = indexer.chunk_text(text, max_chars=800)
    assert all(len(chunk) <= 800 for chunk in chunks)
    assert chunks[0] == "párrafo uno"
    assert chunks[-1].endswith("párrafo tres")


class FakeService:
    model_id = "fake-model"

    def embed_passages(self, texts, kind="passage"):
        return [[0.1, 0.2] for _ in texts]


class FakeStore:
    def __init__(self, message=None, memory=None):
        self.message = message
        self.memory = memory
        self.saved = []

    def fetch_message_for_indexing(self, conversation_id, message_id):
        return self.message

    def get_memory_for_indexing(self, memory_id):
        return self.memory

    def save_message_embeddings(self, user_id, conversation_id, message_id, project_id, chunks, vectors, model):
        self.saved.append((user_id, message_id, chunks, model))
        return len(chunks)

    def save_memory_embedding(self, user_id, memory_id, vector, model):
        self.saved.append((user_id, memory_id, model))
        return True


def test_index_message_chunks_and_saves():
    fake_store = FakeStore(message={"user_id": 1, "conversation_id": 2, "message_id": 3, "project_id": None, "role": "user", "content": "mensaje de prueba"})
    worker = indexer.SemanticIndexer(service=FakeService(), store=fake_store, start_worker=False)
    worker.index_message(2, 3)
    assert fake_store.saved[0][1] == 3 and fake_store.saved[0][2] == ["mensaje de prueba"]


def test_index_message_skips_non_chat_roles():
    fake_store = FakeStore(message={"user_id": 1, "conversation_id": 2, "message_id": 3, "project_id": None, "role": "system", "content": "nota"})
    worker = indexer.SemanticIndexer(service=FakeService(), store=fake_store, start_worker=False)
    worker.index_message(2, 3)
    assert fake_store.saved == []


def test_index_memory_saves_vector():
    fake_store = FakeStore(memory={"id": 9, "user_id": 1, "content": "Prefiere español"})
    worker = indexer.SemanticIndexer(service=FakeService(), store=fake_store, start_worker=False)
    worker.index_memory(9)
    assert fake_store.saved[0][0] == 1


def test_index_message_swallows_embedding_error():
    class BrokenService(FakeService):
        def embed_passages(self, texts, kind="passage"):
            raise EmbeddingError("endpoint down")

    fake_store = FakeStore(message={"user_id": 1, "conversation_id": 2, "message_id": 3, "project_id": None, "role": "user", "content": "hola"})
    worker = indexer.SemanticIndexer(service=BrokenService(), store=fake_store, start_worker=False)
    worker.index_message(2, 3)  # must not raise
    assert fake_store.saved == []
