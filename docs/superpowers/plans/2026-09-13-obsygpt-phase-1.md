# ObsyGPT Phase 1 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build the first working ObsyGPT slice: full rebrand, modular FastAPI backend, provider router, modern frontend shell, configurable agents, and visible single-agent traces.

**Architecture:** Keep FastAPI and PostgreSQL as the system core, introduce focused backend modules, and replace the Flask UI with a modern React/TypeScript frontend. Preserve the existing text chat behavior through an OpenRouter provider adapter while adding the interfaces needed for future providers, skills, MCPs, internet tools, workflows, and multimodal attachments.

**Tech Stack:** Python, FastAPI, PostgreSQL, psycopg, OpenAI Python SDK, React, TypeScript, Vite, CSS modules/plain CSS, pytest.

## Global Constraints

- Product name must be `ObsyGPT`; remove user-facing and internal references to previous product names.
- Session cookie must be named `obsygpt_session`.
- Phase 1 must keep text chat working with OpenRouter before adding other providers.
- Phase 1 must expose visible trace events for the selected agent run.
- Phase 1 must use a modern frontend instead of Flask templates for the main UI.
- Phase 1 must not implement arbitrary code execution or unrestricted browser automation.
- MCP, skills, internet, multimodal files, and additional providers must have schema/API placeholders that are concrete and testable, but their full runtimes can be implemented in later phases.
- Do not commit unless the user explicitly requests it.

---

## File Structure

Create or modify these files during Phase 1:

- Modify: `README.md` for ObsyGPT setup and architecture.
- Modify: `database/schema.sql` to add concrete Phase 1 tables.
- Create: `backend/app/main.py` as the FastAPI app entrypoint.
- Create: `backend/app/config.py` for environment parsing.
- Create: `backend/app/db.py` for database connection helpers.
- Create: `backend/app/auth/routes.py` for auth routes.
- Create: `backend/app/chat/routes.py` for conversation and message routes.
- Create: `backend/app/providers/base.py` for provider interfaces and message types.
- Create: `backend/app/providers/openrouter.py` for the first provider adapter.
- Create: `backend/app/providers/registry.py` for provider lookup.
- Create: `backend/app/agents/runtime.py` for single-agent execution.
- Create: `backend/app/traces/store.py` for trace persistence.
- Create: `backend/app/admin/routes.py` for providers, models, agents, skills, MCPs, and workflow metadata APIs.
- Modify: `backend/app.py` to remain a compatibility entrypoint importing `backend.app.main:app`.
- Modify: `backend/requirements.txt` to add pytest dependencies only if missing.
- Create: `frontend-modern/package.json`.
- Create: `frontend-modern/index.html`.
- Create: `frontend-modern/src/main.tsx`.
- Create: `frontend-modern/src/App.tsx`.
- Create: `frontend-modern/src/api.ts`.
- Create: `frontend-modern/src/styles.css`.

---

### Task 1: Rebrand Existing Application To ObsyGPT

**Files:**
- Modify: `README.md`
- Modify: `backend/app.py`
- Modify: `backend/.env`
- Modify: `frontend/app.py`
- Modify: `frontend/.env`
- Modify: `frontend/templates/home.html`
- Modify: `frontend/templates/register.html`
- Modify: `frontend/templates/chat.html`
- Modify: `frontend/static/chat.js`
- Modify: `frontend/static/login.js`
- Modify: `frontend/static/register.js`
- Modify: `frontend/static/styles.css`
- Modify: `database/schema.sql`
- Modify: `exercises/01-openrouter/README.md`
- Modify: `exercises/01-openrouter/app.py`
- Modify: `exercises/02-postgresql-multiuser/README.md`

**Interfaces:**
- Consumes: current Flask/FastAPI app and SQL schema.
- Produces: all visible product naming changed to ObsyGPT while existing app behavior remains intact.

- [ ] **Step 1: Search product references**

Run a search for stale product names.

Expected: matches in README, backend, frontend, database docs, and exercises.

- [ ] **Step 2: Replace direct product strings**

Use targeted edits so these replacements are applied:

```text
Previous title-case product name -> ObsyGPT
Previous lowercase product name -> obsygpt
Previous demo user name -> Obsy
```

Do not change the MIT license author name.

- [ ] **Step 3: Update session cookie name**

In `backend/app.py`, change:

```python
session_cookie="previous_session"
```

to:

```python
session_cookie="obsygpt_session"
```

- [ ] **Step 4: Verify no stale product references remain outside license**

Run a search for stale product names.

Expected: no matches.

- [ ] **Step 5: Smoke-check Python syntax**

Run: `python -m py_compile backend/app.py frontend/app.py exercises/01-openrouter/app.py exercises/02-postgresql-multiuser/1_build_tables.py exercises/02-postgresql-multiuser/2_insert_users.py exercises/02-postgresql-multiuser/3_insert_conversations.py exercises/02-postgresql-multiuser/4_test_database.py`

