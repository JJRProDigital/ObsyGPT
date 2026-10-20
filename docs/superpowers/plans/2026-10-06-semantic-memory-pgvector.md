# Semantic Memory (pgvector) Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add semantic memory to ObsyGPT: memories and past conversations become searchable by relevance via pgvector, with automatic top-k injection into chat plus an explicit `memory_search` agent tool.

**Architecture:** New module `backend/app/memory/semantic/` with four focused units: `embeddings.py` (EmbeddingService: local fastembed by default, optional OpenAI-compatible endpoint), `store.py` (SQL for vector write/search), `indexer.py` (background queue + chunking), `retrieval.py` (search + context block). Wire into `chat_conversations.save_message` (indexing hook), `chat/routes.py` (injection), `chat/specs.py` (tool registration), `admin/settings.py` (config + reindex endpoints).

**Tech Stack:** Python 3.13 / FastAPI / psycopg3 / PostgreSQL 16 + pgvector (HNSW) / fastembed (`intfloat/multilingual-e5-small`, 384 dim) / React + TypeScript frontend.

**Spec:** `docs/superpowers/specs/2026-10-06-semantic-memory-pgvector-design.md`

## Global Constraints

- Tests run WITHOUT a live database (CI installs only requirements.txt): every test uses fakes/monkeypatch, mirroring `backend/tests/test_memory.py` style.
- Vectors cross the DB boundary as string literals cast with `%s::vector`; read back with `embedding::text`. Do NOT add the `pgvector` Python package.
- Only new Python dependency allowed: `fastembed` in `backend/requirements.txt`.
- Embedding dimension is fixed at 384 (`vector(384)` columns). Endpoint mode rejects other dimensions with `EmbeddingError`.
- All user-facing copy (UI, prompts, tool outputs shown to the model) in Spain Spanish, no voseo ("tienes", "guarda", "ejecuta").
- UI copy rule: never alter unrelated dirty files in the worktree; touch only files listed per task.
- Commits: conventional commits, no AI attribution, one commit per task.
- After each task: `cd backend && python -m pytest -q` must pass (plus `npm run build` in frontend tasks).
- `alembic` migrations are the source of truth; `database/schema.sql` updated in the same task.

---

### Task 1: Dependencies + pgvector image + cache env

**Files:**
- Modify: `backend/requirements.txt`
- Modify: `docker-compose.yml:3` (postgres image) and `docker-compose.yml:24-37` (backend env)
- Test: none new (sanity only)

**Interfaces:**
- Consumes: nothing
- Produces: `fastembed` importable; postgres image with `vector` extension; `FASTEMBED_CACHE_PATH=/app/voice-data/fastembed` in the backend container (persistent volume `obsygpt_voice_data`).

- [ ] **Step 1: Add fastembed to requirements**

Append to `backend/requirements.txt`:

```
fastembed>=0.3
```

- [ ] **Step 2: Switch postgres image to pgvector**

In `docker-compose.yml`, change:

```yaml
  postgres:
    image: pgvector/pgvector:pg16
```

- [ ] **Step 3: Add embeddings cache env to backend service**

In `docker-compose.yml`, inside `backend.environment:` add:

```yaml
      FASTEMBED_CACHE_PATH: /app/voice-data/fastembed
```

- [ ] **Step 4: Sanity: existing suite still passes**

Run: `cd backend && python -m pytest -q`
Expected: all pass (fastembed is imported lazily later, so nothing breaks if not installed yet).

- [ ] **Step 5: Commit**

```bash
git add backend/requirements.txt docker-compose.yml
git commit -m "feat: add fastembed dep and pgvector postgres image for semantic memory"
```

---

### Task 2: Alembic migration 0022 + schema.sql

**Files:**
- Create: `backend/migrations/versions/0022_semantic_memory.py`
- Modify: `database/schema.sql` (append message_embeddings table + memories columns)

**Interfaces:**
- Consumes: existing `memories`, `messages`, `conversations`, `projects`, `users` tables.
- Produces: table `message_embeddings` (columns per SQL below), columns `memories.embedding vector(384)` and `memories.model TEXT`.

- [ ] **Step 1: Confirm the latest migration revision id**

Run: `cd backend && python -c "import pathlib; print(pathlib.Path('migrations/versions/0021_task_context_note.py').read_text()[:600])"`
Expected: shows `revision: str = "0021_task_context_note"`. If the id differs, use it as `down_revision` in Step 2.

- [ ] **Step 2: Write the migration**

Create `backend/migrations/versions/0022_semantic_memory.py`:

```python
"""Semantic memory: pgvector extension, message_embeddings, memory vectors

Revision ID: 0022_semantic_memory
Revises: 0021_task_context_note
Create Date: 2026-10-06
"""

from collections.abc import Sequence

from alembic import op


revision: str = "0022_semantic_memory"
down_revision: str | None = "0021_task_context_note"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.execute("CREATE EXTENSION IF NOT EXISTS vector;")
    op.execute(
        """
        CREATE TABLE message_embeddings (
            id BIGSERIAL PRIMARY KEY,
            user_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
            conversation_id INTEGER NOT NULL REFERENCES conversations(id) ON DELETE CASCADE,
            message_id INTEGER NOT NULL REFERENCES messages(id) ON DELETE CASCADE,
            project_id INTEGER REFERENCES projects(id) ON DELETE SET NULL,
            chunk TEXT NOT NULL,
            embedding vector(384) NOT NULL,
            model TEXT NOT NULL,
            created_at TIMESTAMPTZ NOT NULL DEFAULT now()
        );
        """
    )
    op.execute(
        "CREATE INDEX idx_message_embeddings_hnsw ON message_embeddings USING hnsw (embedding vector_cosine_ops);"
    )
    op.execute("CREATE INDEX idx_message_embeddings_user ON message_embeddings (user_id);")
    op.execute("ALTER TABLE memories ADD COLUMN embedding vector(384);")
    op.execute("ALTER TABLE memories ADD COLUMN model TEXT;")


def downgrade() -> None:
    op.execute("ALTER TABLE memories DROP COLUMN IF EXISTS model;")
    op.execute("ALTER TABLE memories DROP COLUMN IF EXISTS embedding;")
    op.execute("DROP TABLE IF EXISTS message_embeddings;")
```

- [ ] **Step 3: Update database/schema.sql**

