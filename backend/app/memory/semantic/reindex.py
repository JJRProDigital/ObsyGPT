"""Full reindex of memories and messages for the current embedding model."""

import logging
import threading

from ...admin.queries import execute_returning, fetch_one
from .embeddings import get_embedding_service
from . import store as _store

logger = logging.getLogger("obsygpt.memory.semantic")

BATCH_SIZE = 50


def _load_status() -> dict:
    row = fetch_one("SELECT value FROM app_settings WHERE key = 'embeddings_reindex';", ())
    return (row or {}).get("value") or {"running": False, "processed": 0, "total": 0, "error": None}


def _set_status(status: dict) -> None:
    import json

    execute_returning(
        """
        INSERT INTO app_settings (key, value)
        VALUES ('embeddings_reindex', %s::json)
        ON CONFLICT (key) DO UPDATE SET value = EXCLUDED.value
        RETURNING value;
        """,
        (json.dumps(status),),
    )


def reindex_status() -> dict:
    try:
        return _load_status()
    except Exception:  # noqa: BLE001
        return {"running": False, "processed": 0, "total": 0, "error": None}


def clear_stale_reindex() -> None:
    """Startup hook: no reindex can be running before this process starts (single-worker deployment)."""
    try:
        _set_status({"running": False, "processed": 0, "total": 0, "error": None})
    except Exception as error:  # noqa: BLE001
        logger.warning("Could not clear stale reindex status: %s", repr(error))


def run_reindex() -> None:
    status = reindex_status()
    try:
        service = get_embedding_service()
        model = service.model_id
        try:
            purged = _store.purge_other_model_embeddings(model)
            if purged:
                logger.info("Purged %d stale embeddings from a previous model", purged)
        except Exception as error:  # noqa: BLE001
            logger.warning("Could not purge stale model embeddings: %s", repr(error))
        total = _store.count_missing_index(model)
        status = {"running": True, "processed": 0, "total": total, "error": None}
        _set_status(status)
        processed = 0
        excluded_messages: list[int] = []
        excluded_memories: list[int] = []
        while True:
            messages = _store.list_missing_messages(model, limit=BATCH_SIZE, exclude_message_ids=excluded_messages)
            memories = _store.list_missing_memories(model, exclude_memory_ids=excluded_memories)[:BATCH_SIZE]
            if not messages and not memories:
                break
            for record in messages:
                from .indexer import SemanticIndexer

                worker = SemanticIndexer(service=service, store=_store, start_worker=False)
                saved = worker.index_message(record["conversation_id"], record["message_id"])
                if not saved:
                    excluded_messages.append(record["message_id"])
                    continue
                processed += 1
                _set_status({"running": True, "processed": processed, "total": total, "error": None})
            for record in memories:
                from .indexer import SemanticIndexer

                worker = SemanticIndexer(service=service, store=_store, start_worker=False)
                saved = worker.index_memory(record["id"])
                if not saved:
                    excluded_memories.append(record["id"])
                    continue
                processed += 1
                _set_status({"running": True, "processed": processed, "total": total, "error": None})
        _set_status({"running": False, "processed": processed, "total": total, "error": None})
    except Exception as error:  # noqa: BLE001
        logger.error("Reindex failed: %s", repr(error))
        _set_status({"running": False, "processed": status.get("processed", 0), "total": status.get("total", 0), "error": str(error)[:300]})


def start_reindex() -> bool:
    if reindex_status().get("running"):
        return False
    thread = threading.Thread(target=run_reindex, daemon=True, name="obsygpt-semantic-reindex")
    thread.start()
    return True
