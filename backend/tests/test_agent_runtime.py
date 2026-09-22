import pytest

from app.agent.errors import ApprovalRequiredError
from app.agent.protocol import PROTOCOL_MARKER_CLOSE, PROTOCOL_MARKER_OPEN
from app.agent.runtime import CONNECTION_RETRY_DELAYS, AgentLoop, build_tool_catalog, is_connection_error
from app.providers import ChatMessage


def test_is_connection_error_matches_common_cases():
    assert is_connection_error(Exception("Connection error."))
    assert is_connection_error(Exception("HTTPSConnectionPool: connection refused"))
    assert not is_connection_error(Exception("invalid request: bad json"))


def test_call_primary_retries_connection_errors(monkeypatch):
    monkeypatch.setattr("app.agent.runtime.time", type("FakeTime", (), {"sleep": staticmethod(lambda seconds: None)})())
    calls = {"count": 0}

    def flaky_primary():
        calls["count"] += 1
        if calls["count"] <= 2:
            raise Exception("Connection error.")
        return "ok"

    loop = AgentLoop(trace_store=type("FakeTraceStore", (), {"add_event": lambda self, *a, **k: None})())
    result = loop._call_primary_with_retries(1, flaky_primary)

    assert result == "ok"
    assert calls["count"] == 3


def test_call_primary_raises_non_connection_errors_immediately():
    calls = {"count": 0}

    def bad_request():
        calls["count"] += 1
        raise Exception("400 invalid request")

    loop = AgentLoop(trace_store=type("FakeTraceStore", (), {"add_event": lambda self, *a, **k: None})())
    try:
        loop._call_primary_with_retries(1, bad_request)
        raised = False
    except Exception as error:
        raised = "invalid request" in str(error)
    assert raised
    assert calls["count"] == 1


def test_call_primary_gives_up_after_all_retries(monkeypatch):
    monkeypatch.setattr("app.agent.runtime.time", type("FakeTime", (), {"sleep": staticmethod(lambda seconds: None)})())
    calls = {"count": 0}

    def always_down():
        calls["count"] += 1
        raise Exception("Connection error.")

    loop = AgentLoop(trace_store=type("FakeTraceStore", (), {"add_event": lambda self, *a, **k: None})())
    try:
        loop._call_primary_with_retries(1, always_down)
        raised = False
    except Exception as error:
        raised = "Connection" in str(error)
    assert raised
    assert calls["count"] == len(CONNECTION_RETRY_DELAYS) + 1


class FakeProviderRegistry:
    def __init__(self, responses: list[str]):
        self.responses = list(responses)
        self.requests: list[object] = []

    def stream_chat_with_config(self, provider_type, request, api_key_env=None, base_url=None):
        self.requests.append(request)
        response = self.responses.pop(0)
        yield response


class FakeTraceStore:
    def __init__(self):
        self.events: list[tuple] = []
        self.tool_calls: list[tuple] = []

    def add_event(self, agent_run_id, event_type, title, content=""):
        self.events.append((agent_run_id, event_type, title, content))

    def add_tool_call(self, agent_run_id, skill_name, input_summary, output_summary, status):
        self.tool_calls.append((agent_run_id, skill_name, input_summary, output_summary, status))


def tool_block(name: str, args: str) -> str:
    return PROTOCOL_MARKER_OPEN + f'\n{{"tool": "{name}", "args": {args}}}\n' + PROTOCOL_MARKER_CLOSE


