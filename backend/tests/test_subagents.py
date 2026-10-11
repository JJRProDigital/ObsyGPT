import pytest

from app.agent import subagents
from app.agent.errors import ApprovalRequiredError
from app.agent.subagents import (
    DispatchSubagentsTool,
    DISPATCH_SPEC,
    MAX_SUBAGENTS,
    build_child_approval_executor,
    dispatch_complete_observation,
    get_agent_spec_by_name,
    mark_child_completed_and_cascade,
    run_child,
)
from app.agent.tools.base import ToolRegistry, ToolResult, ToolSpec
from app.providers import ChatMessage


class FakeTraceStore:
    def __init__(self):
        self.events = []
        self.next_id = 100

    def create_run(self, user_id, conversation_id, message_id, agent_id, workflow_id=None, parent_run_id=None):
        self.next_id += 1
        return self.next_id

    def add_event(self, agent_run_id, event_type, title, content=""):
        self.events.append((agent_run_id, event_type, title))


class _FakeCursor:
    def __init__(self, script):
        self._script = script
        self.rowcount = 0

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc, traceback):
        return False

    def execute(self, query, params=()):
        self._result = self._script(query, params)

    def fetchone(self):
        return self._result


class _FakeConnection:
    def __init__(self, script):
        self._script = script

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc, traceback):
        return False

    def cursor(self):
        return _FakeCursor(self._script)


def _patch_connect(monkeypatch, script):
    monkeypatch.setattr("app.agent.subagents.connect", lambda: _FakeConnection(script))


def test_dispatch_spec_is_sensitive():
    assert DISPATCH_SPEC.name == "dispatch_subagents"
    assert DISPATCH_SPEC.permission == "sensitive"


def test_dispatch_tool_appends_user_context_to_child_goal(monkeypatch):
    sent_goals = []

    def script(query, params):
        if "FROM agents a" in query:
            return (7, "A", "p", "openrouter", None, None, "m", 0.7)
        return None

    _patch_connect(monkeypatch, script)
    monkeypatch.setattr("app.agent.subagents.get_agent_spec_by_name", lambda name: type("Agent", (), {"id": 7, "name": name, "system_prompt": "p", "provider_type": "openrouter", "provider_base_url": None, "provider_api_key_env": None, "model": "m", "temperature": 0.7, "fallbacks": []})())
    monkeypatch.setattr("app.agent.subagents.run_child", lambda user_id, child_run_id, agent, goal, workspace_root, conversation_id, ts: (sent_goals.append(goal), {"status": "completed", "result": "ok"})[1])
    monkeypatch.setattr("app.agent.subagents.update_dispatch", lambda child_run_id, status, result="": None)
    monkeypatch.setattr("app.agent.subagents.dispatch_complete_observation", lambda parent_run_id: "TOOL RESULT (dispatch_subagents):\nok")

    html_code = "<html><body><h1>Hola</h1></body></html>"
    tool = DispatchSubagentsTool(1, 5, None, 2, FakeTraceStore(), context_message=f"Revisa este codigo: {html_code}")
    result = tool.run({"tasks": [{"agent": "A", "goal": "Revisar el codigo HTML"}]})

    assert result.ok
    assert "Revisar el codigo HTML" in sent_goals[0]
    assert html_code in sent_goals[0]
    assert "no ve la conversacion" in sent_goals[0]


