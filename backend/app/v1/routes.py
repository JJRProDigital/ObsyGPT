"""OpenAI-compatible endpoints: GET /v1/models and POST /v1/chat/completions.

Stateless per call: no conversation or messages are persisted, but every call
creates a traceable agent_run. Tool access is filtered to safe-only (minus
tools the user blocked in Ajustes > Seguridad > Permisos) so no approval flow
can ever trigger from an external client.
"""

import logging
import json
import secrets
import time
from collections import defaultdict
from collections.abc import Callable, Iterator
from dataclasses import dataclass
from dataclasses import replace as dataclass_replace

from fastapi import APIRouter, Request
from fastapi.responses import JSONResponse, StreamingResponse
from pydantic import BaseModel, ValidationError
from starlette.concurrency import run_in_threadpool

from ..agent.runtime import AgentLoop
from ..agent.settings import load_guardrail_config
from ..chat import specs as chat_specs
from ..db import connect
from ..memory.context import build_memory_context, build_user_instructions_block
from ..memory.semantic.retrieval import build_semantic_context_block
from ..providers import ChatMessage
from ..traces.store import TraceStore
from ..workflows import AgentSpec, WorkflowRuntime
from ..workspace.routes import get_user_preferences
from .keys import KeyAuthError, authenticate_key


logger = logging.getLogger("obsygpt.v1.routes")

router = APIRouter(prefix="/v1", tags=["v1"])

VALID_ROLES = {"system", "user", "assistant"}

NON_AGENTIC_NOTE = (
    "SYSTEM NOTE: This conversation runs WITHOUT tool access. You cannot browse, fetch URLs, read files or run commands, "
    "and no tool will be executed for you. Never emit <<<TOOL blocks and never pretend a tool ran or imagine its output. "
    "If the user needs tools, tell them to pick an agent with agentic mode enabled in the agent selector."
)

RATE_LIMIT_MAX_ATTEMPTS = 30
RATE_LIMIT_WINDOW_SECONDS = 60
MAX_TRACKED_KEYS = 10_000


class RateLimitExceededError(RuntimeError):
    """Raised when a key exceeds the /v1 chat rate limit."""


class KeyRateLimiter:
    """Sliding-window per-key limiter (AuthRateLimiter pattern, action v1_chat)."""

    def __init__(self, max_attempts: int, window_seconds: int, now: Callable[[], float] | None = None):
        self.max_attempts = max_attempts
        self.window_seconds = window_seconds
        self.now = now or time.time
        self.attempts: dict[str, list[float]] = defaultdict(list)

    def check(self, key: str) -> None:
        current_time = self.now()
        window_start = current_time - self.window_seconds
        recent_attempts = [attempt for attempt in self.attempts[key] if attempt > window_start]
        if len(recent_attempts) >= self.max_attempts:
            self.attempts[key] = recent_attempts
            raise RateLimitExceededError("Rate limit reached for this API key. Please try again later.")
        recent_attempts.append(current_time)
        self.attempts[key] = recent_attempts
        self._cleanup(current_time, window_start)

    def _cleanup(self, current_time: float, window_start: float) -> None:
        """Drops expired keys so the tracker cannot grow without bound."""
        if len(self.attempts) < MAX_TRACKED_KEYS and (hash(current_time) & 63) != 0:
            return
        expired = [key for key, times in self.attempts.items() if not any(t > window_start for t in times)]
        for key in expired:
            del self.attempts[key]


chat_rate_limiter = KeyRateLimiter(max_attempts=RATE_LIMIT_MAX_ATTEMPTS, window_seconds=RATE_LIMIT_WINDOW_SECONDS)


class ChatCompletionMessage(BaseModel):
    role: str
    content: str = ""


class ChatCompletionRequest(BaseModel):
    model: str
    messages: list[ChatCompletionMessage]
    temperature: float | None = None
    stream: bool = False


def openai_error(status_code: int, message: str, error_type: str, code: str) -> JSONResponse:
    return JSONResponse(status_code=status_code, content={"error": {"message": message, "type": error_type, "code": code}})


def _authenticate(request: Request) -> int:
    """Resolves the caller user_id from the bearer key; raises KeyAuthError."""
    return authenticate_key(request.headers.get("authorization"))


def list_enabled_agents() -> list[tuple[int, str]]:
    with connect() as connection:
        with connection.cursor() as cursor:
            cursor.execute("SELECT id, name FROM agents WHERE enabled = true ORDER BY id;")
            return [(int(row[0]), row[1]) for row in cursor.fetchall()]


