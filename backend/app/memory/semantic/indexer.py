"""Background semantic indexing of chat messages and manual memories."""

import logging
import queue
import threading

from .embeddings import EmbeddingError, get_embedding_service
from . import store as semantic_store

logger = logging.getLogger("obsygpt.memory.semantic")

CHUNK_MAX_CHARS = 800
INDEXABLE_ROLES = {"user", "assistant"}


def chunk_text(text: str, max_chars: int = CHUNK_MAX_CHARS) -> list[str]:
    text = text.strip()
    if not text:
        return []
    if len(text) <= max_chars:
        return [text]
    chunks: list[str] = []
    current = ""
    for paragraph in text.split("\n\n"):
        candidate = f"{current}\n\n{paragraph}" if current else paragraph
        if len(candidate) <= max_chars:
            current = candidate
            continue
        if current:
            chunks.append(current)
        while len(paragraph) > max_chars:
            chunks.append(paragraph[:max_chars])
            paragraph = paragraph[max_chars:]
        current = paragraph
    if current:
        chunks.append(current)
    return chunks


class SemanticIndexer:
    def __init__(self, service=None, store=None, start_worker: bool = True):
        self._service = service
        self._store = store or semantic_store
        self._queue: queue.Queue = queue.Queue()
        self._thread: threading.Thread | None = None
        if start_worker:
            self._ensure_worker()

    @property
    def service(self):
        if self._service is None:
            self._service = get_embedding_service()
        return self._service

    def enqueue_message(self, conversation_id: int, message_id: int) -> None:
        self._ensure_worker()
        self._queue.put(("message", conversation_id, message_id))

    def enqueue_memory(self, memory_id: int) -> None:
        self._ensure_worker()
        self._queue.put(("memory", None, memory_id))

    def _ensure_worker(self) -> None:
        if self._thread is None or not self._thread.is_alive():
            self._thread = threading.Thread(target=self._worker, daemon=True, name="obsygpt-semantic-indexer")
            self._thread.start()

    def _worker(self) -> None:
        while True:
            kind, conversation_id, item_id = self._queue.get()
            try:
                if kind == "message":
                    self.index_message(conversation_id, item_id)
                else:
                    self.index_memory(item_id)
            except Exception as error:  # noqa: BLE001 - the indexer must never crash the worker
                logger.warning("Semantic indexing failed for %s %s: %s", kind, item_id, repr(error))
            finally:
                self._queue.task_done()

    def index_message(self, conversation_id: int, message_id: int) -> bool:
        """Indexes one chat message. Returns True exactly when embeddings were saved, False when skipped or embedding failed."""
        record = self._store.fetch_message_for_indexing(conversation_id, message_id)
        if not record or record["role"] not in INDEXABLE_ROLES:
            return False
        chunks = chunk_text(str(record["content"] or ""))
        if not chunks:
            return False
        try:
            vectors = self.service.embed_passages(chunks)
            self._store.save_message_embeddings(
                user_id=record["user_id"],
                conversation_id=record["conversation_id"],
                message_id=record["message_id"],
                project_id=record["project_id"],
                chunks=chunks,
                vectors=vectors,
                model=self.service.model_id,
            )
            return True
        except EmbeddingError as error:
            logger.warning("Semantic indexing failed for message %s: %s", message_id, repr(error))
            return False

    def index_memory(self, memory_id: int) -> bool:
        """Indexes one manual memory. Returns True exactly when an embedding was saved, False when skipped or embedding failed."""
        record = self._store.get_memory_for_indexing(memory_id)
        if not record:
            return False
        try:
            vector = self.service.embed_passages([str(record["content"] or "")])[0]
            self._store.save_memory_embedding(
                user_id=record["user_id"],
                memory_id=record["id"],
                vector=vector,
                model=self.service.model_id,
            )
            return True
        except EmbeddingError as error:
            logger.warning("Semantic indexing failed for memory %s: %s", memory_id, repr(error))
            return False


semantic_indexer = SemanticIndexer(start_worker=False)
