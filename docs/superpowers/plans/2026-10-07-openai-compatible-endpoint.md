# OpenAI-Compatible Endpoint (/v1) Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Expose ObsyGPT agents as OpenAI-compatible models (`POST /v1/chat/completions`, `GET /v1/models`) authenticated with personal API keys, stateless but traced, safe-tools-only, streaming and non-streaming.

**Architecture:** New module `backend/app/v1/` with `keys.py` (key generation/hash/auth), `routes.py` (OpenAI-shape endpoints + request resolution + response formatting), reusing `AgentLoop` (agentic, safe-filtered registry), `WorkflowRuntime._run_agent` (non-agentic with fallbacks), and the chat context builders. Migration 0023: `api_keys` table + nullable `agent_runs.conversation_id`. Nginx `/v1/` location. UI: Seguridad > Claves de API.

**Tech Stack:** FastAPI / psycopg3 / SHA-256 key hashing / SSE / React+TS frontend.

**Spec:** `docs/superpowers/specs/2026-10-07-openai-compatible-endpoint-design.md`

## Global Constraints

- Tests DB-free with fakes (CI has no Postgres): `backend/tests/test_v1_*.py`.
- Key format: `ogpt-` + `secrets.token_urlsafe(32)`; stored as SHA-256 hex hash; prefix = first 8 chars after the `ogpt-` prefix (for display).
- Responses/errors follow OpenAI shape exactly: success `{id: "chatcmpl-<hex>", object: "chat.completion", created, model, choices, usage}`; error `{"error": {"message", "type", "code"}}`.
- Tools: registry filtered to `permission == "safe"` specs only; no `ApprovalRequiredError` can ever propagate from /v1 runs.
- UI copy: Spain Spanish, no voseo.
- Conventional commits, one per task; full suite green (`cd backend; python -m pytest -q`) after every task.
- Reuse, do not duplicate: `build_user_instructions_block`, `build_memory_context`, `build_semantic_context_block` (from `chat/routes.py` imports), `AgentLoop`, `WorkflowRuntime`, `AuthRateLimiter` pattern.

---

### Task 1: Migration 0023 (api_keys + nullable run columns)

**Files:**
- Create: `backend/migrations/versions/0023_api_keys_openai_endpoint.py`
- Modify: `database/schema.sql`
- Test: run full suite + `alembic upgrade head` against local postgres

**Interfaces:** Produces table `api_keys` (per spec SQL) and nullable `agent_runs.conversation_id` / `agent_runs.message_id`.

- [ ] Step 1: Write migration (revision `0023_api_keys`, down_revision `0022_semantic_memory` — verify both ids first), content per spec: CREATE TABLE api_keys + index + the two `ALTER TABLE agent_runs ALTER COLUMN ... DROP NOT NULL`. Downgrade: drop table, re-add NOT NULL guarded (`WHERE conversation_id IS NOT NULL` equivalent — use plain re-add inside a transaction after null-check delete: `DELETE FROM agent_runs WHERE conversation_id IS NULL;` then SET NOT NULL).
- [ ] Step 2: Mirror in `database/schema.sql` (append api_keys block; update agent_runs column defs to remove NOT NULL on those two).
- [ ] Step 3: `cd backend; python -m pytest -q` green; `alembic upgrade head` applies (local postgres 5433; if DB unreachable, report BLOCKED).
- [ ] Step 4: Commit `feat: migration 0023 api keys and nullable trace runs`

---

### Task 2: `v1/keys.py` — key lifecycle + authentication

**Files:**
- Create: `backend/app/v1/__init__.py` (empty), `backend/app/v1/keys.py`
- Test: `backend/tests/test_v1_keys.py`