Expected: command exits with code 0.

---

### Task 2: Add Phase 1 Database Schema

**Files:**
- Modify: `database/schema.sql`

**Interfaces:**
- Consumes: existing `users`, `conversations`, and `messages` tables.
- Produces: concrete tables used by provider, agent, skill, MCP, workflow, trace, attachment, artifact, and source APIs.

- [ ] **Step 1: Add provider and model tables after `users` table definition**

Add this SQL:

```sql
CREATE TABLE public.providers (
    id integer GENERATED BY DEFAULT AS IDENTITY PRIMARY KEY,
    name character varying(100) NOT NULL UNIQUE,
    provider_type character varying(50) NOT NULL,
    base_url text,
    api_key_env character varying(100),
    enabled boolean DEFAULT true NOT NULL,
    created_at timestamp with time zone DEFAULT CURRENT_TIMESTAMP NOT NULL
);

CREATE TABLE public.models (
    id integer GENERATED BY DEFAULT AS IDENTITY PRIMARY KEY,
    provider_id integer NOT NULL REFERENCES public.providers(id) ON DELETE CASCADE,
    model_name character varying(200) NOT NULL,
    display_name character varying(200) NOT NULL,
    supports_text boolean DEFAULT true NOT NULL,
    supports_streaming boolean DEFAULT true NOT NULL,
    supports_vision boolean DEFAULT false NOT NULL,
    supports_audio boolean DEFAULT false NOT NULL,
    supports_tools boolean DEFAULT false NOT NULL,
    supports_json boolean DEFAULT false NOT NULL,
    context_window integer,
    enabled boolean DEFAULT true NOT NULL,
    UNIQUE (provider_id, model_name)
);
```

- [ ] **Step 2: Add agents, skills, and MCP tables**

Add this SQL:

```sql
CREATE TABLE public.agents (
    id integer GENERATED BY DEFAULT AS IDENTITY PRIMARY KEY,
    name character varying(100) NOT NULL UNIQUE,
    description text DEFAULT '' NOT NULL,
    system_prompt text NOT NULL,
    provider_id integer REFERENCES public.providers(id) ON DELETE SET NULL,
    model_id integer REFERENCES public.models(id) ON DELETE SET NULL,
    temperature numeric(3,2) DEFAULT 0.70 NOT NULL,
    internet_enabled boolean DEFAULT false NOT NULL,
    multimodal_enabled boolean DEFAULT false NOT NULL,
    enabled boolean DEFAULT true NOT NULL,
    created_at timestamp with time zone DEFAULT CURRENT_TIMESTAMP NOT NULL
);

CREATE TABLE public.skills (
    id integer GENERATED BY DEFAULT AS IDENTITY PRIMARY KEY,
    name character varying(100) NOT NULL UNIQUE,
    description text DEFAULT '' NOT NULL,
    enabled boolean DEFAULT true NOT NULL
);

CREATE TABLE public.agent_skills (
    agent_id integer NOT NULL REFERENCES public.agents(id) ON DELETE CASCADE,
    skill_id integer NOT NULL REFERENCES public.skills(id) ON DELETE CASCADE,
    PRIMARY KEY (agent_id, skill_id)
);

CREATE TABLE public.mcp_servers (
    id integer GENERATED BY DEFAULT AS IDENTITY PRIMARY KEY,
    name character varying(100) NOT NULL UNIQUE,
    description text DEFAULT '' NOT NULL,
    connection_type character varying(20) NOT NULL CHECK (connection_type IN ('command', 'url')),
    command text,
    url text,
    enabled boolean DEFAULT false NOT NULL,
    created_at timestamp with time zone DEFAULT CURRENT_TIMESTAMP NOT NULL
);

CREATE TABLE public.agent_mcps (
    agent_id integer NOT NULL REFERENCES public.agents(id) ON DELETE CASCADE,
    mcp_server_id integer NOT NULL REFERENCES public.mcp_servers(id) ON DELETE CASCADE,
    PRIMARY KEY (agent_id, mcp_server_id)
);
```

- [ ] **Step 3: Add workflow and trace tables**

Add this SQL:

```sql
CREATE TABLE public.workflows (
    id integer GENERATED BY DEFAULT AS IDENTITY PRIMARY KEY,
    name character varying(100) NOT NULL UNIQUE,
    workflow_type character varying(30) NOT NULL CHECK (workflow_type IN ('single_agent', 'sequential', 'supervisor', 'reviewer', 'parallel', 'debate')),
    enabled boolean DEFAULT true NOT NULL,
    created_at timestamp with time zone DEFAULT CURRENT_TIMESTAMP NOT NULL
);

CREATE TABLE public.workflow_steps (
    id integer GENERATED BY DEFAULT AS IDENTITY PRIMARY KEY,
    workflow_id integer NOT NULL REFERENCES public.workflows(id) ON DELETE CASCADE,
    agent_id integer REFERENCES public.agents(id) ON DELETE SET NULL,
    step_order integer NOT NULL,
    step_name character varying(100) NOT NULL,
    UNIQUE (workflow_id, step_order)
);

CREATE TABLE public.agent_runs (
    id integer GENERATED BY DEFAULT AS IDENTITY PRIMARY KEY,
    user_id integer NOT NULL REFERENCES public.users(id) ON DELETE CASCADE,
    conversation_id integer NOT NULL REFERENCES public.conversations(id) ON DELETE CASCADE,
    message_id integer REFERENCES public.messages(id) ON DELETE SET NULL,
    agent_id integer REFERENCES public.agents(id) ON DELETE SET NULL,
    workflow_id integer REFERENCES public.workflows(id) ON DELETE SET NULL,
    status character varying(20) NOT NULL CHECK (status IN ('running', 'completed', 'failed')),
    final_response text,
    created_at timestamp with time zone DEFAULT CURRENT_TIMESTAMP NOT NULL,
    completed_at timestamp with time zone
);

CREATE TABLE public.agent_events (
    id integer GENERATED BY DEFAULT AS IDENTITY PRIMARY KEY,
    agent_run_id integer NOT NULL REFERENCES public.agent_runs(id) ON DELETE CASCADE,
    event_type character varying(50) NOT NULL,
    title character varying(200) NOT NULL,
    content text DEFAULT '' NOT NULL,
    created_at timestamp with time zone DEFAULT CURRENT_TIMESTAMP NOT NULL
);
```

- [ ] **Step 4: Add tool, MCP call, attachment, artifact, source, and settings tables**

Add this SQL:

```sql
CREATE TABLE public.tool_calls (
    id integer GENERATED BY DEFAULT AS IDENTITY PRIMARY KEY,
    agent_run_id integer NOT NULL REFERENCES public.agent_runs(id) ON DELETE CASCADE,
    skill_name character varying(100) NOT NULL,
    input_summary text DEFAULT '' NOT NULL,
    output_summary text DEFAULT '' NOT NULL,
    status character varying(20) NOT NULL CHECK (status IN ('running', 'completed', 'failed')),
    created_at timestamp with time zone DEFAULT CURRENT_TIMESTAMP NOT NULL
);

CREATE TABLE public.mcp_calls (
    id integer GENERATED BY DEFAULT AS IDENTITY PRIMARY KEY,
    agent_run_id integer NOT NULL REFERENCES public.agent_runs(id) ON DELETE CASCADE,
    mcp_server_id integer REFERENCES public.mcp_servers(id) ON DELETE SET NULL,
    tool_name character varying(100) NOT NULL,
    input_summary text DEFAULT '' NOT NULL,
    output_summary text DEFAULT '' NOT NULL,
    status character varying(20) NOT NULL CHECK (status IN ('running', 'completed', 'failed')),
    created_at timestamp with time zone DEFAULT CURRENT_TIMESTAMP NOT NULL
);

CREATE TABLE public.attachments (
    id integer GENERATED BY DEFAULT AS IDENTITY PRIMARY KEY,
    user_id integer NOT NULL REFERENCES public.users(id) ON DELETE CASCADE,
    message_id integer REFERENCES public.messages(id) ON DELETE CASCADE,
    file_name text NOT NULL,
    mime_type character varying(150) NOT NULL,
    storage_path text NOT NULL,
    size_bytes integer NOT NULL,
    created_at timestamp with time zone DEFAULT CURRENT_TIMESTAMP NOT NULL
);

CREATE TABLE public.artifacts (
    id integer GENERATED BY DEFAULT AS IDENTITY PRIMARY KEY,
    agent_run_id integer REFERENCES public.agent_runs(id) ON DELETE CASCADE,
    artifact_type character varying(50) NOT NULL,
    title character varying(200) NOT NULL,
    content text NOT NULL,
    created_at timestamp with time zone DEFAULT CURRENT_TIMESTAMP NOT NULL
);

CREATE TABLE public.sources (
    id integer GENERATED BY DEFAULT AS IDENTITY PRIMARY KEY,
    agent_run_id integer REFERENCES public.agent_runs(id) ON DELETE CASCADE,
    url text NOT NULL,
    title text DEFAULT '' NOT NULL,
    snippet text DEFAULT '' NOT NULL,
    created_at timestamp with time zone DEFAULT CURRENT_TIMESTAMP NOT NULL
);

CREATE TABLE public.settings (
    key character varying(100) PRIMARY KEY,
    value text NOT NULL,
    updated_at timestamp with time zone DEFAULT CURRENT_TIMESTAMP NOT NULL
);
```

