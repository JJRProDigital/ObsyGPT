import asyncio
import json
import types

import pytest

from app.agent.tools.base import ToolResult, ToolSpec, UnknownToolError
from app.v1 import routes
from app.v1.keys import KeyAuthError
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
    def __init__(self, provider_registry=None, trace_store=None, skill_registry=None):
        self.trace_store = trace_store
        self.calls = []

    def stream_workflow(self, agent_run_id, workflow, messages):
        self.calls.append((agent_run_id, workflow, list(messages)))
        yield "Hola "
        yield "desde ObsyGPT"


class FakeAgentLoop:
    created = []

    def __init__(self, provider_registry=None, trace_store=None, execute_tool=None):
        self.trace_store = trace_store
        self.execute_tool = execute_tool
        self.run_kwargs = None
        FakeAgentLoop.created.append(self)

    def run(self, **kwargs):
        self.run_kwargs = kwargs
        return iter(["Listo"])


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
        if self.filtered_to is not None and name not in self.filtered_to:
            raise UnknownToolError(f"Tool is not registered: {name}")
        self.executed.append((name, args))
        return ToolResult(ok=True, output=f"ran {name}")


def patch_common(monkeypatch, agent, *, instructions="", memory="", semantic=""):
    trace_store = FakeTraceStore()
    runtime = FakeWorkflowRuntime()
    semantic_queries = []
    monkeypatch.setattr(routes, "authenticate_key", lambda header: 5)
    monkeypatch.setattr(routes, "resolve_agent", lambda model: agent)
    monkeypatch.setattr(routes, "get_user_preferences", lambda user_id: {})
    monkeypatch.setattr(routes, "TraceStore", lambda: trace_store)
    monkeypatch.setattr(routes, "WorkflowRuntime", lambda **kwargs: runtime)
    monkeypatch.setattr(routes, "build_user_instructions_block", lambda user_id: instructions)
    monkeypatch.setattr(routes, "build_memory_context", lambda user_id: memory)

    def fake_semantic(user_id, query):
        semantic_queries.append(query)
        return semantic

    monkeypatch.setattr(routes, "build_semantic_context_block", fake_semantic)
    monkeypatch.setattr(
        routes.chat_specs,
        "get_workflow_spec",
        lambda workflow_id, agent_id: WorkflowSpec(id=None, name="Selected Agent", workflow_type="single_agent", agents=[agent]),
    )
    return types.SimpleNamespace(trace_store=trace_store, runtime=runtime, semantic_queries=semantic_queries)


def error_body(response):
    return json.loads(response.body)["error"]


def test_list_models_returns_enabled_agents(monkeypatch):
    monkeypatch.setattr(routes, "authenticate_key", lambda header: 5)
    monkeypatch.setattr(routes, "list_enabled_agents", lambda: [(2, "Helper"), (7, "Writer")])
    response = routes.list_models(FakeRequest({"authorization": "Bearer ogpt-x"}))
    assert response.status_code == 200
    assert json.loads(response.body) == {
        "object": "list",
        "data": [
            {"id": "agent-2", "object": "model", "owned_by": "obsygpt"},
            {"id": "agent-7", "object": "model", "owned_by": "obsygpt"},
        ],
    }


def test_list_models_missing_auth_returns_openai_401(monkeypatch):
    def boom(header):
        raise KeyAuthError("Missing Authorization header.")

    monkeypatch.setattr(routes, "authenticate_key", boom)
    response = routes.list_models(FakeRequest())
    assert response.status_code == 401
    assert error_body(response) == {
        "message": "Missing Authorization header.",
        "type": "invalid_request_error",
        "code": "invalid_api_key",
    }