Append at the end of `database/schema.sql` (same statements as the migration, minus the extension line which goes at the top of the file right after the existing setup):

```sql
CREATE TABLE IF NOT EXISTS message_embeddings (
    id BIGSERIAL PRIMARY KEY,
    user_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    conversation_id INTEGER NOT NULL REFERENCES conversations(id) ON DELETE CASCADE,
    message_id INTEGER NOT NULL REFERENCES messages(id) ON DELETE CASCADE,
    project_id INTEGER REFERENCES projects(id) ON DELETE SET NULL,
    chunk TEXT NOT NULL,
    embedding vector(384) NOT NULL,
    model TEXT NOT NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);
CREATE INDEX IF NOT EXISTS idx_message_embeddings_hnsw ON message_embeddings USING hnsw (embedding vector_cosine_ops);
CREATE INDEX IF NOT EXISTS idx_message_embeddings_user ON message_embeddings (user_id);
-- and inside the memories table definition add:
--   embedding vector(384),
--   model TEXT
```

Note: `schema.sql` has no `CREATE EXTENSION` today — add `CREATE EXTENSION IF NOT EXISTS vector;` right after the file's initial setup comments.

- [ ] **Step 4: Run full suite (no DB in CI, migration validated on dev run)**

Run: `cd backend && python -m pytest -q`
Expected: all pass.

- [ ] **Step 5: Dev check against local postgres (optional but recommended)**

```bash
docker compose up -d postgres
cd backend && alembic upgrade head
```

Expected: `0022_semantic_memory` applies without error.

- [ ] **Step 6: Commit**

```bash
git add backend/migrations/versions/0022_semantic_memory.py database/schema.sql
git commit -m "feat: migration 0022 semantic memory tables and pgvector extension"
```

---

### Task 3: `semantic/store.py` — vector persistence + search SQL

**Files:**
- Create: `backend/app/memory/semantic/__init__.py` (empty)
- Create: `backend/app/memory/semantic/store.py`
- Test: `backend/tests/test_semantic_store.py`

**Interfaces:**
- Consumes: `..db.connect` (psycopg3 connection, same as `app/memory/store.py`).
- Produces (used by Tasks 4/5/6/8/9):
  - `vector_literal(vector: list[float]) -> str`
  - `fetch_message_for_indexing(conversation_id: int, message_id: int) -> dict | None` — keys: `user_id, conversation_id, message_id, project_id, role, content`
  - `get_memory_for_indexing(memory_id: int) -> dict | None` — keys: `id, user_id, content`
  - `save_message_embeddings(user_id, conversation_id, message_id, project_id, chunks: list[str], vectors: list[list[float]], model: str) -> int`
  - `save_memory_embedding(user_id: int, memory_id: int, vector: list[float], model: str) -> bool`
  - `search_message_chunks(user_id: int, query_vector_literal: str, project_id: int | None, k: int, threshold: float) -> list[dict]` — keys: `text, score, conversation_id, title, when`
  - `search_memory_vectors(user_id: int, query_vector_literal: str, k: int, threshold: float) -> list[dict]` — keys: `text, score, when`

- [ ] **Step 1: Write failing tests**

Create `backend/tests/test_semantic_store.py`:

```python
from unittest.mock import patch

from app.memory.semantic import store


class FakeCursor:
    def __init__(self, rows):
        self.rows = rows
        self.executed = []

    def execute(self, query, params=()):
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
    def __init__(self, rows=None):
        self.cursor_obj = FakeCursor(rows or [])

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
```

- [ ] **Step 2: Run tests, verify failure**

Run: `cd backend && python -m pytest tests/test_semantic_store.py -v`
Expected: FAIL (`ModuleNotFoundError: app.memory.semantic`)

- [ ] **Step 3: Implement `store.py`**

Create `backend/app/memory/semantic/store.py`:

```python
"""SQL persistence and search for semantic memory vectors."""

from ..db import connect  # noqa: I001


def vector_literal(vector: list[float]) -> str:
    """Formats a float vector as a pgvector string literal ('[0.1,0.2]')."""
    return "[" + ",".join(f"{float(value):.6f}" for value in vector) + "]"


def fetch_message_for_indexing(conversation_id: int, message_id: int) -> dict | None:
    with connect() as connection:
        with connection.cursor() as cursor:
            cursor.execute(
                """
                SELECT c.user_id, m.conversation_id, m.id, cp.project_id, m.role, m.content
                FROM messages m
                JOIN conversations c ON c.id = m.conversation_id
                LEFT JOIN conversation_projects cp ON cp.conversation_id = c.id
                WHERE m.conversation_id = %s AND m.id = %s;
                """,
                (conversation_id, message_id),
            )
            row = cursor.fetchone()
    if not row:
        return None
    return {"user_id": row[0], "conversation_id": row[1], "message_id": row[2], "project_id": row[3], "role": row[4], "content": row[5]}


def get_memory_for_indexing(memory_id: int) -> dict | None:
    with connect() as connection:
        with connection.cursor() as cursor:
            cursor.execute("SELECT id, user_id, content FROM memories WHERE id = %s;", (memory_id,))
            row = cursor.fetchone()
    return {"id": row[0], "user_id": row[1], "content": row[2]} if row else None


def save_message_embeddings(
    user_id: int,
    conversation_id: int,
    message_id: int,
    project_id: int | None,
    chunks: list[str],
    vectors: list[list[float]],
    model: str,
) -> int:
    """Replaces any previous embeddings of this message for `model` and inserts the new chunks."""
    with connect() as connection:
        with connection.cursor() as cursor:
            cursor.execute(
                "DELETE FROM message_embeddings WHERE message_id = %s AND model = %s;",
                (message_id, model),
            )
            for chunk, vector in zip(chunks, vectors):
                cursor.execute(
                    """
                    INSERT INTO message_embeddings (user_id, conversation_id, message_id, project_id, chunk, embedding, model)
                    VALUES (%s, %s, %s, %s, %s, %s::vector, %s);
                    """,
                    (user_id, conversation_id, message_id, project_id, chunk, vector_literal(vector), model),
                )
            return len(chunks)


def save_memory_embedding(user_id: int, memory_id: int, vector: list[float], model: str) -> bool:
    with connect() as connection:
        with connection.cursor() as cursor:
            cursor.execute(
                "UPDATE memories SET embedding = %s::vector, model = %s WHERE id = %s AND user_id = %s;",
                (vector_literal(vector), model, memory_id, user_id),
            )
            return cursor.rowcount > 0


def search_message_chunks(
    user_id: int,
    query_vector_literal: str,
    project_id: int | None,
    k: int,
    threshold: float,
) -> list[dict]:
    """Cosine search over message chunks. Strict project scoping: when `project_id` is set, only chunks of that project match."""
    params: list = [query_vector_literal, user_id, threshold]
    project_clause = ""
    if project_id is not None:
        project_clause = " AND me.project_id = %s"
        params.append(project_id)
    params.append(k)
    query = f"""
        SELECT me.chunk, 1 - (me.embedding <=> %s::vector) AS score,
               me.conversation_id, c.title, me.created_at
        FROM message_embeddings me
        JOIN conversations c ON c.id = me.conversation_id
        WHERE me.user_id = %s AND 1 - (me.embedding <=> %s::vector) >= %s{project_clause}
        ORDER BY score DESC
        LIMIT %s;
    """
    with connect() as connection:
        with connection.cursor() as cursor:
            cursor.execute(query, tuple(params))
            rows = cursor.fetchall()
    return [
        {"text": row[0], "score": float(row[1]), "conversation_id": row[2], "title": row[3] or "", "when": str(row[4])}
        for row in rows
    ]


def search_memory_vectors(user_id: int, query_vector_literal: str, k: int, threshold: float) -> list[dict]:
    with connect() as connection:
        with connection.cursor() as cursor:
            cursor.execute(
                """
                SELECT content, 1 - (embedding <=> %s::vector) AS score, updated_at
                FROM memories
                WHERE user_id = %s AND embedding IS NOT NULL
                  AND 1 - (embedding <=> %s::vector) >= %s
                ORDER BY score DESC
                LIMIT %s;
                """,
                (query_vector_literal, user_id, query_vector_literal, threshold, k),
            )
            rows = cursor.fetchall()
    return [{"text": row[0], "score": float(row[1]), "when": str(row[2])} for row in rows]
```