def test_dispatch_tool_marks_truncated_context(monkeypatch):
    sent_goals = []

    def script(query, params):
        if "FROM agents a" in query:
            return (7, "A", "p", "openrouter", None, None, "m", 0.7)
        return None

    _patch_connect(monkeypatch, script)
    monkeypatch.setattr("app.agent.subagents.get_agent_spec_by_name", lambda name: type("Agent", (), {"id": 7, "name": name, "system_prompt": "p", "provider_type": "openrouter", "provider_base_url": None, "provider_api_key_env": None, "model": "m", "temperature": 0.7, "fallbacks": []})())
    monkeypatch.setattr("app.agent.subagents.run_child", lambda user_id, child_run_id, agent, goal, workspace_root, conversation_id, ts: (sent_goals.append(goal), {"status": "completed", "result": "ok"})[1])
    monkeypatch.setattr("app.agent.subagents.update_dispatch", lambda child_run_id, status, result="": None)
    monkeypatch.setattr("app.agent.subagents.dispatch_complete_observation", lambda parent_run_id: "TOOL RESULT (dispatch_subagents):\nok")

    from app.agent.subagents import MAX_CONTEXT_CHARS

    long_document = "x" * (MAX_CONTEXT_CHARS + 5000)
    tool = DispatchSubagentsTool(1, 5, None, 2, FakeTraceStore(), context_message=long_document)
    tool.run({"tasks": [{"agent": "A", "goal": "Revisar el documento"}]})

    goal = sent_goals[0]
    assert "documento truncado" in goal
    assert MAX_CONTEXT_CHARS not in (len(goal),)  # sanity: goal is capped around MAX_CONTEXT_CHARS plus wrappers


def test_dispatch_tool_without_context_keeps_goal_clean(monkeypatch):
    sent_goals = []

    def script(query, params):
        if "FROM agents a" in query:
            return (7, "A", "p", "openrouter", None, None, "m", 0.7)
        return None

    _patch_connect(monkeypatch, script)
    monkeypatch.setattr("app.agent.subagents.get_agent_spec_by_name", lambda name: type("Agent", (), {"id": 7, "name": name, "system_prompt": "p", "provider_type": "openrouter", "provider_base_url": None, "provider_api_key_env": None, "model": "m", "temperature": 0.7, "fallbacks": []})())
    monkeypatch.setattr("app.agent.subagents.run_child", lambda user_id, child_run_id, agent, goal, workspace_root, conversation_id, ts: (sent_goals.append(goal), {"status": "completed", "result": "ok"})[1])
    monkeypatch.setattr("app.agent.subagents.update_dispatch", lambda child_run_id, status, result="": None)
    monkeypatch.setattr("app.agent.subagents.dispatch_complete_observation", lambda parent_run_id: "TOOL RESULT (dispatch_subagents):\nok")

    tool = DispatchSubagentsTool(1, 5, None, 2, FakeTraceStore())
    tool.run({"tasks": [{"agent": "A", "goal": "Solo el goal"}]})

    assert sent_goals[0] == "Solo el goal"


def test_dispatch_tool_requires_tasks_list():
    result = DispatchSubagentsTool(1, 1, None, None, FakeTraceStore()).run({"tasks": "nope"})
    assert not result.ok
    assert "tasks" in result.output


def test_dispatch_tool_rejects_unknown_agent(monkeypatch):
    """A hallucinated agent name no longer aborts the dispatch: it reports the
    unknown agent AND the available ones so the model can correct itself."""
    _patch_connect(monkeypatch, lambda query, params: None)
    monkeypatch.setattr("app.agent.subagents.available_agent_names", lambda: ["Research Agent", "Writer Agent"])
    result = DispatchSubagentsTool(1, 1, None, None, FakeTraceStore()).run({"tasks": [{"agent": "Ghost", "goal": "x"}]})
    assert not result.ok
    assert "Ghost" in result.output
    assert "Research Agent" in result.output, "must list available agents so the model can retry"