def _find_enabled_agent_id(model: str) -> int | None:
    name = model.strip()
    with connect() as connection:
        with connection.cursor() as cursor:
            cursor.execute("SELECT id FROM agents WHERE enabled = true AND lower(name) = lower(%s);", (name,))
            row = cursor.fetchone()
            if row is None and name.lower().startswith("agent-"):
                suffix = name[len("agent-"):]
                if suffix.isdigit():
                    cursor.execute("SELECT id FROM agents WHERE enabled = true AND id = %s;", (int(suffix),))
                    row = cursor.fetchone()
    return int(row[0]) if row else None


def resolve_agent(model: str) -> AgentSpec | None:
    """Resolves an enabled agent by name (case-insensitive) or `agent-{id}`."""
    agent_id = _find_enabled_agent_id(model)
    if agent_id is None:
        return None
    return chat_specs.get_workflow_spec(None, agent_id).agents[0]


def build_v1_messages(user_id: int, agent: AgentSpec, client_messages: list[ChatCompletionMessage]) -> list[ChatMessage]:
    """Agent system prompt first, then client messages in order, then context blocks."""
    messages: list[ChatMessage] = []
    if agent.system_prompt:
        messages.append(ChatMessage(role="system", content=agent.system_prompt))
    for item in client_messages:
        messages.append(ChatMessage(role=item.role, content=item.content))

    last_user_content = next(
        (item.content for item in reversed(client_messages) if item.role == "user" and item.content),
        "",
    )
    instructions_block = build_user_instructions_block(user_id)
    if instructions_block:
        messages.append(ChatMessage(role="user", content=instructions_block))
    memory_context = build_memory_context(user_id)
    if memory_context:
        messages.append(ChatMessage(role="user", content=memory_context))
    semantic_context = build_semantic_context_block(user_id, last_user_content)
    if semantic_context:
        messages.append(ChatMessage(role="user", content=semantic_context))
    if not agent.agentic_mode:
        messages.append(ChatMessage(role="user", content=NON_AGENTIC_NOTE))
    return messages


def _agentic_pieces(user_id: int, agent_run_id: int, agent: AgentSpec, temperature: float, messages: list[ChatMessage], trace_store: TraceStore) -> Iterator[str]:
    registry = chat_specs.build_agent_tool_registry(user_id=user_id, agent_id=agent.id)
    preferences = get_user_preferences(user_id)
    policies = preferences.get("tool_policies") or {}
    v1_access = preferences.get("tool_v1_access") or {}

    def _v1_enabled(name: str) -> bool:
        # Explicit per-tool check ("Permitir por V1") wins; otherwise "ask" stays off
        # on /v1 (no human to approve) and everything else defaults to enabled.
        if name in v1_access:
            return bool(v1_access[name])
        return policies.get(name) != "ask"

    blocked = {name for name, policy in policies.items() if policy == "block"}
    allowed = {spec.name for spec in registry.list_specs() if spec.permission == "safe"} - blocked
    allowed = {name for name in allowed if _v1_enabled(name)}
    registry.filter_to(allowed)
    tool_specs = [
        spec
        for spec in chat_specs.get_agent_tool_specs(agent.id, user_id=user_id)
        if spec.permission == "safe" and spec.name in allowed
    ]
    loop = AgentLoop(trace_store=trace_store, execute_tool=lambda name, args: registry.run(name, args))
    yield from loop.run(
        agent_run_id=agent_run_id,
        system_prompt=agent.system_prompt,
        provider_type=agent.provider_type,
        provider_base_url=agent.provider_base_url,
        provider_api_key_env=agent.provider_api_key_env,
        provider_api_key=agent.provider_api_key,
        model=agent.model,
        temperature=temperature,
        tool_specs=tool_specs,
        messages=messages,
        guardrail_config=load_guardrail_config(),
        fallbacks=agent.fallbacks,
    )


def _run_agentic(user_id: int, agent_run_id: int, agent: AgentSpec, temperature: float, messages: list[ChatMessage], trace_store: TraceStore) -> str:
    output = "".join(_agentic_pieces(user_id, agent_run_id, agent, temperature, messages, trace_store))
    trace_store.complete_run(agent_run_id, output)
    return output