**Interfaces (produces):**
- `generate_key() -> tuple[str, str, str]` — (key, key_hash, prefix); key = `ogpt-` + `secrets.token_urlsafe(32)`; hash = SHA-256 hex of the full key; prefix = first 8 chars of the part after `ogpt-`.
- `create_api_key(user_id: int, name: str) -> dict` — inserts, returns `{"id", "name", "prefix", "created_at", "key": <plaintext, only here>}`.
- `list_api_keys(user_id: int) -> list[dict]` — `{"id", "name", "prefix", "created_at", "last_used_at", "revoked_at"}` (never the key).
- `revoke_api_key(user_id: int, key_id: int) -> bool`
- `authenticate_key(authorization_header: str | None) -> int` — parses `Bearer ogpt-...`, hashes, looks up non-revoked row, updates `last_used_at` (best-effort try/except), returns `user_id`; raises `KeyAuthError` (custom `RuntimeError`) with messages for missing/invalid/revoked.

- [ ] Step 1: Failing tests (fakes for `connect`): generate format, create returns plaintext once + stores hash, authenticate happy path + missing header + malformed + unknown + revoked, revoke.
- [ ] Step 2: RED → implement → GREEN (store functions inline in keys.py using `..db.connect`; `import hashlib; hashlib.sha256(key.encode()).hexdigest()`).
- [ ] Step 3: Full suite green. Commit `feat: api key generation and bearer authentication for v1`

---

### Task 3: Admin endpoints for key management

**Files:**
- Create: `backend/app/admin/api_keys.py` (APIRouter mounted in `admin/routes.py` alongside the others)
- Modify: `backend/app/admin/routes.py` (import + include router)
- Test: `backend/tests/test_admin_api_keys.py`

**Interfaces:** `GET /api/admin/api-keys` (list own), `POST /api/admin/api-keys` (`{"name": str}` → 201 with `{"api_key": {..., "key": plaintext}}`), `POST /api/admin/api-keys/{id}/revoke`. Audit log actions `api_key.created` / `api_key.revoked` (metadata: prefix + name, never the key).

- [ ] Step 1: Failing tests with FakeRequest session + patched queries (follow `test_tasks_settings_roundtrip` fixture style). RED.
- [ ] Step 2: Implement router (require_user — keys are per-user, not admin-only) → GREEN.
- [ ] Step 3: Full suite green. Commit `feat: admin endpoints to manage personal api keys`

---

### Task 4: `v1/routes.py` — non-streaming `POST /v1/chat/completions` + `GET /v1/models`

**Files:**
- Create: `backend/app/v1/routes.py`
- Modify: `backend/app/main.py` (mount router)
- Test: `backend/tests/test_v1_chat.py`

**Interfaces:**
- `resolve_agent(model: str) -> AgentSpec | None` — by exact name (case-insensitive) or `agent-{id}`; only `enabled = true` agents. Reuses `chat_specs.get_workflow_spec(None, agent_id)` for the spec (provider, fallbacks, agentic_mode).
- `build_v1_messages(user_id: int, agent: AgentSpec, client_messages: list[dict]) -> list[ChatMessage]` — system prompt of agent + client messages mapped to ChatMessage + injected context blocks (user instructions, memory, semantic recall via `build_semantic_context_block(user_id, last_user_content)`). Client `system` role messages append after the agent's system prompt.
- `POST /v1/chat/completions`: authenticate → resolve → build messages → execute:
  - agentic: `AgentLoop(trace_store=TraceStore()).run(agent_run_id, agent.system_prompt, agent.provider_type, ..., tool_specs=[specs of safe tools only], messages, fallbacks=agent.fallbacks)` collecting the iterator; safe-only filtering: build registry via `chat_specs.build_agent_tool_registry(user_id=user_id, agent_id=agent.id)`, `allowed = {s.name for s in registry.list_specs() if s.permission == "safe"}`, `registry.filter_to(allowed)`, `execute_tool=lambda name, args: registry.run(name, args)`.
  - non-agentic: `WorkflowRuntime(trace_store).` direct path — reuse `WorkflowRuntime()._run_agent` via `stream_workflow` on a single-agent WorkflowSpec (it already does fallbacks).
