"""Semantic search over memories and message chunks, plus the chat context block."""

import logging

from . import store as semantic_store
from .embeddings import get_embedding_service

logger = logging.getLogger("obsygpt.memory.semantic")

DEFAULT_THRESHOLD = 0.35
MAX_HIT_CHARS = 400


def search_semantic(
    user_id: int,
    query: str,
    project_id: int | None = None,
    k: int = 5,
    threshold: float = DEFAULT_THRESHOLD,
    exclude_conversation_id: int | None = None,
) -> list[dict]:
    """Merges memory and message-chunk hits, sorted by cosine score descending.

    `exclude_conversation_id` skips the conversation whose content is already in the model's context."""
    query = (query or "").strip()
    if not query:
        return []
    service = get_embedding_service()
    literal = semantic_store.vector_literal(service.embed_query(query))
    hits: list[dict] = []
    for hit in semantic_store.search_memory_vectors(user_id, literal, k, threshold):
        hits.append({**hit, "source": "memoria", "conversation_id": None, "title": ""})
    for hit in semantic_store.search_message_chunks(user_id, literal, project_id, k, threshold, model=service.model_id, exclude_conversation_id=exclude_conversation_id):
        hits.append({**hit, "source": "conversación"})
    hits.sort(key=lambda hit: hit["score"], reverse=True)
    deduped: list[dict] = []
    seen: set[str] = set()
    for hit in hits:
        key = " ".join(str(hit.get("text", "")).lower().split())[:100]
        if key in seen:
            continue
        seen.add(key)
        deduped.append(hit)
    return deduped[:k]


def build_semantic_context_block(user_id: int, query: str, project_id: int | None = None, k: int = 5, exclude_conversation_id: int | None = None) -> str:
    """Best-effort context block: empty string when there are no hits or the service fails."""
    try:
        hits = search_semantic(user_id, query, project_id=project_id, k=k, exclude_conversation_id=exclude_conversation_id)
    except Exception as error:  # noqa: BLE001 - semantic memory must never break chat
        logger.warning("Semantic retrieval failed: %s", repr(error))
        return ""
    if not hits:
        return ""
    lines = []
    for hit in hits:
        text = hit["text"].replace("\n", " ").strip()
        if len(text) > MAX_HIT_CHARS:
            text = text[:MAX_HIT_CHARS] + "..."
        origin = hit.get("title") or ("conversación #" + str(hit["conversation_id"]) if hit.get("conversation_id") else hit["source"])
        lines.append(f"- {text} (fuente: {origin}, {str(hit['when'])[:10]})")
    return (
        "RECUERDOS RELEVANTES de tu memoria persistente (conversaciones pasadas y recuerdos; "
        "úsalos si aportan contexto, sin anunciar que provienen de una lista):\n\n" + "\n".join(lines)
    )