- [ ] **Step 5: Seed Phase 1 defaults**

Add this SQL near the end of `database/schema.sql`:

```sql
INSERT INTO public.providers (name, provider_type, base_url, api_key_env, enabled)
VALUES ('OpenRouter', 'openrouter', 'https://openrouter.ai/api/v1', 'OPENROUTER_API_KEY', true)
ON CONFLICT (name) DO NOTHING;

INSERT INTO public.models (provider_id, model_name, display_name, supports_text, supports_streaming)
SELECT id, 'nvidia/nemotron-3-super-120b-a12b:free', 'NVIDIA Nemotron 3 Super 120B', true, true
FROM public.providers
WHERE name = 'OpenRouter'
ON CONFLICT (provider_id, model_name) DO NOTHING;

INSERT INTO public.skills (name, description, enabled)
VALUES
    ('web_search', 'Search the web and return ranked results.', true),
    ('read_url', 'Read and extract clean content from a URL.', true),
    ('extract_pdf', 'Extract text and metadata from uploaded PDFs.', true),
    ('summarize_document', 'Summarize extracted document content.', true),
    ('analyze_image', 'Analyze an uploaded image with a vision-capable model.', true),
    ('critic_review', 'Review an intermediate answer for quality and accuracy.', true),
    ('final_answer', 'Synthesize a final user-facing answer.', true)
ON CONFLICT (name) DO NOTHING;

INSERT INTO public.agents (name, description, system_prompt, provider_id, model_id, internet_enabled, multimodal_enabled, enabled)
SELECT
    'Default Assistant',
    'Default ObsyGPT text assistant.',
    'You are ObsyGPT, a helpful multi-agent AI assistant. Answer clearly and accurately.',
    p.id,
    m.id,
    false,
    false,
    true
FROM public.providers p
JOIN public.models m ON m.provider_id = p.id
WHERE p.name = 'OpenRouter'
  AND m.model_name = 'nvidia/nemotron-3-super-120b-a12b:free'
ON CONFLICT (name) DO NOTHING;

INSERT INTO public.workflows (name, workflow_type, enabled)
VALUES ('Default Single Agent', 'single_agent', true)
ON CONFLICT (name) DO NOTHING;
```

- [ ] **Step 6: Validate schema with PostgreSQL**

Run: `psql -h localhost -U postgres -d obsygpt -f database/schema.sql`

Expected: schema applies without SQL errors on a clean database.

---

### Task 3: Create Backend Module Skeleton And Compatibility Entrypoint

**Files:**
- Create: `backend/app/__init__.py`
- Create: `backend/app/main.py`
- Create: `backend/app/config.py`
- Create: `backend/app/db.py`
- Modify: `backend/app.py`

**Interfaces:**
- Consumes: existing `DATABASE_URL`, `OPENROUTER_API_KEY`, `FRONTEND_URL`, `SESSION_SECRET`, `COOKIE_SECURE`, and `COOKIE_SAMESITE` env vars.
- Produces: importable FastAPI app at `backend.app.main:app` and compatibility app at `backend/app.py`.

- [ ] **Step 1: Create `backend/app/config.py`**

```python
import os
from dataclasses import dataclass

from dotenv import load_dotenv


load_dotenv()


@dataclass(frozen=True)
class Settings:
    database_url: str
    openrouter_api_key: str
    frontend_url: str
    session_secret: str
    cookie_secure: bool
    cookie_samesite: str


def get_settings() -> Settings:
    database_url = os.getenv("DATABASE_URL")
    openrouter_api_key = os.getenv("OPENROUTER_API_KEY")

    if not database_url:
        raise RuntimeError("DATABASE_URL is not configured.")

    if not openrouter_api_key:
        raise RuntimeError("OPENROUTER_API_KEY is not configured.")

    return Settings(
        database_url=database_url,
        openrouter_api_key=openrouter_api_key,
        frontend_url=os.getenv("FRONTEND_URL", "http://127.0.0.1:5173"),
        session_secret=os.getenv("SESSION_SECRET", "local-development-secret-change-me"),
        cookie_secure=os.getenv("COOKIE_SECURE", "false").lower() == "true",
        cookie_samesite=os.getenv("COOKIE_SAMESITE", "lax"),
    )
```

- [ ] **Step 2: Create `backend/app/db.py`**

```python
from collections.abc import Generator

import psycopg
from psycopg import Connection

from .config import get_settings


def connect() -> Connection:
    return psycopg.connect(get_settings().database_url)


def cursor() -> Generator[psycopg.Cursor, None, None]:
    with connect() as connection:
        with connection.cursor() as db_cursor:
            yield db_cursor
```

- [ ] **Step 3: Create `backend/app/main.py`**