def test_completion_non_agentic_happy_path(monkeypatch):
    agent = make_agent()
    ctx = patch_common(monkeypatch, agent, instructions="", memory="", semantic="")
    payload = {"model": "helper", "messages": [{"role": "user", "content": "Hola"}]}
    response = call_completions({"authorization": "Bearer ogpt-x"}, payload)
    assert response.status_code == 200
    body = json.loads(response.body)
    assert body["id"].startswith("chatcmpl-")
    assert body["object"] == "chat.completion"
    assert isinstance(body["created"], int)
    assert body["model"] == "helper"
    assert body["choices"] == [
        {"index": 0, "message": {"role": "assistant", "content": "Hola desde ObsyGPT"}, "finish_reason": "stop"}
    ]
    prompt_chars = len("You are Helper.") + len("Hola") + len(routes.NON_AGENTIC_NOTE)
    assert body["usage"] == {
        "prompt_tokens": prompt_chars // 4,
        "completion_tokens": len("Hola desde ObsyGPT") // 4,
        "total_tokens": prompt_chars // 4 + len("Hola desde ObsyGPT") // 4,
    }
    assert ctx.trace_store.runs == [(5, None, None, 3, None)]
    assert ctx.runtime.calls[0][0] == 4242
    assert ctx.runtime.calls[0][1].agents == [agent]


def test_completion_unknown_model_returns_openai_404(monkeypatch):
    monkeypatch.setattr(routes, "authenticate_key", lambda header: 5)
    monkeypatch.setattr(routes, "resolve_agent", lambda model: None)
    payload = {"model": "ghost", "messages": [{"role": "user", "content": "hola"}]}
    response = call_completions({"authorization": "Bearer ogpt-x"}, payload)
    assert response.status_code == 404
    assert error_body(response) == {
        "message": "The model 'ghost' does not exist or is disabled.",
        "type": "invalid_request_error",
        "code": "model_not_found",
    }


@pytest.mark.parametrize("headers", [{}, {"authorization": "Bearer ogpt-bad"}])
def test_completion_invalid_auth_returns_openai_401(monkeypatch, headers):
    def boom(header):
        raise KeyAuthError("Invalid or revoked API key.")

    monkeypatch.setattr(routes, "authenticate_key", boom)
    payload = {"model": "helper", "messages": [{"role": "user", "content": "hola"}]}
    response = call_completions(headers, payload)
    assert response.status_code == 401
    assert error_body(response) == {
        "message": "Invalid or revoked API key.",
        "type": "invalid_request_error",
        "code": "invalid_api_key",
    }


def patch_agent_loop(monkeypatch):
    monkeypatch.setattr(routes, "AgentLoop", lambda **kwargs: FakeAgentLoop(**kwargs))
    return FakeAgentLoop


def test_completion_agentic_filters_registry_and_specs_to_safe(monkeypatch):
    agent = make_agent(agentic_mode=True)
    ctx = patch_common(monkeypatch, agent)
    safe_web = ToolSpec(name="web_fetch", description="d", parameters="{}", permission="safe")
    safe_files = ToolSpec(name="read_file", description="d", parameters="{}", permission="safe")
    sensitive = ToolSpec(name="run_terminal", description="d", parameters="{}", permission="sensitive")
    registry = FakeRegistry([safe_web, safe_files, sensitive])
    loops = patch_agent_loop(monkeypatch)
    monkeypatch.setattr(routes.chat_specs, "build_agent_tool_registry", lambda **kwargs: registry)
    monkeypatch.setattr(routes.chat_specs, "get_agent_tool_specs", lambda agent_id, user_id=None: [safe_web, sensitive])

    payload = {"model": "helper", "messages": [{"role": "user", "content": "busca"}]}
    response = call_completions({"authorization": "Bearer ogpt-x"}, payload)

    loop = loops.created[-1]
    assert response.status_code == 200
    assert registry.filtered_to == {"web_fetch", "read_file"}
    assert [spec.name for spec in loop.run_kwargs["tool_specs"]] == ["web_fetch"]
    assert json.loads(response.body)["choices"][0]["message"]["content"] == "Listo"
    assert ctx.trace_store.completed == [(4242, "Listo")]
    assert loop.execute_tool("web_fetch", {"url": "https://x"}) == ToolResult(ok=True, output="ran web_fetch")
    assert registry.executed == [("web_fetch", {"url": "https://x"})]
    assert loop.trace_store is ctx.trace_store