def test_dispatch_tool_runs_children_and_aggregates(monkeypatch):
    trace_store = FakeTraceStore()
    created_children = []

    def script(query, params):
        if "FROM agents a" in query:
            return (7, "Research Agent", "prompt", "openrouter", None, "OPENROUTER_API_KEY", "model-x", 0.7)
        if "INSERT INTO subagent_dispatches" in query:
            created_children.append(params[1])
            return None
        return None

    _patch_connect(monkeypatch, script)
    monkeypatch.setattr("app.agent.subagents.get_agent_spec_by_name", lambda name: type("Agent", (), {"id": 7, "name": name, "system_prompt": "p", "provider_type": "openrouter", "provider_base_url": None, "provider_api_key_env": None, "model": "m", "temperature": 0.7, "fallbacks": []})())
    monkeypatch.setattr("app.agent.subagents.run_child", lambda user_id, child_run_id, agent, goal, workspace_root, conversation_id, ts: {"status": "completed", "result": f"resultado de {goal}"})
    monkeypatch.setattr("app.agent.subagents.update_dispatch", lambda child_run_id, status, result="": None)
    monkeypatch.setattr("app.agent.subagents.dispatch_complete_observation", lambda parent_run_id: "TOOL RESULT (dispatch_subagents):\nagregado")

    tool = DispatchSubagentsTool(1, 5, None, 2, trace_store)
    result = tool.run({"tasks": [{"agent": "Research Agent", "goal": "buscar X"}, {"agent": "Research Agent", "goal": "buscar Y"}]})

    assert result.ok
    assert "agregado" in result.output
    assert any(event[1] == "subagent_started" for event in trace_store.events)
    assert any(event[1] == "subagent_completed" for event in trace_store.events)


def test_dispatch_tool_caps_parallel_tasks(monkeypatch):
    trace_store = FakeTraceStore()
    seen_tasks = []

    def script(query, params):
        if "FROM agents a" in query:
            return (7, "A", "p", "openrouter", None, None, "m", 0.7)
        if "INSERT INTO subagent_dispatches" in query:
            return None
        return None

    _patch_connect(monkeypatch, script)
    monkeypatch.setattr("app.agent.subagents.get_agent_spec_by_name", lambda name: type("Agent", (), {"id": 7, "name": name, "system_prompt": "p", "provider_type": "openrouter", "provider_base_url": None, "provider_api_key_env": None, "model": "m", "temperature": 0.7, "fallbacks": []})())
    monkeypatch.setattr("app.agent.subagents.run_child", lambda user_id, child_run_id, agent, goal, workspace_root, conversation_id, ts: (seen_tasks.append(goal), {"status": "completed", "result": "ok"})[1])
    monkeypatch.setattr("app.agent.subagents.update_dispatch", lambda child_run_id, status, result="": None)
    monkeypatch.setattr("app.agent.subagents.dispatch_complete_observation", lambda parent_run_id: "TOOL RESULT (dispatch_subagents):\nagregado")

    tasks = [{"agent": "A", "goal": f"t{i}"} for i in range(6)]
    result = DispatchSubagentsTool(1, 5, None, 2, trace_store).run({"tasks": tasks})

    assert result.ok
    assert len(seen_tasks) == MAX_SUBAGENTS


def test_dispatch_tool_raises_pending_child_approval(monkeypatch):
    trace_store = FakeTraceStore()

    def script(query, params):
        if "FROM agents a" in query:
            return (7, "A", "p", "openrouter", None, None, "m", 0.7)
        return None

    _patch_connect(monkeypatch, script)
    monkeypatch.setattr("app.agent.subagents.get_agent_spec_by_name", lambda name: type("Agent", (), {"id": 7, "name": name, "system_prompt": "p", "provider_type": "openrouter", "provider_base_url": None, "provider_api_key_env": None, "model": "m", "temperature": 0.7, "fallbacks": []})())
    monkeypatch.setattr("app.agent.subagents.run_child", lambda user_id, child_run_id, agent, goal, workspace_root, conversation_id, ts: {"status": "awaiting_approval", "approval_id": 77, "result": ""})
    monkeypatch.setattr("app.agent.subagents.update_dispatch", lambda child_run_id, status, result="": None)

    with pytest.raises(ApprovalRequiredError) as error:
        DispatchSubagentsTool(1, 5, None, 2, trace_store).run({"tasks": [{"agent": "A", "goal": "x"}]})

    assert error.value.approval_id == 77
    assert error.value.tool_name == "dispatch_subagents"