- [ ] **Step 4: Run tests, verify pass**

Run: `cd backend && python -m pytest tests/test_semantic_store.py -v`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add backend/app/memory/semantic/__init__.py backend/app/memory/semantic/store.py backend/tests/test_semantic_store.py
git commit -m "feat: semantic memory vector store with pgvector search"
```

---

### Task 4: `semantic/embeddings.py` — EmbeddingService

**Files:**
- Create: `backend/app/memory/semantic/embeddings.py`
- Test: `backend/tests/test_semantic_embeddings.py`

**Interfaces:**
- Consumes: `fastembed` (lazy import, local mode only); `app_settings` key `'embeddings'` via `admin.queries.fetch_one`.
- Produces (used by Tasks 5/6/8/9):
  - `LOCAL_MODEL = "intfloat/multilingual-e5-small"`, `EMBEDDING_DIMENSION = 384`
  - `class EmbeddingError(RuntimeError)`
  - `class EmbeddingService` with `mode`, `base_url`, `model`, `api_key_env`, `model_id: str`, `dimension: int`, `embed_query(text: str) -> list[float]`, `embed_passages(texts: list[str]) -> list[list[float]]`
  - `load_embedding_config() -> dict`, `get_embedding_service() -> EmbeddingService`

- [ ] **Step 1: Write failing tests**

Create `backend/tests/test_semantic_embeddings.py`:

```python
import json
from unittest.mock import patch

import pytest

from app.memory.semantic import embeddings as emb


class FakeResponse:
    def __init__(self, payload):
        self._payload = payload

    def read(self):
        return json.dumps(self._payload).encode()

    def __enter__(self):
        return self

    def __exit__(self, *args):
        return False


def test_endpoint_embed_passages_posts_and_parses():
    service = emb.EmbeddingService(mode="endpoint", base_url="http://emb.local/v1", model="text-embed-x", api_key_env="EMB_KEY")
    payload = {"data": [{"embedding": [0.0] * 384}, {"embedding": [0.5] * 384}]}
    with patch.object(emb, "urlopen", return_value=FakeResponse(payload)) as fake_open:
        vectors = service.embed_passages(["hola", "mundo"])
    assert len(vectors) == 2 and len(vectors[0]) == 384
    request = fake_open.call_args[0][0]
    body = json.loads(request.data)
    assert body["input"] == ["hola", "mundo"] and body["model"] == "text-embed-x"
    assert "Authorization" not in dict(request.header_items())


def test_endpoint_rejects_wrong_dimension():
    service = emb.EmbeddingService(mode="endpoint", base_url="http://emb.local/v1", model="x")
    with patch.object(emb, "urlopen", return_value=FakeResponse({"data": [{"embedding": [0.0] * 100}]})):
        with pytest.raises(emb.EmbeddingError):
            service.embed_passages(["hola"])


def test_local_prefixes_e5_query_and_passage(monkeypatch):
    captured = {}

    def fake_embed(texts):
        captured["texts"] = list(texts)
        return [[0.1] * 384 for _ in texts]

    monkeypatch.setattr(emb, "_embed_with_local_model", fake_embed)
    service = emb.EmbeddingService(mode="local")
    service.embed_query("qué hablamos de postgres")
    assert captured["texts"] == ["query: qué hablamos de postgres"]
    service.embed_passages(["texto uno"])
    assert captured["texts"] == ["passage: texto uno"]


def test_get_embedding_service_reads_settings(monkeypatch):
    monkeypatch.setattr(emb, "load_embedding_config", lambda: {"mode": "endpoint", "base_url": "http://e/v1", "model": "m", "api_key_env": "K"})
    service = emb.get_embedding_service()
    assert service.mode == "endpoint" and service.model == "m" and service.base_url == "http://e/v1"
```

- [ ] **Step 2: Run tests, verify failure**

Run: `cd backend && python -m pytest tests/test_semantic_embeddings.py -v`
Expected: FAIL (`ModuleNotFoundError`)

- [ ] **Step 3: Implement `embeddings.py`**

Create `backend/app/memory/semantic/embeddings.py`:

```python
"""Embedding generation for semantic memory: local fastembed by default, optional OpenAI-compatible endpoint."""

import json
import logging
import os
import threading
from urllib.error import HTTPError, URLError
from urllib.request import Request as UrlRequest
from urllib.request import urlopen