def _non_agentic_pieces(agent_run_id: int, agent: AgentSpec, temperature: float | None, messages: list[ChatMessage], trace_store: TraceStore) -> Iterator[str]:
    workflow = chat_specs.get_workflow_spec(None, agent.id)
    if temperature is not None and workflow.agents:
        workflow = dataclass_replace(
            workflow,
            agents=[dataclass_replace(workflow.agents[0], temperature=float(temperature)), *workflow.agents[1:]],
        )
    runtime = WorkflowRuntime(trace_store=trace_store)
    yield from runtime.stream_workflow(agent_run_id, workflow, messages)


def _run_non_agentic(agent_run_id: int, agent: AgentSpec, temperature: float | None, messages: list[ChatMessage], trace_store: TraceStore) -> str:
    return "".join(_non_agentic_pieces(agent_run_id, agent, temperature, messages, trace_store))


@router.get("/models")
def list_models(request: Request):
    try:
        _authenticate(request)
    except KeyAuthError as error:
        return openai_error(401, str(error), "invalid_request_error", "invalid_api_key")
    return JSONResponse(
        content={
            "object": "list",
            "data": [
                {"id": f"agent-{agent_id}", "object": "model", "owned_by": "obsygpt"}
                for agent_id, _name in list_enabled_agents()
            ],
        }
    )


@dataclass
class ChatExecutionContext:
    """Everything the execution stage needs once pre-flight checks pass."""

    user_id: int
    data: ChatCompletionRequest
    agent: AgentSpec
    temperature: float
    messages: list[ChatMessage]
    trace_store: TraceStore
    agent_run_id: int


def _prepare_chat_completion(request: Request, raw_body: bytes) -> tuple[ChatExecutionContext | None, JSONResponse | None]:
    """Shared pre-execution flow: auth -> parse -> validate -> rate limit -> resolve -> build messages -> create run.

    Sync on purpose: the caller runs it via run_in_threadpool because the auth
    DB writes, agent resolution, context builders and create_run are blocking
    psycopg calls that must stay off the event loop.
    """
    try:
        user_id = _authenticate(request)
    except KeyAuthError as error:
        return None, openai_error(401, str(error), "invalid_request_error", "invalid_api_key")

    try:
        payload = json.loads(raw_body)
    except (json.JSONDecodeError, UnicodeDecodeError):
        return None, openai_error(400, "Invalid JSON body", "invalid_request_error", "invalid_request_error")
    if not isinstance(payload, dict):
        return None, openai_error(400, "Body must be a JSON object", "invalid_request_error", "invalid_request_error")

    try:
        data = ChatCompletionRequest.model_validate(payload)
    except ValidationError as error:
        return None, openai_error(400, f"Invalid request: {error.errors()[0].get('msg', 'malformed body')}", "invalid_request_error", "invalid_request_error")

    if not data.messages:
        return None, openai_error(400, "Invalid request: 'messages' must contain at least one message.", "invalid_request_error", "invalid_request_error")

    invalid = next((item for item in data.messages if item.role not in VALID_ROLES), None)
    if invalid is not None:
        return None, openai_error(
            400,
            f"Invalid message role: {invalid.role!r}. Allowed roles: system, user, assistant.",
            "invalid_request_error",
            "invalid_request_error",
        )

    try:
        # Keyed per user (v1_chat:{user_id}), not per key: all of a user's keys share one budget — stricter than per-key, intentional.
        chat_rate_limiter.check(f"v1_chat:{user_id}")
    except RateLimitExceededError as error:
        return None, openai_error(429, str(error), "rate_limit_error", "rate_limit_exceeded")

    agent = resolve_agent(data.model)
    if agent is None or agent.id is None:
        return None, openai_error(404, f"The model '{data.model}' does not exist or is disabled.", "invalid_request_error", "model_not_found")

    temperature = data.temperature if data.temperature is not None else agent.temperature
    messages = build_v1_messages(user_id, agent, data.messages)

    trace_store = TraceStore()
    agent_run_id = trace_store.create_run(user_id, None, None, agent.id, None)
    trace_store.add_event(agent_run_id, "v1_request", "OpenAI-compatible API request", f"model={data.model}")
    return ChatExecutionContext(
        user_id=user_id,
        data=data,
        agent=agent,
        temperature=temperature,
        messages=messages,
        trace_store=trace_store,
        agent_run_id=agent_run_id,
    ), None