def test_completion_agentic_excludes_user_blocked_tools(monkeypatch):
    agent = make_agent(agentic_mode=True)
    patch_common(monkeypatch, agent)
    safe_web = ToolSpec(name="web_fetch", description="d", parameters="{}", permission="safe")
    safe_files = ToolSpec(name="read_file", description="d", parameters="{}", permission="safe")
    registry = FakeRegistry([safe_web, safe_files])
    loops = patch_agent_loop(monkeypatch)
    monkeypatch.setattr(routes.chat_specs, "build_agent_tool_registry", lambda **kwargs: registry)
    monkeypatch.setattr(routes.chat_specs, "get_agent_tool_specs", lambda agent_id, user_id=None: [safe_web, safe_files])
    monkeypatch.setattr(routes, "get_user_preferences", lambda user_id: {"tool_policies": {"web_fetch": "block"}})

    payload = {"model": "helper", "messages": [{"role": "user", "content": "busca"}]}
    response = call_completions({"authorization": "Bearer ogpt-x"}, payload)

    loop = loops.created[-1]
    assert response.status_code == 200
    assert registry.filtered_to == {"read_file"}
    assert [spec.name for spec in loop.run_kwargs["tool_specs"]] == ["read_file"]
    with pytest.raises(UnknownToolError):
        loop.execute_tool("web_fetch", {"url": "https://x"})
    assert registry.executed == []


def test_completion_temperature_defaults_to_agent_temperature(monkeypatch):
    agent = make_agent(agentic_mode=True, temperature=0.3)
    patch_common(monkeypatch, agent)
    loops = patch_agent_loop(monkeypatch)
    monkeypatch.setattr(routes.chat_specs, "build_agent_tool_registry", lambda **kwargs: FakeRegistry([]))
    monkeypatch.setattr(routes.chat_specs, "get_agent_tool_specs", lambda agent_id, user_id=None: [])

    payload = {"model": "helper", "messages": [{"role": "user", "content": "hola"}]}
    call_completions({"authorization": "Bearer ogpt-x"}, payload)
    assert loops.created[-1].run_kwargs["temperature"] == 0.3


def test_completion_request_temperature_overrides_agent(monkeypatch):
    agent = make_agent(agentic_mode=True, temperature=0.3)
    patch_common(monkeypatch, agent)
    loops = patch_agent_loop(monkeypatch)
    monkeypatch.setattr(routes.chat_specs, "build_agent_tool_registry", lambda **kwargs: FakeRegistry([]))
    monkeypatch.setattr(routes.chat_specs, "get_agent_tool_specs", lambda agent_id, user_id=None: [])

    payload = {"model": "helper", "temperature": 0.9, "messages": [{"role": "user", "content": "hola"}]}
    call_completions({"authorization": "Bearer ogpt-x"}, payload)
    assert loops.created[-1].run_kwargs["temperature"] == 0.9


def test_completion_non_agentic_applies_client_temperature(monkeypatch):
    agent = make_agent(temperature=0.3)
    ctx = patch_common(monkeypatch, agent)
    payload = {"model": "helper", "temperature": 0.2, "messages": [{"role": "user", "content": "hola"}]}
    response = call_completions({"authorization": "Bearer ogpt-x"}, payload)
    assert response.status_code == 200
    workflow = ctx.runtime.calls[0][1]
    assert workflow.agents[0].temperature == 0.2


