"""Embedding generation for semantic memory: local fastembed by default, optional OpenAI-compatible endpoint."""

import json
import logging
import os
import threading
from urllib.error import HTTPError, URLError
from urllib.request import Request as UrlRequest
from urllib.request import urlopen

logger = logging.getLogger("obsygpt.memory.semantic")

# Multilingual (Spanish included), 384 dims — fastembed >=0.8 dropped multilingual-e5-small.
LOCAL_MODEL = "sentence-transformers/paraphrase-multilingual-MiniLM-L12-v2"
EMBEDDING_DIMENSION = 384
# Short timeout for the interactive chat path (embed_query); background indexing can wait longer.
QUERY_TIMEOUT = 10.0
INDEX_TIMEOUT = 60.0


class EmbeddingError(RuntimeError):
    pass


_local_model_lock = threading.Lock()
_local_model = None


def _embed_with_local_model(texts: list[str]) -> list[list[float]]:
    """Module-level indirection so tests can monkeypatch the local model call."""
    global _local_model
    with _local_model_lock:
        if _local_model is None:
            try:
                from fastembed import TextEmbedding
            except ImportError as error:
                raise EmbeddingError("fastembed is not installed; run pip install fastembed.") from error
            logger.info("Loading local embedding model %s", LOCAL_MODEL)
            _local_model = TextEmbedding(model_name=LOCAL_MODEL)
    return [list(map(float, vector)) for vector in _local_model.embed(texts)]


class EmbeddingService:
    def __init__(self, mode: str = "local", base_url: str = "", model: str = "", api_key_env: str = ""):
        self.mode = mode if mode in {"local", "endpoint"} else "local"
        self.base_url = (base_url or "").rstrip("/")
        self.model = model or ""
        self.api_key_env = api_key_env or ""

    @property
    def model_id(self) -> str:
        return LOCAL_MODEL if self.mode == "local" else self.model

    @property
    def dimension(self) -> int:
        return EMBEDDING_DIMENSION

    def embed_query(self, text: str) -> list[float]:
        return self.embed_passages([text], kind="query", timeout=QUERY_TIMEOUT)[0]

    def embed_passages(self, texts: list[str], kind: str = "passage", timeout: float = INDEX_TIMEOUT) -> list[list[float]]:
        if not texts:
            return []
        prepared = list(texts) if self.mode == "endpoint" else [f"{kind}: {text}" for text in texts]
        if self.mode == "endpoint":
            return self._embed_endpoint(prepared, timeout=timeout)
        return _embed_with_local_model(prepared)

    def _embed_endpoint(self, texts: list[str], timeout: float = INDEX_TIMEOUT) -> list[list[float]]:
        if not self.base_url or not self.model:
            raise EmbeddingError("Endpoint mode requires base_url and model in the embeddings settings.")
        headers = {"Content-Type": "application/json"}
        key = os.environ.get(self.api_key_env, "") if self.api_key_env else ""
        if key:
            headers["Authorization"] = f"Bearer {key}"
        request = UrlRequest(
            f"{self.base_url}/embeddings",
            data=json.dumps({"model": self.model, "input": texts}).encode(),
            headers=headers,
            method="POST",
        )
        try:
            with urlopen(request, timeout=timeout) as response:
                data = json.loads(response.read().decode())
        except HTTPError as error:
            raise EmbeddingError(f"Embeddings endpoint returned HTTP {error.code}.") from error
        except (URLError, TimeoutError, json.JSONDecodeError) as error:
            raise EmbeddingError(f"Embeddings endpoint unreachable: {error}") from error
        try:
            vectors = [list(map(float, item["embedding"])) for item in data["data"]]
        except (KeyError, TypeError, ValueError) as error:
            raise EmbeddingError("Unexpected response from the embeddings endpoint.") from error
        for vector in vectors:
            if len(vector) != EMBEDDING_DIMENSION:
                raise EmbeddingError(
                    f"Embeddings endpoint returned dimension {len(vector)}, expected {EMBEDDING_DIMENSION}."
                )
        return vectors


def load_embedding_config() -> dict:
    from ...admin.queries import fetch_one

    row = fetch_one("SELECT value FROM app_settings WHERE key = 'embeddings';", ())
    return (row or {}).get("value") or {}


def get_embedding_service() -> EmbeddingService:
    config = load_embedding_config()
    return EmbeddingService(
        mode=str(config.get("mode") or "local"),
        base_url=str(config.get("base_url") or ""),
        model=str(config.get("model") or ""),
        api_key_env=str(config.get("api_key_env") or ""),
    )