- OpenAI response shape + `usage` estimate `{"prompt_tokens": chars//4, "completion_tokens": ..., "total_tokens": ...}`.
- Errors OpenAI-shape: 401 `invalid_api_key`, 404 `model_not_found`, 400 `invalid_request_error`.
- Rate limit: module-level `AuthRateLimiter`-style limiter keyed by key hash (reuse `auth.rate_limit_auth` approach with action "v1_chat").

- [ ] Step 1: Failing tests (FakeRequest-free — call route functions directly with a fake `Request` exposing `.headers` and `.client`; fake `AgentLoop`/`WorkflowRuntime` via monkeypatch; fake key auth via patched `authenticate_key`). Cases: models list shape; completions happy path (non-agentic fake returns "Hola desde ObsyGPT"); unknown model 404 shape; missing auth 401 shape; temperature default passthrough; agentic path uses safe-filtered registry (assert registry.filter_to called with only safe names).
- [ ] Step 2: RED → implement → GREEN. Mount in `main.py` (find where admin/chat routers are included; add `from .v1.routes import router as v1_router` + include).
- [ ] Step 3: Full suite green. Commit `feat: OpenAI-compatible chat completions and models endpoints`

---

### Task 5: Streaming SSE support

**Files:**
- Modify: `backend/app/v1/routes.py`
- Test: `backend/tests/test_v1_streaming.py`

**Interfaces:** `stream=true` → `StreamingResponse(media_type="text/event-stream")` emitting `data: {"id","object":"chat.completion.chunk","choices":[{"delta":{"content": "..."}}]}\n\n` per piece and `data: [DONE]\n\n` at the end. Agentic agents: each iterator piece from `AgentLoop.run` becomes one chunk. Non-agentic: stream the generator directly.

- [ ] Step 1: Failing tests: fake iterator yields "Hola" / " mundo" → body contains two delta chunks + `[DONE]`; content-type `text/event-stream`.
- [ ] Step 2: RED → implement → GREEN. Full suite green.
- [ ] Step 3: Commit `feat: streaming SSE support for v1 chat completions`

---

### Task 6: Nginx `/v1/` location

**Files:**
- Modify: `frontend-modern/nginx.conf`

- [ ] Step 1: Duplicate the `/api/` block as `location /v1/` (same proxy settings).
- [ ] Step 2: Commit `feat: proxy /v1 to backend in nginx`

---

### Task 7: Frontend — Seguridad > Claves de API

**Files:**
- Modify: `frontend-modern/src/views/SettingsView.tsx` (new `ApiKeysSection` rendered for `settingsTab === "seguridad" && (settingsSubTab === "" || settingsSubTab === "api")`; follow `EmbeddingsSection` patterns: `apiRequest`, `isAdmin` gate not required — section is per-user)
- Modify: `frontend-modern/src/App.tsx` (search-index entry `{ label: "Claves de API", keywords: "api keys token clave acceso v1", tab: "seguridad", sub: "api" }`)

**Interfaces:** State: keys list, create form (name), created-key-once display with copy button, revoke with `confirm()`. Types: `{ id, name, prefix, created_at, last_used_at, revoked_at }`.

- [ ] Step 1: Implement section (load on mount, create → show plaintext once, revoke → reload).
- [ ] Step 2: `cd frontend-modern; npm run build` green. Commit `feat: api keys management section in security settings`

---

### Task 8: README + final verification

- [ ] Step 1: README: "Qué incluye" bullet ("Endpoint OpenAI-compatible — expone tus agentes como modelos en `/v1/chat/completions` con API keys personales...") + short usage example (curl) in the advanced section.
- [ ] Step 2: `cd backend; python -m pytest -q` + `cd frontend-modern; npm run build` green.
- [ ] Step 3: Commit `docs: document OpenAI-compatible endpoint and api keys`

---

## Post-implementation manual checks (dev)

1. `curl -H "Authorization: Bearer ogpt-..." http://localhost:3001/v1/models` → agent list.
2. Non-streaming + streaming chat completion against `agent-6`.
3. Trace view shows the stateless runs.
4. Revoked key → 401.