```python
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from starlette.middleware.sessions import SessionMiddleware

from .config import get_settings


settings = get_settings()

app = FastAPI(title="ObsyGPT API")

app.add_middleware(
    SessionMiddleware,
    secret_key=settings.session_secret,
    session_cookie="obsygpt_session",
    same_site=settings.cookie_samesite,
    https_only=settings.cookie_secure,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=[settings.frontend_url],
    allow_credentials=True,
    allow_methods=["GET", "POST", "PUT", "PATCH", "DELETE"],
    allow_headers=["Content-Type"],
)


@app.get("/")
def root():
    return {"message": "ObsyGPT API is running"}


@app.get("/api/health")
def health():
    return {"status": "healthy"}
```

- [ ] **Step 4: Create `backend/app/__init__.py`**

```python
from .main import app

__all__ = ["app"]
```

- [ ] **Step 5: Replace `backend/app.py` with compatibility import**

```python
from app.main import app
```

- [ ] **Step 6: Verify import works**

Run: `python -c "from app.main import app; print(app.title)"` from `backend`.

Expected: `ObsyGPT API`.

---

### Task 4: Add Provider Router With OpenRouter Adapter

**Files:**
- Create: `backend/app/providers/__init__.py`
- Create: `backend/app/providers/base.py`
- Create: `backend/app/providers/openrouter.py`
- Create: `backend/app/providers/registry.py`

**Interfaces:**
- Consumes: `Settings.openrouter_api_key` and OpenAI SDK.
- Produces: `ProviderRegistry.stream_chat(provider_type: str, request: ChatRequest) -> Iterator[str]`.

- [ ] **Step 1: Create `backend/app/providers/base.py`**

```python
from collections.abc import Iterator
from dataclasses import dataclass


@dataclass(frozen=True)
class ChatMessage:
    role: str
    content: str


@dataclass(frozen=True)
class ChatRequest:
    model: str
    messages: list[ChatMessage]
    temperature: float = 0.7


class AIProvider:
    provider_type: str

    def stream_chat(self, request: ChatRequest) -> Iterator[str]:
        raise NotImplementedError
```

- [ ] **Step 2: Create `backend/app/providers/openrouter.py`**

```python
from collections.abc import Iterator

from openai import OpenAI

from .base import AIProvider, ChatRequest


class OpenRouterProvider(AIProvider):
    provider_type = "openrouter"

    def __init__(self, api_key: str):
        self.client = OpenAI(
            base_url="https://openrouter.ai/api/v1",
            api_key=api_key,
        )

    def stream_chat(self, request: ChatRequest) -> Iterator[str]:
        stream = self.client.chat.completions.create(
            model=request.model,
            messages=[{"role": message.role, "content": message.content} for message in request.messages],
            temperature=float(request.temperature),
            stream=True,
            extra_body={"provider": {"sort": "latency"}},
        )

        for chunk in stream:
            token = chunk.choices[0].delta.content
            if token:
                yield token
```

- [ ] **Step 3: Create `backend/app/providers/registry.py`**

```python
from collections.abc import Iterator

from ..config import get_settings
from .base import AIProvider, ChatRequest
from .openrouter import OpenRouterProvider


class ProviderRegistry:
    def __init__(self):
        settings = get_settings()
        self.providers: dict[str, AIProvider] = {
            "openrouter": OpenRouterProvider(settings.openrouter_api_key),
        }

    def stream_chat(self, provider_type: str, request: ChatRequest) -> Iterator[str]:
        provider = self.providers.get(provider_type)
        if not provider:
            raise ValueError(f"Provider is not configured: {provider_type}")
        return provider.stream_chat(request)
```

- [ ] **Step 4: Create `backend/app/providers/__init__.py`**

```python
from .base import AIProvider, ChatMessage, ChatRequest
from .registry import ProviderRegistry

__all__ = ["AIProvider", "ChatMessage", "ChatRequest", "ProviderRegistry"]
```

- [ ] **Step 5: Verify provider module imports**

Run: `python -c "from app.providers import ChatMessage, ChatRequest, ProviderRegistry; print(ChatMessage('user', 'hi'))"` from `backend`.

Expected: `ChatMessage(role='user', content='hi')`.

---

### Task 5: Add Agent Runtime And Trace Store

**Files:**
- Create: `backend/app/agents/__init__.py`
- Create: `backend/app/agents/runtime.py`
- Create: `backend/app/traces/__init__.py`
- Create: `backend/app/traces/store.py`

**Interfaces:**
- Consumes: `ProviderRegistry`, `ChatMessage`, `ChatRequest`, and PostgreSQL tables `agent_runs`, `agent_events`.
- Produces: `AgentRuntime.stream_default_agent(...) -> Iterator[str]` and persisted trace events.

- [ ] **Step 1: Create `backend/app/traces/store.py`**