logger = logging.getLogger("obsygpt.memory.semantic")

LOCAL_MODEL = "intfloat/multilingual-e5-small"
EMBEDDING_DIMENSION = 384


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
        return self.embed_passages([text], kind="query")[0]

    def embed_passages(self, texts: list[str], kind: str = "passage") -> list[list[float]]:
        if not texts:
            return []
        prepared = list(texts) if self.mode == "endpoint" else [f"{kind}: {text}" for text in texts]
        if self.mode == "endpoint":
            return self._embed_endpoint(prepared)
        return _embed_with_local_model(prepared)

    def _embed_endpoint(self, texts: list[str]) -> list[list[float]]:
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
            with urlopen(request, timeout=60) as response:
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
```

- [ ] **Step 4: Run tests, verify pass**

Run: `cd backend && python -m pytest tests/test_semantic_embeddings.py -v`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add backend/app/memory/semantic/embeddings.py backend/tests/test_semantic_embeddings.py
git commit -m "feat: EmbeddingService with local fastembed and endpoint modes"
```

---

### Task 5: `semantic/indexer.py` — chunking, background queue, hooks

**Files:**
- Create: `backend/app/memory/semantic/indexer.py`
- Modify: `backend/app/chat/conversations.py:223-234` (`save_message`) and the message-edit function in the same file
- Modify: `backend/app/memory/store.py:46` (`create_memory`)
- Test: `backend/tests/test_semantic_indexer.py`

**Interfaces:**
- Consumes: Task 3 store functions, Task 4 `get_embedding_service`/`embed_passages`.
- Produces:
  - `chunk_text(text: str, max_chars: int = 800) -> list[str]`
  - `class SemanticIndexer` with `enqueue_message(conversation_id: int, message_id: int) -> None`, `enqueue_memory(memory_id: int) -> None`, `index_message(conversation_id: int, message_id: int) -> None`, `index_memory(memory_id: int) -> None`
  - Module singleton `semantic_indexer = SemanticIndexer()`

- [ ] **Step 1: Write failing tests**

Create `backend/tests/test_semantic_indexer.py`:

```python
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
```

- [ ] **Step 2: Run tests, verify failure**

Run: `cd backend && python -m pytest tests/test_semantic_indexer.py -v`
Expected: FAIL

- [ ] **Step 3: Implement `indexer.py`**

Create `backend/app/memory/semantic/indexer.py`:

```python
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

    def index_message(self, conversation_id: int, message_id: int) -> None:
        record = self._store.fetch_message_for_indexing(conversation_id, message_id)
        if not record or record["role"] not in INDEXABLE_ROLES:
            return
        chunks = chunk_text(str(record["content"] or ""))
        if not chunks:
            return
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

    def index_memory(self, memory_id: int) -> None:
        record = self._store.get_memory_for_indexing(memory_id)
        if not record:
            return
        vector = self.service.embed_passages([str(record["content"] or "")])[0]
        self._store.save_memory_embedding(
            user_id=record["user_id"],
            memory_id=record["id"],
            vector=vector,
            model=self.service.model_id,
        )


semantic_indexer = SemanticIndexer()
```

- [ ] **Step 4: Hook `save_message` and message editing**

In `backend/app/chat/conversations.py`, add at module level:

```python
from ..memory.semantic.indexer import semantic_indexer
```

And change `save_message` (line ~223) to enqueue after the insert:

```python
def save_message(conversation_id: int, role: str, content: str) -> int:
    with app_db.connect() as connection:
        with connection.cursor() as cursor:
            cursor.execute(
                """
                INSERT INTO messages (conversation_id, role, content)
                VALUES (%s, %s, %s)
                RETURNING id;
                """,
                (conversation_id, role, content),
            )
            message_id = cursor.fetchone()[0]
    try:
        semantic_indexer.enqueue_message(conversation_id, message_id)
    except Exception:  # noqa: BLE001 - indexing is best-effort
        pass
    return message_id
```

In the same file, find the message-edit function that updates `messages` content (`update_user_message`, driven by `MessageEditPayload`) and append the same `try: semantic_indexer.enqueue_message(conversation_id, message_id) / except Exception: pass` block after a successful update (only for user-role edits if the function distinguishes roles).

- [ ] **Step 5: Hook `create_memory`**

In `backend/app/memory/store.py`, inside `create_memory` (line ~46), after the INSERT returns the row, add before `return memory`:

```python
    try:
        from .semantic.indexer import semantic_indexer

        semantic_indexer.enqueue_memory(memory["id"])
    except Exception:  # noqa: BLE001 - indexing is best-effort
        pass
```

- [ ] **Step 6: Run tests**

Run: `cd backend && python -m pytest tests/test_semantic_indexer.py tests/test_memory.py tests/test_chat_modes.py -v`
Expected: PASS (existing tests monkeypatch or tolerate the new hook; if a test constructs a real DB call path, it already uses fakes for `connect`).

- [ ] **Step 7: Commit**

```bash
git add backend/app/memory/semantic/indexer.py backend/app/chat/conversations.py backend/app/memory/store.py backend/tests/test_semantic_indexer.py
git commit -m "feat: background semantic indexer with message and memory hooks"
```

---

### Task 6: `semantic/retrieval.py` + chat injection

**Files:**
- Create: `backend/app/memory/semantic/retrieval.py`
- Modify: `backend/app/chat/routes.py:100-104` (after the `memory_context` block)
- Test: `backend/tests/test_semantic_retrieval.py`

**Interfaces:**
- Consumes: Task 3 `search_message_chunks`/`search_memory_vectors`, Task 4 `get_embedding_service`.
- Produces:
  - `DEFAULT_THRESHOLD = 0.35`
  - `search_semantic(user_id: int, query: str, project_id: int | None = None, k: int = 5, threshold: float = DEFAULT_THRESHOLD) -> list[dict]` — each hit: `{"text", "score", "source" ("memoria" | "conversación"), "conversation_id", "title", "when"}`
  - `build_semantic_context_block(user_id: int, query: str, project_id: int | None = None, k: int = 5) -> str` (empty string when no hits or on error)

- [ ] **Step 1: Write failing tests**

Create `backend/tests/test_semantic_retrieval.py`:

```python
from unittest.mock import patch

from app.memory.semantic import retrieval


class FakeService:
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
```

