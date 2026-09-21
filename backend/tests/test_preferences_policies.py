import pytest
from fastapi import HTTPException

from app.agent.tools.base import ToolResult
from app.chat.routes import build_approval_aware_executor
from app.workspace import routes as workspace_routes


class FakeRequest:
    session = {"user_id": 2, "role": "user"}


class FakeSpec:
    def __init__(self, permission):
        self.permission = permission


class FakeTool:
    def __init__(self, permission):
        self.spec = FakeSpec(permission)

    def run(self, args):
        return ToolResult(ok=True, output="ejecutado")


class FakeRegistry:
    def __init__(self):
        self.calls = []

    def get(self, name):
        return FakeTool("sensitive" if name == "run_command" else "safe")

    def run(self, name, args):
        self.calls.append((name, args))
        return ToolResult(ok=True, output="ejecutado")


def patch_preferences(monkeypatch, policies):
    monkeypatch.setattr(
        "app.chat.routes.get_user_preferences",
        lambda user_id: {"display_name": "", "accent": "gold", "memory_max": 30, "tool_policies": policies},
    )


def test_executor_blocks_tool_when_policy_block(monkeypatch):
    patch_preferences(monkeypatch, {"web_fetch": "block"})
    registry = FakeRegistry()

    executor = build_approval_aware_executor(2, 1, 1, registry)
    result = executor("web_fetch", {"url": "https://x"})

    assert result.ok is False
    assert "blocked" in result.output.lower()
    assert registry.calls == []


def test_executor_runs_sensitive_without_approval_when_policy_allow(monkeypatch):
    from app.agent.errors import ApprovalRequiredError

    patch_preferences(monkeypatch, {"run_command": "allow"})
    registry = FakeRegistry()

    executor = build_approval_aware_executor(2, 1, 1, registry)
    result = executor("run_command", {"command": "dir"})

    assert result.ok is True
    assert registry.calls == [("run_command", {"command": "dir"})]


def test_executor_asks_for_sensitive_by_default(monkeypatch):
    from app.agent.errors import ApprovalRequiredError

    patch_preferences(monkeypatch, {})
    monkeypatch.setattr("app.chat.routes.create_tool_approval", lambda *args, **kwargs: 11)

    executor = build_approval_aware_executor(2, 1, 1, FakeRegistry())

    with pytest.raises(ApprovalRequiredError):
        executor("run_command", {"command": "dir"})


def test_executor_runs_safe_tools_directly(monkeypatch):
    patch_preferences(monkeypatch, {})
    registry = FakeRegistry()

    executor = build_approval_aware_executor(2, 1, 1, registry)
    result = executor("read_file", {"path": "a.txt"})

    assert result.ok is True
    assert registry.calls == [("read_file", {"path": "a.txt"})]


def test_write_preferences_rejects_bad_values():
    with pytest.raises(HTTPException) as error:
        workspace_routes.write_preferences(workspace_routes.PreferencesPayload(memory_max=500), FakeRequest())
    assert error.value.status_code == 400

    with pytest.raises(HTTPException) as error:
        workspace_routes.write_preferences(workspace_routes.PreferencesPayload(accent="naranja"), FakeRequest())
    assert error.value.status_code == 400


def test_write_preferences_merges_and_persists(monkeypatch):
    stored = {}
    monkeypatch.setattr(workspace_routes, "get_user_setting", lambda user_id, key: stored.get(key))
    monkeypatch.setattr(
        workspace_routes,
        "set_user_setting",
        lambda user_id, key, value: stored.update({key: value}),
    )

    result = workspace_routes.write_preferences(workspace_routes.PreferencesPayload(display_name="Juanjo"), FakeRequest())

    assert result["preferences"]["display_name"] == "Juanjo"
    assert result["preferences"]["accent"] == "gold"
    assert stored["preferences"]["display_name"] == "Juanjo"


def test_write_preferences_instructions_roundtrip_and_limit(monkeypatch):
    stored = {}
    monkeypatch.setattr(workspace_routes, "get_user_setting", lambda user_id, key: stored.get(key))
    monkeypatch.setattr(
        workspace_routes,
        "set_user_setting",
        lambda user_id, key, value: stored.update({key: value}),
    )

    result = workspace_routes.write_preferences(
        workspace_routes.PreferencesPayload(instructions="  Responde en espanol, breve.  "), FakeRequest()
    )
    assert result["preferences"]["instructions"] == "Responde en espanol, breve."

    with pytest.raises(HTTPException) as error:
        workspace_routes.write_preferences(
            workspace_routes.PreferencesPayload(instructions="x" * (workspace_routes.MAX_INSTRUCTIONS_CHARS + 1)), FakeRequest()
        )
    assert error.value.status_code == 400


def test_build_user_instructions_block(monkeypatch):
    from app.memory.context import build_user_instructions_block

    monkeypatch.setattr(
        "app.workspace.routes.get_user_preferences",
        lambda user_id: {"instructions": "  Sé breve.  "},
    )
    block = build_user_instructions_block(2)
    assert "INSTRUCCIONES PERSONALES" in block
    assert block.endswith("Sé breve.")

    monkeypatch.setattr(
        "app.workspace.routes.get_user_preferences",
        lambda user_id: {"instructions": "   "},
    )
    assert build_user_instructions_block(2) == ""
