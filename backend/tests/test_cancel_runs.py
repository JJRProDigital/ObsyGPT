"""Tests for user-cancelled runs (double-Esc): interrupt_run + GeneratorExit handling."""

import pytest

from app.chat import streaming as chat_streaming
from app.traces import store as traces_store


class FakeCursor:
    def __init__(self, store):
        self.store = store

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc, traceback):
        return False

    def execute(self, query, params=()):
        self.store["queries"].append((query.strip(), params))


class FakeConnection:
    def __init__(self, store):
        self.store = store

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc, traceback):
        return False

    def cursor(self):
        return FakeCursor(self.store)


def test_interrupt_run_marks_cancelled(monkeypatch):
    store = {"queries": []}
    monkeypatch.setattr(traces_store, "connect", lambda: FakeConnection(store))
    traces_store.TraceStore().interrupt_run(9, "respuesta parcial")
    query, params = store["queries"][-1]
    assert "SET status = 'interrupted'" in query
    assert params[0] == "respuesta parcial"
    assert params[2] == 9


def test_stream_agentic_handles_generator_exit(monkeypatch):
    recorded: dict = {}

    class FakeTrace:
        def add_event(self, *a, **k):
            pass

        def interrupt_run(self, run_id, partial):
            recorded["run_id"] = run_id
            recorded["partial"] = partial

        def fail_run(self, *a, **k):
            recorded["failed"] = True

    def fake_drive(start_loop):
        yield "token", "respuesta par"
        raise GeneratorExit

    monkeypatch.setattr(chat_streaming.chat_activity, "drive_agent_loop", fake_drive)

    agent = type(
        "Agent",
        (),
        {
            "id": 1, "system_prompt": "x", "provider_type": "openai_compatible", "provider_base_url": "http://x",
            "provider_api_key_env": None, "provider_api_key": "k", "model": "m", "temperature": 0.7,
            "fallbacks": [], "agentic_mode": True,
        },
    )()

    class FakeRegistry:
        def register(self, tool):
            pass

        def list_specs(self):
            return []

    monkeypatch.setattr(chat_streaming.chat_specs, "build_agent_tool_registry", lambda **k: FakeRegistry())
    monkeypatch.setattr(chat_streaming.chat_specs, "get_agent_tool_specs", lambda *a, **k: [])
    monkeypatch.setattr(chat_streaming.chat_approvals, "build_approval_aware_executor", lambda *a, **k: (lambda name, args: None))
    monkeypatch.setattr(chat_streaming, "load_guardrail_config", lambda: {})
    monkeypatch.setattr(chat_streaming.chat_conversations, "save_message", lambda *a, **k: recorded.update({"saved": True}))

    captured = {}

    class FakeStreamingResponse:
        def __init__(self, generator, **kwargs):
            captured["gen"] = generator

    monkeypatch.setattr(chat_streaming, "StreamingResponse", FakeStreamingResponse)

    response = chat_streaming.stream_agentic(1, 5, 42, agent, [], FakeTrace(), user_message="hola")
    generator = captured["gen"]
    first = next(generator)
    assert "respuesta par" in first

    generator.close()  # raises GeneratorExit at the yield: simulates client disconnect

    assert recorded["run_id"] == 42
    assert recorded["partial"] == "respuesta par"
    assert recorded.get("saved") is True
    assert "failed" not in recorded