def run_loop(responses, tool_executor=None, max_iterations=8, activities=None):
    provider = FakeProviderRegistry(responses)
    traces = FakeTraceStore()
    executor_calls: list[tuple] = []

    def executor(name, args):
        executor_calls.append((name, args))
        if tool_executor:
            return tool_executor(name, args)
        from app.agent.tools.base import ToolResult

        return ToolResult(ok=True, output=f"resultado de {name}")

    loop = AgentLoop(provider_registry=provider, trace_store=traces, execute_tool=executor)
    chunks = list(
        loop.run(
            agent_run_id=1,
            system_prompt="Eres ObsyGPT.",
            provider_type="llamacpp",
            provider_base_url=None,
            provider_api_key_env=None,
            model="gemma",
            temperature=0.7,
            tool_specs=build_tool_catalog([("read_file", "Lee un fichero", "safe")]),
            messages=[ChatMessage(role="user", content="lee el readme")],
            max_iterations=max_iterations,
            on_activity=(activities.append if activities is not None else None),
        )
    )
    return provider, traces, executor_calls, "".join(chunks)


def test_loop_returns_final_answer_without_tools():
    _, _, _, output = run_loop(["La respuesta final."])

    assert output == "La respuesta final."


def test_loop_emits_activity_sequence():
    activities: list[dict] = []
    provider = FakeProviderRegistry([tool_block("read_file", '{"path": "README.md"}'), "He leido el fichero."])
    traces = FakeTraceStore()

    def executor(name, args):
        from app.agent.tools.base import ToolResult

        return ToolResult(ok=True, output=f"resultado de {name}")

    loop = AgentLoop(provider_registry=provider, trace_store=traces, execute_tool=executor)
    list(
        loop.run(
            agent_run_id=1,
            system_prompt="Eres ObsyGPT.",
            provider_type="llamacpp",
            provider_base_url=None,
            provider_api_key_env=None,
            model="gemma",
            temperature=0.7,
            tool_specs=build_tool_catalog([("read_file", "Lee un fichero", "safe")]),
            messages=[ChatMessage(role="user", content="lee el readme")],
            max_iterations=8,
            on_activity=activities.append,
        )
    )

    kinds = [(item["kind"], item.get("phase")) for item in activities]
    assert ("iteration", None) in kinds
    assert ("thinking", None) in kinds
    assert ("tool", "start") in kinds
    assert ("tool", "done") in kinds
    response_events = [item for item in activities if item["kind"] == "response"]
    assert response_events and response_events[0]["chars"] > 0
    assert kinds.index(("tool", "start")) < kinds.index(("tool", "done"))
    assert kinds.count(("iteration", None)) == 2


def test_loop_executes_tool_then_finishes():
    provider, traces, executor_calls, output = run_loop(
        [tool_block("read_file", '{"path": "README.md"}'), "He leido el fichero."],
    )

    assert output == "He leido el fichero."
    assert executor_calls == [("read_file", {"path": "README.md"})]
    assert traces.tool_calls[0][1] == "read_file"
    second_request_messages = provider.requests[1].messages
    assert any("resultado de read_file" in message.content for message in second_request_messages)


def test_loop_executes_multiple_xml_tool_calls_in_one_response():
    from app.agent.protocol import parse_model_output  # noqa: F401 - sanity import

    provider = FakeProviderRegistry(
        [
            (
                "<tool_call>read_file\n<arg_key>path</arg_key>\n<arg_value>README.md</arg_value>\n</tool_call>\n"
                "<tool_call>read_file\n<arg_key>path</arg_key>\n<arg_value>NOTES.md</arg_value>\n</tool_call>"
            ),
            "He leido ambos ficheros.",
        ],
    )
    traces = FakeTraceStore()
    executor_calls: list[tuple] = []

    def executor(name, args):
        from app.agent.tools.base import ToolResult

        executor_calls.append((name, args))
        return ToolResult(ok=True, output=f"resultado de {name} {args['path']}")

    loop = AgentLoop(provider_registry=provider, trace_store=traces, execute_tool=executor)
    chunks = list(
        loop.run(
            agent_run_id=1,
            system_prompt="Eres ObsyGPT.",
            provider_type="llamacpp",
            provider_base_url=None,
            provider_api_key_env=None,
            model="gemma",
            temperature=0.7,
            tool_specs=build_tool_catalog([("read_file", "Lee un fichero", "safe")]),
            messages=[ChatMessage(role="user", content="lee el readme y las notas")],
            max_iterations=8,
        )
    )
    output = "".join(chunks)

    assert output == "He leido ambos ficheros."
    assert executor_calls == [("read_file", {"path": "README.md"}), ("read_file", {"path": "NOTES.md"})]
    second_request_messages = provider.requests[1].messages
    assert any("resultado de read_file README.md" in message.content for message in second_request_messages)
    assert any("resultado de read_file NOTES.md" in message.content for message in second_request_messages)