```python
from datetime import datetime

from ..db import connect


class TraceStore:
    def create_run(self, user_id: int, conversation_id: int, message_id: int | None, agent_id: int | None) -> int:
        with connect() as connection:
            with connection.cursor() as cursor:
                cursor.execute(
                    """
                    INSERT INTO agent_runs (user_id, conversation_id, message_id, agent_id, status)
                    VALUES (%s, %s, %s, %s, 'running')
                    RETURNING id;
                    """,
                    (user_id, conversation_id, message_id, agent_id),
                )
                return cursor.fetchone()[0]

    def add_event(self, agent_run_id: int, event_type: str, title: str, content: str = "") -> None:
        with connect() as connection:
            with connection.cursor() as cursor:
                cursor.execute(
                    """
                    INSERT INTO agent_events (agent_run_id, event_type, title, content)
                    VALUES (%s, %s, %s, %s);
                    """,
                    (agent_run_id, event_type, title, content),
                )

    def complete_run(self, agent_run_id: int, final_response: str) -> None:
        with connect() as connection:
            with connection.cursor() as cursor:
                cursor.execute(
                    """
                    UPDATE agent_runs
                    SET status = 'completed', final_response = %s, completed_at = %s
                    WHERE id = %s;
                    """,
                    (final_response, datetime.utcnow(), agent_run_id),
                )

    def fail_run(self, agent_run_id: int, error_message: str) -> None:
        with connect() as connection:
            with connection.cursor() as cursor:
                cursor.execute(
                    """
                    UPDATE agent_runs
                    SET status = 'failed', final_response = %s, completed_at = %s
                    WHERE id = %s;
                    """,
                    (error_message, datetime.utcnow(), agent_run_id),
                )
```

- [ ] **Step 2: Create `backend/app/agents/runtime.py`**

```python
from collections.abc import Iterator

from ..providers import ChatMessage, ChatRequest, ProviderRegistry
from ..traces.store import TraceStore


DEFAULT_MODEL = "nvidia/nemotron-3-super-120b-a12b:free"


class AgentRuntime:
    def __init__(self, provider_registry: ProviderRegistry | None = None, trace_store: TraceStore | None = None):
        self.provider_registry = provider_registry or ProviderRegistry()
        self.trace_store = trace_store or TraceStore()

    def stream_default_agent(
        self,
        agent_run_id: int,
        messages: list[ChatMessage],
    ) -> Iterator[str]:
        self.trace_store.add_event(agent_run_id, "agent_started", "Default Assistant started")

        request = ChatRequest(
            model=DEFAULT_MODEL,
            messages=messages[-20:],
            temperature=0.7,
        )

        self.trace_store.add_event(agent_run_id, "provider_started", "OpenRouter streaming started", DEFAULT_MODEL)

        complete_response = ""
        for token in self.provider_registry.stream_chat("openrouter", request):
            complete_response += token
            yield token

        self.trace_store.add_event(agent_run_id, "agent_completed", "Default Assistant completed")
        self.trace_store.complete_run(agent_run_id, complete_response)
```

- [ ] **Step 3: Create package exports**

Create `backend/app/agents/__init__.py`:

```python
from .runtime import AgentRuntime

__all__ = ["AgentRuntime"]
```

Create `backend/app/traces/__init__.py`:

```python
from .store import TraceStore

__all__ = ["TraceStore"]
```

- [ ] **Step 4: Verify runtime imports**

Run: `python -c "from app.agents import AgentRuntime; print(AgentRuntime.__name__)"` from `backend`.

Expected: `AgentRuntime`.

---

### Task 6: Restore Auth And Chat Routes On Modular Backend

**Files:**
- Create: `backend/app/auth/__init__.py`
- Create: `backend/app/auth/routes.py`
- Create: `backend/app/chat/__init__.py`
- Create: `backend/app/chat/routes.py`
- Modify: `backend/app/main.py`

**Interfaces:**
- Consumes: existing auth behavior and `AgentRuntime`.
- Produces: `/api/register`, `/api/login`, `/api/session`, `/api/logout`, `/api/conversations`, `/api/conversations/{id}/messages`.

- [ ] **Step 1: Move auth logic into `backend/app/auth/routes.py`**

Copy the existing register, login, session, logout, password hashing, and user lookup logic from the old backend into this router. The router must be declared as:

```python
from fastapi import APIRouter

router = APIRouter(prefix="/api", tags=["auth"])
```

The exported object must be named `router`.

- [ ] **Step 2: Move conversation helpers into `backend/app/chat/routes.py`**

Copy existing helpers for conversations and messages. Replace direct OpenRouter calls with:

```python
agent_run_id = trace_store.create_run(user_id, conversation_id, user_message_id, None)
runtime = AgentRuntime(trace_store=trace_store)
for token in runtime.stream_default_agent(agent_run_id, openrouter_messages):
    complete_response += token
    yield token
```