- [ ] **Step 2: Run tests, verify failure**

Run: `cd backend && python -m pytest tests/test_semantic_retrieval.py -v`
Expected: FAIL

- [ ] **Step 3: Implement `retrieval.py`**

Create `backend/app/memory/semantic/retrieval.py`:

```python
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
) -> list[dict]:
    """Merges memory and message-chunk hits, sorted by cosine score descending."""
    query = (query or "").strip()
    if not query:
        return []
    service = get_embedding_service()
    literal = semantic_store.vector_literal(service.embed_query(query))
    hits: list[dict] = []
    for hit in semantic_store.search_memory_vectors(user_id, literal, k, threshold):
        hits.append({**hit, "source": "memoria", "conversation_id": None, "title": ""})
    for hit in semantic_store.search_message_chunks(user_id, literal, project_id, k, threshold):
        hits.append({**hit, "source": "conversación"})
    hits.sort(key=lambda hit: hit["score"], reverse=True)
    return hits[:k]


def build_semantic_context_block(user_id: int, query: str, project_id: int | None = None, k: int = 5) -> str:
    """Best-effort context block: empty string when there are no hits or the service fails."""
    try:
        hits = search_semantic(user_id, query, project_id=project_id, k=k)
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
```

- [ ] **Step 4: Inject into `stream_message`**

In `backend/app/chat/routes.py`, extend the import at line 20:

```python
from ..memory.semantic.retrieval import build_semantic_context_block
```

Then immediately after the `memory_context` block (lines 101-104) insert:

```python
    semantic_context = build_semantic_context_block(user_id, user_message, project_id=(project or {}).get("id"))
    if semantic_context:
        provider_messages.append(ChatMessage(role="user", content=semantic_context))
        trace_store.add_event(agent_run_id, "semantic_memory_loaded", "Semantic memory hits injected")
```

- [ ] **Step 5: Run tests**

Run: `cd backend && python -m pytest tests/test_semantic_retrieval.py tests/test_chat_modes.py -q`
Expected: PASS

- [ ] **Step 6: Commit**

```bash
git add backend/app/memory/semantic/retrieval.py backend/app/chat/routes.py backend/tests/test_semantic_retrieval.py
git commit -m "feat: semantic retrieval with automatic chat context injection"
```

---

### Task 7: `memory_search` agent tool

**Files:**
- Create: `backend/app/agent/tools/memory.py`
- Modify: `backend/app/chat/specs.py:349-354` (register next to trigger tools)
- Test: `backend/tests/test_memory_search_tool.py`

**Interfaces:**
- Consumes: `ToolSpec`/`ToolResult` (`agent/tools/base.py`), `search_semantic` (Task 6).
- Produces: `class MemorySearchTool` with `spec` (name `memory_search`, permission `safe`) and `run(args: dict) -> ToolResult`.

- [ ] **Step 1: Write failing tests**

Create `backend/tests/test_memory_search_tool.py`:

```python
from unittest.mock import patch

from app.agent.tools.memory import MemorySearchTool


def test_run_requires_query():
    result = MemorySearchTool(user_id=1).run({})
    assert result.ok is False and "query" in result.output


def test_run_formats_hits_with_source():
    hits = [{"text": "hablamos de pgvector", "score": 0.9, "source": "conversación", "conversation_id": 3, "title": "Chat DB", "when": "2026-10-01T10:00:00"}]
    with patch("app.agent.tools.memory.search_semantic", return_value=hits):
        result = MemorySearchTool(user_id=1).run({"query": "pgvector"})
    assert result.ok is True
    assert "1." in result.output and "Chat DB" in result.output and "hablamos de pgvector" in result.output


def test_run_degrades_when_service_unavailable():
    with patch("app.agent.tools.memory.search_semantic", side_effect=RuntimeError("down")):
        result = MemorySearchTool(user_id=1).run({"query": "pgvector"})
    assert result.ok is False and "disponible" in result.output


def test_run_reports_no_hits():
    with patch("app.agent.tools.memory.search_semantic", return_value=[]):
        result = MemorySearchTool(user_id=1).run({"query": "nada"})
    assert result.ok is True and "No encontré" in result.output
```

- [ ] **Step 2: Run tests, verify failure**

Run: `cd backend && python -m pytest tests/test_memory_search_tool.py -v`
Expected: FAIL

- [ ] **Step 3: Implement the tool**

Create `backend/app/agent/tools/memory.py`:

```python
"""Agent tool: search the user's persistent semantic memory."""

from .base import ToolResult, ToolSpec
from ..memory.semantic.retrieval import search_semantic


class MemorySearchTool:
    spec = ToolSpec(
        name="memory_search",
        description=(
            "Busca en la memoria persistente del usuario (recuerdos guardados y conversaciones pasadas) "
            "los fragmentos más relevantes para una consulta. Úsala cuando necesites contexto histórico."
        ),
        parameters='{"query": "<texto a buscar>", "k": "<opcional: máximo de resultados, por defecto 5>"}',
        permission="safe",
    )

    def __init__(self, user_id: int):
        self.user_id = user_id

    def run(self, args: dict) -> ToolResult:
        query = str(args.get("query", "")).strip()
        if not query:
            return ToolResult(ok=False, output="Debes indicar 'query': el texto a buscar en la memoria.")
        try:
            k = int(args.get("k", 5))
        except (TypeError, ValueError):
            k = 5
        k = max(1, min(k, 20))
        try:
            hits = search_semantic(self.user_id, query, k=k)
        except Exception:  # noqa: BLE001
            return ToolResult(ok=False, output="La memoria semántica no está disponible en este momento.")
        if not hits:
            return ToolResult(ok=True, output="No encontré fragmentos relevantes en la memoria para esa consulta.")
        lines = []
        for index, hit in enumerate(hits, start=1):
            origin = hit.get("title") or (f"conversación #{hit['conversation_id']}" if hit.get("conversation_id") else hit["source"])
            text = hit["text"].replace("\n", " ").strip()
            if len(text) > 400:
                text = text[:400] + "..."
            lines.append(f"{index}. [{origin}, {str(hit['when'])[:10]}] {text}")
        return ToolResult(ok=True, output="\n".join(lines))
```

- [ ] **Step 4: Register in the agent registry**