def test_loop_feeds_error_for_unknown_tool():
    provider, _, _, output = run_loop(
        [tool_block("no_existe", "{}"), "Recuperado."],
    )

    assert output == "Recuperado."
    second_request_messages = provider.requests[1].messages
    assert any("Unknown tool" in message.content for message in second_request_messages)


def test_loop_recovers_from_malformed_tool_block():
    provider, _, executor_calls, output = run_loop(
        [
            PROTOCOL_MARKER_OPEN + "\n{tool: mal formado}\n" + PROTOCOL_MARKER_CLOSE,
            tool_block("read_file", '{"path": "a.txt"}'),
            "Listo.",
        ],
    )

    assert output == "Listo."
    assert executor_calls == [("read_file", {"path": "a.txt"})]
    second_request_messages = provider.requests[1].messages
    assert any("Invalid JSON" in message.content for message in second_request_messages)


def test_loop_stops_cleanly_on_iteration_guardrail():
    provider, _, _, output = run_loop(
        [tool_block("read_file", '{"path": "a.txt"}')] * 3,
        max_iterations=2,
    )

    assert "guardrail" in output.lower()
    assert "iterations" in output.lower()
    assert len(provider.requests) == 2


def test_loop_streams_thought_text_before_tool_call():
    activities: list[dict] = []
    provider, _, _, output = run_loop(
        ["Voy a leerlo. " + tool_block("read_file", '{"path": "a.txt"}'), "Hecho."],
        activities=activities,
    )

    # Reasoning travels through the activity channel (ChatGPT/Claude style),
    # never as answer text.
    assert "Voy a leerlo." not in output
    assert "Hecho." in output
    thoughts = [activity for activity in activities if activity.get("kind") == "thought"]
    assert any("Voy a leerlo." in activity.get("text", "") for activity in thoughts)


def test_system_prompt_includes_catalog_and_protocol():
    provider, _, _, _ = run_loop(["ok"])

    system = provider.requests[0].messages[0].content
    assert "read_file" in system
    assert PROTOCOL_MARKER_OPEN in system
    assert "Eres ObsyGPT." in system


def test_loop_pauses_on_approval_required_and_reports_it():
    provider = FakeProviderRegistry(["Pensando. " + tool_block("read_file", '{"path": "a.txt"}'), "no llega"])
    snapshots: list[list[ChatMessage]] = []

    def executor(name, args):
        raise ApprovalRequiredError(approval_id=7, tool_name=name, args=args)

    loop = AgentLoop(provider_registry=provider, trace_store=FakeTraceStore(), execute_tool=executor)
    generator = loop.run(
        agent_run_id=1,
        system_prompt="s",
        provider_type="llamacpp",
        provider_base_url=None,
        provider_api_key_env=None,
        model="m",
        temperature=0.7,
        tool_specs=build_tool_catalog([("read_file", "lee", "safe")]),
        messages=[ChatMessage(role="user", content="lee")],
        max_iterations=5,
        on_before_tool=lambda name, args, conversation: snapshots.append(list(conversation)),
    )

    chunks = []
    with pytest.raises(ApprovalRequiredError) as error:
        for chunk in generator:
            chunks.append(chunk)

    assert error.value.approval_id == 7
    assert "".join(chunks) == ""  # reasoning is no longer part of the answer stream
    assert len(snapshots) == 1
    assert snapshots[0][-1].role == "assistant"
    assert PROTOCOL_MARKER_OPEN in snapshots[0][-1].content