After streaming completes, save the assistant message with the same `save_message` helper.

- [ ] **Step 3: Include routers in `backend/app/main.py`**

Add:

```python
from .auth.routes import router as auth_router
from .chat.routes import router as chat_router

app.include_router(auth_router)
app.include_router(chat_router)
```

- [ ] **Step 4: Verify routes import**

Run: `python -c "from app.main import app; print(len(app.routes))"` from `backend`.

Expected: route count is greater than 6.

---

### Task 7: Add Metadata APIs For Providers, Agents, Skills, MCPs, And Traces

**Files:**
- Create: `backend/app/admin/__init__.py`
- Create: `backend/app/admin/routes.py`
- Modify: `backend/app/main.py`

**Interfaces:**
- Consumes: schema tables from Task 2.
- Produces: read-only Phase 1 metadata endpoints for the modern frontend.

- [ ] **Step 1: Create `backend/app/admin/routes.py`**

```python
from fastapi import APIRouter, Request

from ..auth.routes import require_user
from ..db import connect


router = APIRouter(prefix="/api/admin", tags=["admin"])


def fetch_all(query: str, params: tuple = ()):
    with connect() as connection:
        with connection.cursor() as cursor:
            cursor.execute(query, params)
            columns = [column.name for column in cursor.description]
            return [dict(zip(columns, row)) for row in cursor.fetchall()]


@router.get("/providers")
def list_providers(request: Request):
    require_user(request)
    return {"providers": fetch_all("SELECT id, name, provider_type, base_url, api_key_env, enabled FROM providers ORDER BY name;")}


@router.get("/models")
def list_models(request: Request):
    require_user(request)
    return {"models": fetch_all("SELECT id, provider_id, model_name, display_name, supports_text, supports_streaming, supports_vision, supports_audio, supports_tools, supports_json, context_window, enabled FROM models ORDER BY display_name;")}


@router.get("/agents")
def list_agents(request: Request):
    require_user(request)
    return {"agents": fetch_all("SELECT id, name, description, provider_id, model_id, temperature, internet_enabled, multimodal_enabled, enabled FROM agents ORDER BY name;")}


@router.get("/skills")
def list_skills(request: Request):
    require_user(request)
    return {"skills": fetch_all("SELECT id, name, description, enabled FROM skills ORDER BY name;")}


@router.get("/mcp-servers")
def list_mcp_servers(request: Request):
    require_user(request)
    return {"mcp_servers": fetch_all("SELECT id, name, description, connection_type, command, url, enabled FROM mcp_servers ORDER BY name;")}


@router.get("/agent-runs/{conversation_id}")
def list_agent_runs(conversation_id: int, request: Request):
    user_id = require_user(request)
    return {"agent_runs": fetch_all("SELECT id, conversation_id, agent_id, workflow_id, status, final_response, created_at, completed_at FROM agent_runs WHERE user_id = %s AND conversation_id = %s ORDER BY created_at DESC;", (user_id, conversation_id))}


@router.get("/agent-events/{agent_run_id}")
def list_agent_events(agent_run_id: int, request: Request):
    user_id = require_user(request)
    query = """
        SELECT e.id, e.agent_run_id, e.event_type, e.title, e.content, e.created_at
        FROM agent_events e
        JOIN agent_runs r ON r.id = e.agent_run_id
        WHERE r.user_id = %s AND e.agent_run_id = %s
        ORDER BY e.created_at, e.id;
    """
    return {"agent_events": fetch_all(query, (user_id, agent_run_id))}
```

- [ ] **Step 2: Create `backend/app/admin/__init__.py`**

```python
from .routes import router

__all__ = ["router"]
```

- [ ] **Step 3: Include admin router in `backend/app/main.py`**

Add:

```python
from .admin.routes import router as admin_router

app.include_router(admin_router)
```

- [ ] **Step 4: Verify admin routes exist**

Run: `python -c "from app.main import app; print([route.path for route in app.routes if '/api/admin' in route.path])"` from `backend`.

Expected: paths for providers, models, agents, skills, mcp-servers, agent-runs, and agent-events.

---

### Task 8: Create Modern Frontend Shell

**Files:**
- Create: `frontend-modern/package.json`
- Create: `frontend-modern/index.html`
- Create: `frontend-modern/src/main.tsx`
- Create: `frontend-modern/src/App.tsx`
- Create: `frontend-modern/src/api.ts`
- Create: `frontend-modern/src/styles.css`

**Interfaces:**
- Consumes: FastAPI endpoints from Tasks 6 and 7.
- Produces: modern ObsyGPT UI with login, chat workspace, provider panel, agent panel, skills panel, MCP panel, and trace panel.

- [ ] **Step 1: Create `frontend-modern/package.json`**