In `backend/app/chat/specs.py`, inside `build_agent_tool_registry`, extend the `if user_id is not None:` block that registers trigger tools (line ~349):

```python
    if user_id is not None:
        from ..agent.tools.triggers import CancelTriggerTool, MyTriggersTool, ScheduleTriggerTool

        registry.register(ScheduleTriggerTool(user_id=user_id, agent_id=agent_id))
        registry.register(MyTriggersTool(user_id=user_id))
        registry.register(CancelTriggerTool(user_id=user_id))
        from ..agent.tools.memory import MemorySearchTool

        registry.register(MemorySearchTool(user_id=user_id))
```

- [ ] **Step 5: Run tests**

Run: `cd backend && python -m pytest tests/test_memory_search_tool.py tests/test_triggers.py tests/test_subagents.py -q`
Expected: PASS

- [ ] **Step 6: Commit**

```bash
git add backend/app/agent/tools/memory.py backend/app/chat/specs.py backend/tests/test_memory_search_tool.py
git commit -m "feat: memory_search agent tool backed by semantic retrieval"
```

---

### Task 8: Admin settings endpoints (embeddings config + reindex trigger)

**Files:**
- Modify: `backend/app/admin/settings.py` (extend the existing settings router)
- Test: `backend/tests/test_admin_payloads.py` (append tests, following its `FakeRequest`/`fake_execute_returning` pattern)

**Interfaces:**
- Consumes: `app_settings` key `'embeddings'` (Task 4 reads it); `start_reindex`/`reindex_status` (Task 9).
- Produces (consumed by Task 10 frontend):
  - `GET /api/admin/settings/embeddings` → `{"embeddings": {...}}`
  - `PUT /api/admin/settings/embeddings` → merged payload, validates `mode in {"local","endpoint"}`, requires `base_url`+`model` when mode is `endpoint`
  - `POST /api/admin/embeddings/reindex` → `{"reindex": {...}}` (409 if already running)
  - `GET /api/admin/embeddings/reindex` → `{"reindex": {...}}`

- [ ] **Step 1: Write failing tests**

Append to `backend/tests/test_admin_payloads.py` (reuse its existing `FakeRequest`, `fake_fetch_one` and `fake_execute_returning` fixtures — copy their exact construction from the `test_tasks_settings_roundtrip` test at line ~312):

```python
def test_embeddings_settings_payload_defaults_to_local():
    payload = EmbeddingsSettingsPayload()
    assert payload.mode is None and payload.base_url is None


def test_embeddings_settings_rejects_endpoint_without_base_url():
    with patch("app.admin.queries.fetch_one", return_value=None), \
         patch("app.admin.queries.execute_returning", return_value={"value": {}}):
        response = update_embeddings_settings(EmbeddingsSettingsPayload(mode="endpoint"), FakeRequest())
    assert response["embeddings"]["mode"] == "local"  # invalid merge falls back; see implementation
```

(Adapt fixtures 1:1 from `test_tasks_settings_roundtrip` — the fake request exposes `.session = {"user_id": 1}` and the audit store is patched the same way.)

- [ ] **Step 2: Run tests, verify failure**

Run: `cd backend && python -m pytest tests/test_admin_payloads.py -k embeddings -v`
Expected: FAIL (`EmbeddingsSettingsPayload` not defined)

- [ ] **Step 3: Implement the endpoints**

In `backend/app/admin/settings.py` add (after the guardrails endpoints):

```python
class EmbeddingsSettingsPayload(BaseModel):
    mode: Literal["local", "endpoint"] | None = None
    base_url: str | None = Field(default=None, max_length=500)
    model: str | None = Field(default=None, max_length=200)
    api_key_env: str | None = Field(default=None, max_length=100)


def _merged_embeddings_settings(settings: EmbeddingsSettingsPayload) -> dict:
    current_row = queries.fetch_one("SELECT value FROM app_settings WHERE key = 'embeddings';", ())
    current = current_row.get("value", {}) if current_row else {}
    payload = {**current, **{key: value for key, value in settings.model_dump().items() if value is not None}}
    if payload.get("mode") == "endpoint" and (not payload.get("base_url") or not payload.get("model")):
        payload["mode"] = "local"  # endpoint without base_url/model is not usable: fall back to local
    return payload


@router.get("/settings/embeddings")
def list_embeddings_settings(request: Request):
    auth.require_admin(request)
    row = queries.fetch_one("SELECT value FROM app_settings WHERE key = 'embeddings';", ())
    return {"embeddings": (row or {}).get("value", {"mode": "local"})}


@router.put("/settings/embeddings")
def update_embeddings_settings(settings: EmbeddingsSettingsPayload, request: Request):
    auth.require_admin(request)
    payload = _merged_embeddings_settings(settings)
    row = queries.execute_returning(
        """
        INSERT INTO app_settings (key, value)
        VALUES ('embeddings', %s::json)
        ON CONFLICT (key) DO UPDATE SET value = EXCLUDED.value
        RETURNING value;
        """,
        (json.dumps(payload),),
    )
    audit_module.AuditStore().add_log(
        actor_user_id=int(request.session.get("user_id")),
        action="embeddings_settings.updated",
        target_type="settings",
        target_id=None,
        metadata=payload,
    )
    return {"embeddings": row["value"]}


@router.post("/embeddings/reindex")
def trigger_reindex(request: Request):
    auth.require_admin(request)
    from ..memory.semantic.reindex import reindex_status, start_reindex

    started = start_reindex()
    if not started:
        raise HTTPException(status_code=409, detail="Ya hay un reindexado en curso.")
    audit_module.AuditStore().add_log(
        actor_user_id=int(request.session.get("user_id")),
        action="embeddings.reindex_started",
        target_type="settings",
        target_id=None,
        metadata={},
    )
    return {"reindex": reindex_status()}


@router.get("/embeddings/reindex")
def get_reindex_status(request: Request):
    auth.require_admin(request)
    from ..memory.semantic.reindex import reindex_status

    return {"reindex": reindex_status()}
```

Add the needed imports at the top of the file: `from typing import Literal` and `from fastapi import APIRouter, HTTPException, Request`.

- [ ] **Step 4: Run tests**