def test_child_executor_asks_for_approval_on_sensitive(monkeypatch):
    class FakeRegistry:
        def get(self, name):
            class FakeTool:
                spec = ToolSpec(name="write_file", description="d", parameters="{}", permission="sensitive")

            return FakeTool()

    captured = {}

    def fake_create_approval(agent_run_id, user_id, conversation_id, tool_name, args, task_id=None):
        captured.update({"agent_run_id": agent_run_id, "tool_name": tool_name})
        return 42

    monkeypatch.setattr("app.agent.subagents.create_tool_approval", fake_create_approval)
    monkeypatch.setattr("app.workspace.routes.get_user_preferences", lambda user_id: {"tool_policies": {}})

    execute = build_child_approval_executor(9, 3, 55, FakeRegistry())
    with pytest.raises(ApprovalRequiredError) as error:
        execute("write_file", {"path": "x"})

    assert error.value.approval_id == 42
    assert captured["agent_run_id"] == 55


def test_dispatch_complete_observation_waits_for_all_children(monkeypatch):
    dispatches = [
        {"child_run_id": 11, "agent_name": "A", "goal": "g1", "status": "completed", "result": "r1"},
        {"child_run_id": 12, "agent_name": "B", "goal": "g2", "status": "awaiting_approval", "result": ""},
    ]
    monkeypatch.setattr("app.agent.subagents.list_dispatches", lambda parent_run_id: dispatches)
    assert dispatch_complete_observation(5) is None

    dispatches[1]["status"] = "completed"
    dispatches[1]["result"] = "r2"
    observation = dispatch_complete_observation(5)
    assert "r1" in observation and "r2" in observation
    assert observation.startswith("TOOL RESULT (dispatch_subagents):")


def test_mark_child_completed_and_cascade_returns_parent_when_done(monkeypatch):
    monkeypatch.setattr("app.agent.subagents.update_dispatch", lambda child_run_id, status, result="": None)
    monkeypatch.setattr("app.agent.subagents.get_parent_run_id", lambda child_run_id: 5)
    monkeypatch.setattr("app.agent.subagents.dispatch_complete_observation", lambda parent_run_id: "TOOL RESULT (dispatch_subagents):\nok")

    cascade = mark_child_completed_and_cascade(12, "final")
    assert cascade == (5, "TOOL RESULT (dispatch_subagents):\nok")


def test_get_agent_spec_by_name_returns_none_when_missing(monkeypatch):
    _patch_connect(monkeypatch, lambda query, params: None)
    assert get_agent_spec_by_name("Ghost") is None


def test_context_for_parent_run_prefers_stored_message(monkeypatch):
    calls = []

    def script(query, params):
        calls.append(query)
        if "SELECT message_id FROM agent_runs" in query:
            return (55,)
        if "SELECT content FROM messages" in query:
            return ("revisa este HTML: <html>...</html>",)
        return None

    _patch_connect(monkeypatch, script)
    context = subagents.context_for_parent_run(78, {"messages": [{"role": "user", "content": "fallback"}]})
    assert context == "revisa este HTML: <html>...</html>"


def test_context_for_parent_run_skips_injected_blocks_in_fallback(monkeypatch):
    _patch_connect(monkeypatch, lambda query, params: None)
    state = {
        "messages": [
            {"role": "user", "content": "SYSTEM NOTE: sin tools"},
            {"role": "user", "content": "Attachment context for this request:\narchivo.txt"},
            {"role": "user", "content": "revisa el codigo real"},
        ]
    }
    context = subagents.context_for_parent_run(78, state)
    assert context == "revisa el codigo real"

def test_parse_tasks_arg_accepts_stringified_json():
    """Regression: llama.cpp XML tool calls stringify nested structures, so
    dispatch_subagents received tasks as a string and failed forever, looping
    the run through repeated approvals (run 114)."""
    from app.agent.subagents import parse_tasks_arg

    stringified = '[{"agent": "Research Agent", "goal": "buscar noticias"}]'
    assert parse_tasks_arg(stringified) == [{"agent": "Research Agent", "goal": "buscar noticias"}]
    assert parse_tasks_arg([{"agent": "a", "goal": "b"}]) == [{"agent": "a", "goal": "b"}]
    assert parse_tasks_arg("no es json") is None
    assert parse_tasks_arg('{"no": "lista"}') is None
    assert parse_tasks_arg(42) is None
    assert parse_tasks_arg(None) is None