def _agentic_pieces_traced(context: ChatExecutionContext) -> Iterator[str]:
    """Agentic pieces that finalize their own trace run (AgentLoop does not do it)."""
    parts: list[str] = []
    try:
        for piece in _agentic_pieces(context.user_id, context.agent_run_id, context.agent, context.temperature, context.messages, context.trace_store):
            parts.append(piece)
            yield piece
    except Exception as error:  # trace the failure, then let the streamer close the stream
        try:
            context.trace_store.fail_run(context.agent_run_id, str(error))
        except Exception:  # noqa: BLE001 - tracing must not mask the provider error
            logger.warning("Could not mark v1 run %s as failed", context.agent_run_id)
        raise
    try:
        context.trace_store.complete_run(context.agent_run_id, "".join(parts))
    except Exception:  # noqa: BLE001 - tracing must not break the stream close
        logger.warning("Could not mark v1 run %s as completed", context.agent_run_id)


def _execution_pieces(context: ChatExecutionContext) -> Iterator[str]:
    """Execution iterator for either mode; finalizes its own trace run in both."""
    if context.agent.agentic_mode:
        yield from _agentic_pieces_traced(context)
    else:
        # WorkflowRuntime.stream_workflow completes/fails the run itself.
        yield from _non_agentic_pieces(context.agent_run_id, context.agent, context.data.temperature, context.messages, context.trace_store)


def _sse_chunk(chat_id: str, created: int, model: str, delta: dict, finish_reason: str | None) -> str:
    payload = {
        "id": chat_id,
        "object": "chat.completion.chunk",
        "created": created,
        "model": model,
        "choices": [{"index": 0, "delta": delta, "finish_reason": finish_reason}],
    }
    return f"data: {json.dumps(payload, ensure_ascii=False, separators=(',', ':'))}\n\n"


def _stream_chat(context: ChatExecutionContext) -> Iterator[str]:
    chat_id = f"chatcmpl-{secrets.token_hex(8)}"
    created = int(time.time())
    model = context.data.model
    try:
        for piece in _execution_pieces(context):
            yield _sse_chunk(chat_id, created, model, {"content": piece}, None)
    except Exception as error:  # noqa: BLE001 - mid-stream failures close the stream cleanly instead of crashing
        logger.error("v1 streaming chat completion failed: %s", repr(error))
        yield _sse_chunk(chat_id, created, model, {}, "stop")
        yield "data: [DONE]\n\n"
        return
    yield _sse_chunk(chat_id, created, model, {}, "stop")
    yield "data: [DONE]\n\n"


@router.post("/chat/completions")
async def chat_completions(request: Request):
    raw_body = await request.body()
    # All blocking sync work (prepare + execution) runs in the threadpool so
    # the psycopg DB writes never stall the event loop.
    context, error = await run_in_threadpool(_prepare_chat_completion, request, raw_body)
    if context is None:
        return error

    if context.data.stream:
        # Sync generator on purpose: Starlette iterates sync iterators in its
        # threadpool, so the blocking provider/DB work never stalls the event loop.
        return StreamingResponse(_stream_chat(context), media_type="text/event-stream")

    try:
        # run_in_threadpool keeps the blocking sync DB + LLM work off the event loop.
        if context.agent.agentic_mode:
            output = await run_in_threadpool(
                _run_agentic,
                context.user_id,
                context.agent_run_id,
                context.agent,
                context.temperature,
                context.messages,
                context.trace_store,
            )
        else:
            output = await run_in_threadpool(
                _run_non_agentic,
                context.agent_run_id,
                context.agent,
                context.data.temperature,
                context.messages,
                context.trace_store,
            )
    except Exception as error:  # noqa: BLE001 - every provider failure surfaces as an OpenAI-shape 502
        logger.error("v1 chat completion failed: %s", repr(error))
        try:
            context.trace_store.fail_run(context.agent_run_id, str(error))
        except Exception:  # noqa: BLE001 - tracing must not mask the client error
            logger.warning("Could not mark v1 run %s as failed", context.agent_run_id)
        return openai_error(502, "The model failed to generate a response. Please try again later.", "api_error", "api_error")

    prompt_tokens = sum(len(message.content) for message in context.messages) // 4
    completion_tokens = len(output) // 4
    return JSONResponse(
        content={
            "id": f"chatcmpl-{secrets.token_hex(8)}",
            "object": "chat.completion",
            "created": int(time.time()),
            "model": context.data.model,
            "choices": [
                {
                    "index": 0,
                    "message": {"role": "assistant", "content": output},
                    "finish_reason": "stop",
                }
            ],
            "usage": {
                "prompt_tokens": prompt_tokens,
                "completion_tokens": completion_tokens,
                "total_tokens": prompt_tokens + completion_tokens,
            },
        }
    )