Run: `cd backend && python -m pytest tests/test_admin_payloads.py -q`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add backend/app/admin/settings.py backend/tests/test_admin_payloads.py
git commit -m "feat: admin endpoints for embeddings settings and reindex trigger"
```

---

### Task 9: `semantic/reindex.py` — reindex job

**Files:**
- Create: `backend/app/memory/semantic/reindex.py`
- Modify: `backend/app/memory/semantic/store.py` (add the two "missing index" queries below)
- Test: `backend/tests/test_semantic_reindex.py`

**Interfaces:**
- Consumes: Task 3 store, Task 4 service, `app_settings` key `'embeddings_reindex'` via `admin.queries`.
- Produces (consumed by Task 8 endpoints):
  - `start_reindex() -> bool` (False when already running; spawns daemon thread)
  - `reindex_status() -> dict` — `{"running": bool, "processed": int, "total": int, "error": str | None}`
  - store additions: `count_missing_index(model: str) -> int`, `list_missing_memories(model: str) -> list[dict]`, `list_missing_messages(model: str, limit: int = 50) -> list[dict]` (keys: `user_id, conversation_id, message_id, project_id, content`)

- [ ] **Step 1: Write failing tests**

Create `backend/tests/test_semantic_reindex.py`:

```python
from unittest.mock import patch

from app.memory.semantic import reindex


def test_start_reindex_refuses_when_running(monkeypatch):
    monkeypatch.setattr(reindex, "reindex_status", lambda: {"running": True})
    assert reindex.start_reindex() is False


def test_status_defaults(monkeypatch):
    monkeypatch.setattr(reindex, "load_embedding_config", lambda: {})
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
        def count_missing_index(self, model):
            return len(messages) + len(memories)

        def list_missing_messages(self, model, limit=50):
            return messages if not indexed else []

        def list_missing_memories(self, model):
            return memories if not indexed else []

        def save_message_embeddings(self, **kwargs):
            indexed.append(kwargs)

        def save_memory_embedding(self, **kwargs):
            indexed.append(kwargs)

    with patch.object(reindex, "get_embedding_service", lambda: FakeService()), \
         patch.object(reindex, "_store", FakeStore()), \
         patch.object(reindex, "_set_status") as status_calls, \
         patch.object(reindex, "fetch_one", return_value=None):
        reindex.run_reindex()

    assert len(indexed) == 2
    assert status_calls.call_args[0][0]["running"] is False
```

- [ ] **Step 2: Run tests, verify failure**

Run: `cd backend && python -m pytest tests/test_semantic_reindex.py -v`
Expected: FAIL

- [ ] **Step 3: Add store queries**

Append to `backend/app/memory/semantic/store.py`:

```python
def count_missing_index(model: str) -> int:
    """Total pending units (memories + messages) not yet embedded with `model`."""
    with connect() as connection:
        with connection.cursor() as cursor:
            cursor.execute(
                """
                SELECT (
                    (SELECT COUNT(*) FROM memories WHERE embedding IS NULL OR model IS DISTINCT FROM %s)
                    + (SELECT COUNT(*) FROM messages m
                       JOIN conversations c ON c.id = m.conversation_id
                       WHERE m.role IN ('user', 'assistant')
                         AND NOT EXISTS (
                             SELECT 1 FROM message_embeddings me
                             WHERE me.message_id = m.id AND me.model = %s
                         ))
                );
                """,
                (model, model),
            )
            return int(cursor.fetchone()[0])


def list_missing_memories(model: str) -> list[dict]:
    with connect() as connection:
        with connection.cursor() as cursor:
            cursor.execute(
                "SELECT id, user_id, content FROM memories WHERE embedding IS NULL OR model IS DISTINCT FROM %s ORDER BY id;",
                (model,),
            )
            rows = cursor.fetchall()
    return [{"id": row[0], "user_id": row[1], "content": row[2]} for row in rows]


def list_missing_messages(model: str, limit: int = 50) -> list[dict]:
    with connect() as connection:
        with connection.cursor() as cursor:
            cursor.execute(
                """
                SELECT c.user_id, m.conversation_id, m.id, cp.project_id, m.content
                FROM messages m
                JOIN conversations c ON c.id = m.conversation_id
                LEFT JOIN conversation_projects cp ON cp.conversation_id = c.id
                WHERE m.role IN ('user', 'assistant')
                  AND NOT EXISTS (
                      SELECT 1 FROM message_embeddings me
                      WHERE me.message_id = m.id AND me.model = %s
                  )
                ORDER BY m.id
                LIMIT %s;
                """,
                (model, limit),
            )
            rows = cursor.fetchall()
    return [
        {"user_id": row[0], "conversation_id": row[1], "message_id": row[2], "project_id": row[3], "content": row[4]}
        for row in rows
    ]
```

- [ ] **Step 4: Implement `reindex.py`**

Create `backend/app/memory/semantic/reindex.py`:

```python
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


