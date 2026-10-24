import asyncio
import json
import types

import pytest
from fastapi.responses import StreamingResponse

from app.agent.tools.base import ToolResult, ToolSpec
from app.v1 import routes
from app.workflows import AgentSpec, WorkflowSpec


class FakeRequest:
    def __init__(self, headers=None, body=b""):
        self.headers = headers or {}
        self.client = types.SimpleNamespace(host="127.0.0.1")
        self._body = body if isinstance(body, (bytes, bytearray)) else body.encode("utf-8")

    async def body(self):
        return bytes(self._body)


def call_completions(headers=None, payload=None, raw=None):
    """Invokes the async endpoint with a serialized payload (or raw bytes)."""
    if raw is None:
        raw = json.dumps(payload).encode("utf-8")
    return asyncio.run(routes.chat_completions(FakeRequest(headers, body=raw)))


def make_agent(**overrides) -> AgentSpec:
    defaults = dict(
        id=3,
        name="Helper",
        system_prompt="You are Helper.",
        provider_type="openrouter",
        provider_base_url=None,
        provider_api_key_env="OPENROUTER_API_KEY",
        model="test-model",
        temperature=0.3,
        agentic_mode=False,
    )
    defaults.update(overrides)
    return AgentSpec(**defaults)


class FakeTraceStore:
    def __init__(self):
        self.runs = []
        self.events = []
        self.completed = []
        self.failed = []

    def create_run(self, user_id, conversation_id, message_id, agent_id, workflow_id=None, parent_run_id=None):
        self.runs.append((user_id, conversation_id, message_id, agent_id, workflow_id))
        return 4242

    def add_event(self, *args, **kwargs):
        self.events.append((args, kwargs))

    def complete_run(self, run_id, final_response):
        self.completed.append((run_id, final_response))

    def fail_run(self, run_id, error):
        self.failed.append((run_id, error))


class FakeWorkflowRuntime:
    def __init__(self, provider_registry=None, trace_store=None, skill_registry=None, pieces=None):
        self.trace_store = trace_store
        self.calls = []
        self.pieces = ["Hola", " mundo"] if pieces is None else pieces

    def stream_workflow(self, agent_run_id, workflow, messages):
        self.calls.append((agent_run_id, workflow, list(messages)))
        yield from self.pieces


class FakeAgentLoop:
    created = []

    def __init__(self, provider_registry=None, trace_store=None, execute_tool=None, pieces=None):
        self.trace_store = trace_store
        self.execute_tool = execute_tool
        self.run_kwargs = None
        self.pieces = ["Listo"] if pieces is None else pieces
        FakeAgentLoop.created.append(self)

    def run(self, **kwargs):
        self.run_kwargs = kwargs
        return iter(self.pieces)


@pytest.fixture(autouse=True)
def reset_fake_loops():
    FakeAgentLoop.created = []
    yield
    FakeAgentLoop.created = []


class FakeRegistry:
    def __init__(self, specs):
        self.specs = list(specs)
        self.filtered_to = None
        self.executed = []

    def list_specs(self):
        return list(self.specs)

    def filter_to(self, allowed):
        self.filtered_to = set(allowed)

    def run(self, name, args):
        self.executed.append((name, args))
        return ToolResult(ok=True, output=f"ran {name}")


def patch_common(monkeypatch, agent, *, runtime_pieces=None):
    trace_store = FakeTraceStore()
    runtime = FakeWorkflowRuntime(pieces=runtime_pieces)
    monkeypatch.setattr(routes, "authenticate_key", lambda header: 5)
    monkeypatch.setattr(routes, "resolve_agent", lambda model: agent)
    monkeypatch.setattr(routes, "get_user_preferences", lambda user_id: {})
    monkeypatch.setattr(routes, "TraceStore", lambda: trace_store)
    monkeypatch.setattr(routes, "WorkflowRuntime", lambda **kwargs: runtime)
    monkeypatch.setattr(routes, "build_user_instructions_block", lambda user_id: "")
    monkeypatch.setattr(routes, "build_memory_context", lambda user_id: "")
    monkeypatch.setattr(routes, "build_semantic_context_block", lambda user_id, query: "")
    monkeypatch.setattr(
        routes.chat_specs,
        "get_workflow_spec",
        lambda workflow_id, agent_id: WorkflowSpec(id=None, name="Selected Agent", workflow_type="single_agent", agents=[agent]),
    )
    return types.SimpleNamespace(trace_store=trace_store, runtime=runtime)


def patch_agent_loop(monkeypatch, pieces=None):
    def factory(**kwargs):
        return FakeAgentLoop(pieces=pieces, **kwargs)

    monkeypatch.setattr(routes, "AgentLoop", factory)
    return FakeAgentLoop


def collect_body(response) -> str:
    """Drains the StreamingResponse body (Starlette wraps sync iterators as async ones)."""

    async def drain():
        return "".join([part async for part in response.body_iterator])

    return asyncio.run(drain())


def sse_data_events(body: str) -> list[str]:
    """Extracts the payload of every `data: ...` event, `[DONE]` included."""
    return [part.removeprefix("data: ") for part in body.split("\n\n") if part]


def parse_chunks(body: str) -> tuple[list[dict], str]:
    events = sse_data_events(body)
    assert events[-1] == "[DONE]"
    return [json.loads(event) for event in events[:-1]], events[-1]