def test_completion_client_system_message_and_context_blocks_order(monkeypatch):
    agent = make_agent()
    ctx = patch_common(monkeypatch, agent, instructions="INSTR", memory="MEM", semantic="SEM")
    payload = {
        "model": "helper",
        "messages": [
            {"role": "system", "content": "Responde breve."},
            {"role": "user", "content": "primera pregunta"},
            {"role": "user", "content": "Hola"},
        ],
    }
    response = call_completions({"authorization": "Bearer ogpt-x"}, payload)
    assert response.status_code == 200
    messages = ctx.runtime.calls[0][2]
    assert [(m.role, m.content) for m in messages] == [
        ("system", "You are Helper."),
        ("system", "Responde breve."),
        ("user", "primera pregunta"),
        ("user", "Hola"),
        ("user", "INSTR"),
        ("user", "MEM"),
        ("user", "SEM"),
        ("user", routes.NON_AGENTIC_NOTE),
    ]
    assert ctx.semantic_queries == ["Hola"]


def test_completion_unknown_role_returns_openai_400(monkeypatch):
    monkeypatch.setattr(routes, "authenticate_key", lambda header: 5)
    payload = {"model": "helper", "messages": [{"role": "tool", "content": "x"}]}
    response = call_completions({"authorization": "Bearer ogpt-x"}, payload)
    assert response.status_code == 400
    body = error_body(response)
    assert body["type"] == "invalid_request_error"
    assert "tool" in body["message"]


def test_completion_empty_messages_returns_openai_400(monkeypatch):
    monkeypatch.setattr(routes, "authenticate_key", lambda header: 5)
    payload = {"model": "helper", "messages": []}
    response = call_completions({"authorization": "Bearer ogpt-x"}, payload)
    assert response.status_code == 400
    body = error_body(response)
    assert body["type"] == "invalid_request_error"
    assert "messages" in body["message"]


def test_completion_malformed_payload_returns_openai_400(monkeypatch):
    monkeypatch.setattr(routes, "authenticate_key", lambda header: 5)
    response = call_completions({"authorization": "Bearer ogpt-x"}, {"messages": [{"role": "user", "content": "hola"}]})
    assert response.status_code == 400
    body = error_body(response)
    assert body["type"] == "invalid_request_error"
    assert body["code"] == "invalid_request_error"


@pytest.mark.parametrize("raw", [b"", b"not json at all", b"{truncated"])
def test_completion_invalid_json_body_returns_openai_400(monkeypatch, raw):
    monkeypatch.setattr(routes, "authenticate_key", lambda header: 5)
    response = call_completions({"authorization": "Bearer ogpt-x"}, raw=raw)
    assert response.status_code == 400
    assert error_body(response) == {
        "message": "Invalid JSON body",
        "type": "invalid_request_error",
        "code": "invalid_request_error",
    }


@pytest.mark.parametrize("raw", [b"[1, 2]", b'"hello"', b"42", b"null"])
def test_completion_non_object_json_body_returns_openai_400(monkeypatch, raw):
    monkeypatch.setattr(routes, "authenticate_key", lambda header: 5)
    response = call_completions({"authorization": "Bearer ogpt-x"}, raw=raw)
    assert response.status_code == 400
    assert error_body(response) == {
        "message": "Body must be a JSON object",
        "type": "invalid_request_error",
        "code": "invalid_request_error",
    }


@pytest.mark.parametrize("raw", [b"\x89PNG\r\n\x1a\n\x00\x00\x00\rIHDR", b"\x80\x81\x82\x83 binary\xff"])
def test_completion_binary_body_returns_openai_400(monkeypatch, raw):
    monkeypatch.setattr(routes, "authenticate_key", lambda header: 5)
    response = call_completions({"authorization": "Bearer ogpt-x"}, raw=raw)
    assert response.status_code == 400
    assert error_body(response) == {
        "message": "Invalid JSON body",
        "type": "invalid_request_error",
        "code": "invalid_request_error",
    }