def run_reindex() -> None:
    status = reindex_status()
    try:
        service = get_embedding_service()
        model = service.model_id
        total = _store.count_missing_index(model)
        status = {"running": True, "processed": 0, "total": total, "error": None}
        _set_status(status)
        processed = 0
        while True:
            messages = _store.list_missing_messages(model, limit=BATCH_SIZE)
            memories = _store.list_missing_memories(model)[:BATCH_SIZE]
            if not messages and not memories:
                break
            for record in messages:
                from .indexer import SemanticIndexer

                worker = SemanticIndexer(service=service, store=_store, start_worker=False)
                worker.index_message(record["conversation_id"], record["message_id"])
                processed += 1
                _set_status({"running": True, "processed": processed, "total": total, "error": None})
            for record in memories:
                from .indexer import SemanticIndexer

                worker = SemanticIndexer(service=service, store=_store, start_worker=False)
                worker.index_memory(record["id"])
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
```

- [ ] **Step 5: Run tests**

Run: `cd backend && python -m pytest tests/test_semantic_reindex.py tests/test_semantic_store.py -q`
Expected: PASS

- [ ] **Step 6: Commit**

```bash
git add backend/app/memory/semantic/reindex.py backend/app/memory/semantic/store.py backend/tests/test_semantic_reindex.py
git commit -m "feat: semantic memory full reindex job with progress status"
```

---

### Task 10: Frontend — Embeddings section in Settings > Modelo

**Files:**
- Modify: `frontend-modern/src/views/SettingsView.tsx` (new section + component)
- Modify: `frontend-modern/src/App.tsx:1827` area (search entry for the new subtab)

**Interfaces:**
- Consumes: Task 8 endpoints `GET/PUT /api/admin/settings/embeddings`, `POST/GET /api/admin/embeddings/reindex` (through the same request helper the view already uses for providers — check its import at the top of `SettingsView.tsx` and reuse it; do not introduce a second HTTP helper).
- Produces: settings UI; no new exports.

- [ ] **Step 1: Add the Embeddings section to SettingsView**

In `frontend-modern/src/views/SettingsView.tsx`, add a `EmbeddingsSection` component (self-contained state, same class names as the providers panel) and render it when `settingsTab === "modelo" && settingsSubTab === "embeddings"`:

```tsx
function EmbeddingsSection() {
  const [config, setConfig] = useState<{ mode: string; base_url: string; model: string; api_key_env: string } | null>(null);
  const [status, setStatus] = useState<{ running: boolean; processed: number; total: number; error: string | null } | null>(null);
  const [saving, setSaving] = useState(false);
  const [saved, setSaved] = useState(false);

  const load = useCallback(async () => {
    const res = await fetch("/api/admin/settings/embeddings", { credentials: "include" });
    if (res.ok) setConfig((await res.json()).embeddings);
    const st = await fetch("/api/admin/embeddings/reindex", { credentials: "include" });
    if (st.ok) setStatus((await st.json()).reindex);
  }, []);

  useEffect(() => {
    load().catch(() => undefined);
  }, [load]);

  if (!config) return null;

  const save = async () => {
    setSaving(true);
    setSaved(false);
    try {
      const res = await fetch("/api/admin/settings/embeddings", {
        method: "PUT",
        headers: { "Content-Type": "application/json" },
        credentials: "include",
        body: JSON.stringify(config),
      });
      if (res.ok) {
        setConfig((await res.json()).embeddings);
        setSaved(true);
      }
    } finally {
      setSaving(false);
    }
  };

  const reindex = async () => {
    const res = await fetch("/api/admin/embeddings/reindex", { method: "POST", credentials: "include" });
    if (res.ok) setStatus((await res.json()).reindex);
  };

  return (
    <section className="panel">
      <h2>Embeddings (memoria semántica)</h2>
      <div className="config-form">
        <label>
          Modo
          <select value={config.mode || "local"} onChange={(event) => setConfig({ ...config, mode: event.target.value })}>
            <option value="local">Local (rápido, sin API key)</option>
            <option value="endpoint">Endpoint compatible con OpenAI</option>
          </select>
        </label>
        {config.mode === "endpoint" && (
          <>
            <label>
              Base URL
              <input value={config.base_url || ""} onChange={(event) => setConfig({ ...config, base_url: event.target.value })} placeholder="http://host:8000/v1" />
            </label>
            <label>
              Modelo
              <input value={config.model || ""} onChange={(event) => setConfig({ ...config, model: event.target.value })} placeholder="nombre-del-modelo" />
            </label>
            <label>
              Variable de entorno con la API key (opcional)
              <input value={config.api_key_env || ""} onChange={(event) => setConfig({ ...config, api_key_env: event.target.value })} placeholder="EMBEDDINGS_API_KEY" />
            </label>
          </>
        )}
        <div>
          <button type="button" onClick={save} disabled={saving}>{saving ? "Guardando..." : "Guardar cambios"}</button>
          {saved && <span className="chip">Guardado</span>}
        </div>
        <div>
          <button type="button" onClick={reindex} disabled={Boolean(status?.running)}>Reindexar memoria</button>
          {status?.running && <span className="chip">{status.processed}/{status.total} procesados</span>}
          {status?.error && <span className="chip">{status.error}</span>}
        </div>
      </div>
    </section>
  );
}
```

Render it in the tab block (next to the providers condition at line ~62):

```tsx
{settingsSearch.trim() === "" && settingsTab === "modelo" && settingsSubTab === "embeddings" && <EmbeddingsSection />}
```

Add the missing React imports (`useCallback`, `useEffect`, `useState`) if not already imported in the file.

- [ ] **Step 2: Register the subtab in the settings search index**

In `frontend-modern/src/App.tsx`, add next to the "Proveedores guardados" entry (line ~1827):

```tsx
{ label: "Embeddings", keywords: "embeddings memoria semantica vector reindexar", tab: "modelo", sub: "embeddings" },
```

- [ ] **Step 3: Build check**

Run: `cd frontend-modern && npm run build`
Expected: build succeeds with no TypeScript errors.

- [ ] **Step 4: Commit**

```bash
git add frontend-modern/src/views/SettingsView.tsx frontend-modern/src/App.tsx
git commit -m "feat: embeddings settings section with reindex button"
```

---

### Task 11: README + final verification

**Files:**
- Modify: `README.md` (Qué incluye + Variables de entorno)

- [ ] **Step 1: README bullet in "Qué incluye"**

Add after the "Memoria persistente y hábitos" bullet:

```markdown
- **Memoria semántica** — recuerdos y conversaciones pasadas se indexan con embeddings locales (pgvector): los agentes recuperan contexto relevante automáticamente y pueden buscar a fondo con la tool `memory_search`. Configurable en Ajustes > Modelo > Embeddings (local o endpoint compatible con OpenAI).
```

- [ ] **Step 2: README env var row**

Add to the advanced variables paragraph: `FASTEMBED_CACHE_PATH` (directorio de caché del modelo de embeddings; por defecto el cache local de fastembed — en Docker se monta en el volumen de voz).

- [ ] **Step 3: Full verification**

```bash
cd backend && python -m pytest -q
cd ../frontend-modern && npm run build
```

Expected: all tests pass, frontend builds.

- [ ] **Step 4: Commit**

```bash
git add README.md
git commit -m "docs: document semantic memory feature and embeddings env var"
```

---

## Post-implementation manual checks (dev environment)

1. `docker compose up -d postgres && cd backend && alembic upgrade head` — migration 0022 applies.
2. Chat a few messages, then `SELECT COUNT(*) FROM message_embeddings;` — rows appear (first message may take seconds while fastembed downloads).
3. Ask the agent "¿de qué hablamos antes sobre X?" — verify the trace shows `semantic_memory_loaded` and the tool `memory_search` works when enabled in the agent's tools list.
4. Settings > Modelo > Embeddings: switch to endpoint mode with a bad URL — chat keeps working (degradation) and the indexer logs warnings.