def test_streaming_non_agentic_emits_sse_chunks(monkeypatch):
    agent = make_agent()
    ctx = patch_common(monkeypatch, agent)
    payload = {"model": "helper", "stream": True, "messages": [{"role": "user", "content": "hola"}]}
    response = call_completions({"authorization": "Bearer ogpt-x"}, payload)

    assert isinstance(response, StreamingResponse)
    assert response.media_type == "text/event-stream"
    assert "text/event-stream" in response.headers["content-type"]

    body = collect_body(response)
    chunks, done = parse_chunks(body)
    assert done == "[DONE]"

    delta_chunks, final_chunk = chunks[:-1], chunks[-1]
    assert [chunk["choices"][0]["delta"]["content"] for chunk in delta_chunks] == ["Hola", " mundo"]
    assert final_chunk["choices"] == [{"index": 0, "delta": {}, "finish_reason": "stop"}]
    assert all(chunk["choices"][0]["finish_reason"] is None for chunk in delta_chunks)

    ids = {chunk["id"] for chunk in chunks}
    assert len(ids) == 1
    chat_id = ids.pop()
    assert chat_id.startswith("chatcmpl-")
    assert all(chunk["object"] == "chat.completion.chunk" for chunk in chunks)
    assert all(chunk["model"] == "helper" for chunk in chunks)
    assert all(isinstance(chunk["created"], int) for chunk in chunks)
    assert all("usage" not in chunk for chunk in chunks)

    assert ctx.runtime.calls[0][0] == 4242
    assert [(m.role, m.content) for m in ctx.runtime.calls[0][2]] == [
        ("system", "You are Helper."),
        ("user", "hola"),
        ("user", routes.NON_AGENTIC_NOTE),
    ]


def test_streaming_agentic_emits_chunks_and_filters_tools(monkeypatch):
    agent = make_agent(agentic_mode=True)
    ctx = patch_common(monkeypatch, agent)
    safe_web = ToolSpec(name="web_fetch", description="d", parameters="{}", permission="safe")
    sensitive = ToolSpec(name="run_terminal", description="d", parameters="{}", permission="sensitive")
    registry = FakeRegistry([safe_web, sensitive])
    patch_agent_loop(monkeypatch, pieces=["Listo", " ya"])
    monkeypatch.setattr(routes.chat_specs, "build_agent_tool_registry", lambda **kwargs: registry)
    monkeypatch.setattr(routes.chat_specs, "get_agent_tool_specs", lambda agent_id, user_id=None: [safe_web, sensitive])

    payload = {"model": "helper", "stream": True, "messages": [{"role": "user", "content": "busca"}]}
    response = call_completions({"authorization": "Bearer ogpt-x"}, payload)

    assert isinstance(response, StreamingResponse)
    chunks, done = parse_chunks(collect_body(response))
    assert done == "[DONE]"
    assert [chunk["choices"][0]["delta"]["content"] for chunk in chunks[:-1]] == ["Listo", " ya"]
    assert chunks[-1]["choices"][0]["finish_reason"] == "stop"

    loop = FakeAgentLoop.created[-1]
    assert registry.filtered_to == {"web_fetch"}
    assert [spec.name for spec in loop.run_kwargs["tool_specs"]] == ["web_fetch"]
    assert ctx.trace_store.completed == [(4242, "Listo ya")]
    assert ctx.trace_store.failed == []


class FakeAgentLoopPieces(FakeAgentLoop):
    """Loop whose run() returns a predefined piece iterator (errors included)."""

    def __init__(self, pieces, **kwargs):
        super().__init__(pieces=None, **kwargs)
        self._pieces = pieces

    def run(self, **kwargs):
        self.run_kwargs = kwargs
        return self._pieces


def exploding_pieces():
    yield "Hola"
    raise RuntimeError("provider exploded mid-stream")


def test_streaming_mid_stream_error_closes_stream_and_fails_run(monkeypatch):
    agent = make_agent(agentic_mode=True)
    ctx = patch_common(monkeypatch, agent)
    monkeypatch.setattr(routes, "AgentLoop", lambda **kwargs: FakeAgentLoopPieces(exploding_pieces(), **kwargs))
    monkeypatch.setattr(routes.chat_specs, "build_agent_tool_registry", lambda **kwargs: FakeRegistry([]))
    monkeypatch.setattr(routes.chat_specs, "get_agent_tool_specs", lambda agent_id, user_id=None: [])

    payload = {"model": "helper", "stream": True, "messages": [{"role": "user", "content": "hola"}]}
    response = call_completions({"authorization": "Bearer ogpt-x"}, payload)

    assert isinstance(response, StreamingResponse)
    chunks, done = parse_chunks(collect_body(response))
    assert done == "[DONE]"
    assert [chunk["choices"][0]["delta"]["content"] for chunk in chunks[:-1]] == ["Hola"]
    assert chunks[-1]["choices"][0]["finish_reason"] == "stop"

    assert ctx.trace_store.failed == [(4242, "provider exploded mid-stream")]
    assert ctx.trace_store.completed == []


def test_streaming_pre_stream_errors_keep_openai_json_shape(monkeypatch):
    monkeypatch.setattr(routes, "authenticate_key", lambda header: 5)
    monkeypatch.setattr(routes, "resolve_agent", lambda model: None)
    payload = {"model": "ghost", "stream": True, "messages": [{"role": "user", "content": "hola"}]}
    response = call_completions({"authorization": "Bearer ogpt-x"}, payload)
    assert not isinstance(response, StreamingResponse)
    assert response.status_code == 404
    assert json.loads(response.body)["error"]["code"] == "model_not_found"