def test_run_agentic_empty_output_still_completes_run(monkeypatch):
    agent = make_agent(agentic_mode=True)
    ctx = patch_common(monkeypatch, agent)

    class EmptyOutputLoop(FakeAgentLoop):
        def run(self, **kwargs):
            self.run_kwargs = kwargs
            return iter([])

    monkeypatch.setattr(routes, "AgentLoop", lambda **kwargs: EmptyOutputLoop(**kwargs))
    monkeypatch.setattr(routes.chat_specs, "build_agent_tool_registry", lambda **kwargs: FakeRegistry([]))
    monkeypatch.setattr(routes.chat_specs, "get_agent_tool_specs", lambda agent_id, user_id=None: [])

    payload = {"model": "helper", "messages": [{"role": "user", "content": "hola"}]}
    response = call_completions({"authorization": "Bearer ogpt-x"}, payload)

    assert response.status_code == 200
    assert json.loads(response.body)["choices"][0]["message"]["content"] == ""
    assert ctx.trace_store.completed == [(4242, "")]


def test_completion_rate_limited_returns_openai_429(monkeypatch):
    monkeypatch.setattr(routes, "authenticate_key", lambda header: 5)
    monkeypatch.setattr(routes, "resolve_agent", lambda model: None)
    monkeypatch.setattr(routes, "chat_rate_limiter", routes.KeyRateLimiter(max_attempts=1, window_seconds=60, now=lambda: 1000.0))
    payload = {"model": "helper", "messages": [{"role": "user", "content": "hola"}]}
    first = call_completions({"authorization": "Bearer ogpt-x"}, payload)
    assert first.status_code == 404
    second = call_completions({"authorization": "Bearer ogpt-x"}, payload)
    assert second.status_code == 429
    body = error_body(second)
    assert body["type"] == "rate_limit_error"
    assert body["code"] == "rate_limit_exceeded"


def test_completion_agentic_ask_policy_excluded_by_default(monkeypatch):
    agent = make_agent(agentic_mode=True)
    patch_common(monkeypatch, agent)
    safe_web = ToolSpec(name="web_fetch", description="d", parameters="{}", permission="safe")
    safe_files = ToolSpec(name="read_file", description="d", parameters="{}", permission="safe")
    registry = FakeRegistry([safe_web, safe_files])
    loops = patch_agent_loop(monkeypatch)
    monkeypatch.setattr(routes.chat_specs, "build_agent_tool_registry", lambda **kwargs: registry)
    monkeypatch.setattr(routes.chat_specs, "get_agent_tool_specs", lambda agent_id, user_id=None: [safe_web, safe_files])
    monkeypatch.setattr(routes, "get_user_preferences", lambda user_id: {"tool_policies": {"web_fetch": "ask"}})

    response = call_completions({"authorization": "Bearer ogpt-x"}, {"model": "helper", "messages": [{"role": "user", "content": "busca"}]})

    loop = loops.created[-1]
    assert response.status_code == 200
    assert registry.filtered_to == {"read_file"}
    assert [spec.name for spec in loop.run_kwargs["tool_specs"]] == ["read_file"]


def test_completion_agentic_v1_access_overrides_ask(monkeypatch):
    agent = make_agent(agentic_mode=True)
    patch_common(monkeypatch, agent)
    safe_web = ToolSpec(name="web_fetch", description="d", parameters="{}", permission="safe")
    safe_files = ToolSpec(name="read_file", description="d", parameters="{}", permission="safe")
    registry = FakeRegistry([safe_web, safe_files])
    loops = patch_agent_loop(monkeypatch)
    monkeypatch.setattr(routes.chat_specs, "build_agent_tool_registry", lambda **kwargs: registry)
    monkeypatch.setattr(routes.chat_specs, "get_agent_tool_specs", lambda agent_id, user_id=None: [safe_web, safe_files])
    monkeypatch.setattr(routes, "get_user_preferences", lambda user_id: {"tool_policies": {"web_fetch": "ask"}, "tool_v1_access": {"web_fetch": True, "read_file": False}})

    response = call_completions({"authorization": "Bearer ogpt-x"}, {"model": "helper", "messages": [{"role": "user", "content": "busca"}]})

    loop = loops.created[-1]
    assert response.status_code == 200
    assert registry.filtered_to == {"web_fetch"}
    assert [spec.name for spec in loop.run_kwargs["tool_specs"]] == ["web_fetch"]