```json
{
  "scripts": {
    "dev": "vite --host 0.0.0.0 --port 5173",
    "build": "tsc && vite build",
    "preview": "vite preview --host 0.0.0.0 --port 4173"
  },
  "dependencies": {
    "@vitejs/plugin-react": "latest",
    "vite": "latest",
    "typescript": "latest",
    "react": "latest",
    "react-dom": "latest"
  },
  "devDependencies": {}
}
```

- [ ] **Step 2: Create `frontend-modern/index.html`**

```html
<!doctype html>
<html lang="en">
  <head>
    <meta charset="UTF-8" />
    <meta name="viewport" content="width=device-width, initial-scale=1.0" />
    <title>ObsyGPT</title>
  </head>
  <body>
    <div id="root"></div>
    <script type="module" src="/src/main.tsx"></script>
  </body>
</html>
```

- [ ] **Step 3: Create `frontend-modern/src/api.ts`**

```ts
const backendUrl = import.meta.env.VITE_BACKEND_URL ?? "http://127.0.0.1:8000";

export async function apiRequest<T>(path: string, options: RequestInit = {}): Promise<T> {
  const response = await fetch(`${backendUrl}${path}`, {
    ...options,
    credentials: "include",
    headers: {
      "Content-Type": "application/json",
      ...(options.headers ?? {})
    }
  });

  const data = await response.json().catch(() => ({}));

  if (!response.ok) {
    throw new Error(data.detail ?? "Request failed");
  }

  return data as T;
}

export async function streamMessage(conversationId: number, message: string, onToken: (token: string) => void): Promise<void> {
  const response = await fetch(`${backendUrl}/api/conversations/${conversationId}/messages`, {
    method: "POST",
    credentials: "include",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ message })
  });

  if (!response.ok || !response.body) {
    throw new Error(await response.text());
  }

  const reader = response.body.getReader();
  const decoder = new TextDecoder();

  while (true) {
    const result = await reader.read();
    if (result.done) break;
    onToken(decoder.decode(result.value, { stream: true }));
  }
}
```

- [ ] **Step 4: Create `frontend-modern/src/main.tsx`**

```tsx
import React from "react";
import { createRoot } from "react-dom/client";
import App from "./App";
import "./styles.css";

createRoot(document.getElementById("root")!).render(
  <React.StrictMode>
    <App />
  </React.StrictMode>
);
```

- [ ] **Step 5: Create `frontend-modern/src/App.tsx`**

Create a single-file Phase 1 app with typed state for session, conversations, providers, agents, skills, MCP servers, trace runs, and events. The UI must include these headings exactly: `Chat Workspace`, `Agent Studio`, `Provider Settings`, `Skills Library`, `MCP Manager`, `Trace Viewer`.

- [ ] **Step 6: Create `frontend-modern/src/styles.css`**

Use a dark, dense workspace layout with left navigation, central chat, and right trace/config panels. The CSS must include responsive behavior for screens below 800px by stacking panels vertically.

- [ ] **Step 7: Build frontend**

Run: `npm install; if ($?) { npm run build }` from `frontend-modern`.

Expected: Vite production build completes successfully.

---

### Task 9: Verification Pass

**Files:**
- All changed files.

**Interfaces:**
- Consumes: completed Tasks 1-8.
- Produces: verified Phase 1 baseline.

- [ ] **Step 1: Check git status**

Run: `git status --short`

Expected: only intended ObsyGPT files are modified or created.

- [ ] **Step 2: Check product references**

Run a search for stale product names.

Expected: no matches outside `.git` internals.

- [ ] **Step 3: Compile backend**

Run: `python -m compileall backend`

Expected: compile completes without syntax errors.

- [ ] **Step 4: Build frontend**

Run: `npm run build` from `frontend-modern`.

Expected: production build completes.

- [ ] **Step 5: Start backend smoke test**

Run: `uvicorn app.main:app --host 127.0.0.1 --port 8000` from `backend`.

Expected: server starts and `/api/health` returns `{"status":"healthy"}`.

- [ ] **Step 6: Start frontend smoke test**

Run: `npm run dev` from `frontend-modern`.

Expected: Vite starts on port 5173 and the page title is ObsyGPT.

---

## Self-Review

- Spec coverage: This plan covers the rebrand, modular backend, provider router, visible agent traces, modern frontend shell, schema foundations for providers, models, agents, skills, MCPs, workflows, internet sources, attachments, and artifacts. Full multi-provider adapters, real MCP execution, full skills runtime, internet search implementation, and multimodal extraction are intentionally deferred to later phase plans.
- Placeholder scan: The plan contains no open TBD markers. Deferred items are explicitly scoped as later phases and Phase 1 creates concrete schema/API surfaces for them.
- Type consistency: `ChatMessage`, `ChatRequest`, `ProviderRegistry`, `TraceStore`, and `AgentRuntime` names are defined before use.
