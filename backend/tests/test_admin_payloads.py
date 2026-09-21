import json

from pydantic import ValidationError
import pytest
from fastapi import HTTPException

from app.admin.routes import AgentPayload, AgentToolsPayload, GuardrailSettingsPayload, McpRunPayload, McpServerPayload, ModelPayload, ProviderPayload, SkillGeneratePayload, SkillPayload, SkillRunPayload, UserRolePayload, WorkflowPayload, assign_agent_mcp, assign_agent_skill, build_skill_draft, check_model_config, create_agent, create_mcp_server, create_model, create_provider, create_skill, create_workflow, delete_mcp_server, delete_skill, diagnostics, ensure_admin_role_change_allowed, ensure_positive_id, generate_skill, inspect_mcp_server, list_audit_logs, list_guardrail_settings, remove_agent_mcp, remove_agent_skill, render_skill_md, resource_paths, run_mcp_server, set_agent_tools, update_guardrail_settings, update_mcp_server, update_skill, write_skill_files, delete_skill_files, update_user_role, update_workflow, validate_mcp_server


class FakeRequest:
    session = {"user_id": 1, "role": "admin"}


def _fake_trace_store_factory():
    return lambda: type(
        "FakeTraceStore",
        (),
        {
            "add_tool_call": lambda self, *args, **kwargs: None,
            "add_mcp_call": lambda self, *args, **kwargs: None,
        },
    )()


def test_provider_payload_accepts_openai_compatible_provider():
    payload = ProviderPayload(
        name="Local llama.cpp",
        provider_type="openai_compatible",
        base_url="http://127.0.0.1:8080/v1",
        api_key_env=None,
        enabled=True,
    )

    assert payload.provider_type == "openai_compatible"
    assert payload.base_url == "http://127.0.0.1:8080/v1"


def test_provider_payload_rejects_unknown_provider_type():
    with pytest.raises(ValidationError):
        ProviderPayload(name="Bad", provider_type="bad", enabled=True)


def test_create_provider_records_audit_log(monkeypatch):
    captured = {}
    monkeypatch.setattr("app.admin.routes.require_admin", lambda request: 1)
    monkeypatch.setattr(
        "app.admin.routes.execute_returning",
        lambda query, params: {"id": 10, "name": "OpenAI", "provider_type": "openai", "base_url": None, "api_key_env": "OPENAI_API_KEY", "enabled": True},
    )

    class FakeAuditStore:
        def add_log(self, actor_user_id, action, target_type, target_id, metadata):
            captured.update({"actor_user_id": actor_user_id, "action": action, "target_type": target_type, "target_id": target_id, "metadata": metadata})

    monkeypatch.setattr("app.admin.routes.AuditStore", FakeAuditStore)

    create_provider(ProviderPayload(name="OpenAI", provider_type="openai", api_key_env="OPENAI_API_KEY", enabled=True), FakeRequest())

    assert captured == {
        "actor_user_id": 1,
        "action": "provider.created",
        "target_type": "provider",
        "target_id": 10,
        "metadata": {"name": "OpenAI", "provider_type": "openai", "enabled": True},
    }


def test_model_payload_accepts_capability_flags():
    payload = ModelPayload(
        provider_id=1,
        model_name="gpt-4.1-mini",
        display_name="GPT-4.1 Mini",
        supports_text=True,
        supports_streaming=True,
        supports_vision=True,
        supports_audio=False,
        supports_tools=True,
        supports_json=True,
        context_window=1047576,
        enabled=True,
    )

    assert payload.model_name == "gpt-4.1-mini"
    assert payload.context_window == 1047576


def test_create_model_records_audit_log(monkeypatch):
    captured = {}
    monkeypatch.setattr("app.admin.routes.require_admin", lambda request: 1)
    monkeypatch.setattr(
        "app.admin.routes.execute_returning",
        lambda query, params: {"id": 12, "provider_id": 1, "model_name": "gpt-test", "display_name": "GPT Test", "enabled": True},
    )

    class FakeAuditStore:
        def add_log(self, actor_user_id, action, target_type, target_id, metadata):
            captured.update({"actor_user_id": actor_user_id, "action": action, "target_type": target_type, "target_id": target_id, "metadata": metadata})

    monkeypatch.setattr("app.admin.routes.AuditStore", FakeAuditStore)
    payload = ModelPayload(provider_id=1, model_name="gpt-test", display_name="GPT Test", enabled=True)

    create_model(payload, FakeRequest())

    assert captured == {
        "actor_user_id": 1,
        "action": "model.created",
        "target_type": "model",
        "target_id": 12,
        "metadata": {"model_name": "gpt-test", "provider_id": 1, "enabled": True},
    }


def test_model_payload_rejects_missing_name_or_invalid_context_window():
    with pytest.raises(ValidationError):
        ModelPayload(provider_id=1, model_name="", display_name="Model")

    with pytest.raises(ValidationError):
        ModelPayload(provider_id=1, model_name="model", display_name="Model", context_window=0)


def test_check_model_config_returns_provider_and_model_status(monkeypatch):
    monkeypatch.setattr("app.admin.routes.require_admin", lambda request: 1)
    monkeypatch.setenv("OPENAI_API_KEY", "secret")
    monkeypatch.setattr(
        "app.admin.routes.fetch_one",
        lambda query, params: {
            "id": 2,
            "model_name": "gpt-test",
            "display_name": "GPT Test",
            "enabled": True,
            "provider_id": 1,
            "provider_name": "OpenAI",
            "provider_type": "openai",
            "api_key_env": "OPENAI_API_KEY",
            "provider_enabled": True,
        },
    )

    result = check_model_config(2, FakeRequest())

    assert result == {
        "model_id": 2,
        "model_name": "gpt-test",
        "provider": "OpenAI",
        "provider_type": "openai",
        "enabled": True,
        "provider_enabled": True,
        "api_key_env": "OPENAI_API_KEY",
        "api_key_configured": True,
        "ready": True,
    }


def test_diagnostics_returns_counts_and_readiness(monkeypatch):
    monkeypatch.setattr("app.admin.routes.require_admin", lambda request: 1)

    def fake_fetch_one(query, params=()):
        if "COUNT(*) AS users" in query:
            return {"users": 2, "agents": 3, "workflows": 4, "mcp_servers": 1}
        return None

    def fake_fetch_all(query, params=()):
        return [
            {"id": 1, "name": "OpenAI", "provider_type": "openai", "enabled": True, "api_key_env": "OPENAI_API_KEY", "configured_models": 1},
            {"id": 2, "name": "Local", "provider_type": "ollama", "enabled": False, "api_key_env": None, "configured_models": 0},
        ]

    monkeypatch.setenv("OPENAI_API_KEY", "secret")
    monkeypatch.setattr("app.admin.routes.fetch_one", fake_fetch_one)
    monkeypatch.setattr("app.admin.routes.fetch_all", fake_fetch_all)

    result = diagnostics(FakeRequest())

    assert result["counts"] == {"users": 2, "agents": 3, "workflows": 4, "mcp_servers": 1}
    assert result["providers"][0]["api_key_configured"] is True
    assert result["providers"][0]["ready"] is True
    assert result["providers"][1]["ready"] is False


def test_list_audit_logs_returns_recent_logs(monkeypatch):
    monkeypatch.setattr("app.admin.routes.require_admin", lambda request: 1)
    captured = {}

    def fake_fetch_all(query, params=()):
        captured["params"] = params
        return [
            {
                "id": 1,
                "actor_user_id": 1,
                "actor_username": "admin",
                "action": "user.role_updated",
                "target_type": "user",
                "target_id": 2,
                "metadata": {"next_role": "admin"},
                "created_at": "created",
            }
        ]

    monkeypatch.setattr(
        "app.admin.routes.fetch_all",
        fake_fetch_all,
    )

    result = list_audit_logs(FakeRequest())

    assert result["audit_logs"][0]["action"] == "user.role_updated"
    assert result["audit_logs"][0]["actor_username"] == "admin"
    assert captured["params"] == (100,)


def test_list_audit_logs_accepts_custom_limit(monkeypatch):
    monkeypatch.setattr("app.admin.routes.require_admin", lambda request: 1)
    captured = {}

    def fake_fetch_all(query, params=()):
        captured["params"] = params
        return []

    monkeypatch.setattr("app.admin.routes.fetch_all", fake_fetch_all)

    result = list_audit_logs(FakeRequest(), limit=25)

    assert result == {"audit_logs": []}
    assert captured["params"] == (25,)


def test_list_audit_logs_accepts_action_and_target_filters(monkeypatch):
    monkeypatch.setattr("app.admin.routes.require_admin", lambda request: 1)
    captured = {}

    def fake_fetch_all(query, params=()):
        captured["query"] = query
        captured["params"] = params
        return []

    monkeypatch.setattr("app.admin.routes.fetch_all", fake_fetch_all)

    result = list_audit_logs(FakeRequest(), limit=10, action="agent.updated", target_type="agent")

    assert result == {"audit_logs": []}
    assert "a.action = %s" in captured["query"]
    assert "a.target_type = %s" in captured["query"]
    assert captured["params"] == ("agent.updated", "agent", 10)


def test_agent_payload_requires_system_prompt():
    with pytest.raises(ValidationError):
        AgentPayload(
            name="Researcher",
            description="Finds sources",
            system_prompt="",
            provider_id=1,
            model_id=1,
            temperature=0.7,
            internet_enabled=True,
            multimodal_enabled=False,
            enabled=True,
        )


def test_create_agent_records_audit_log(monkeypatch):
    captured = {}
    monkeypatch.setattr("app.admin.routes.require_admin", lambda request: 1)
    monkeypatch.setattr(
        "app.admin.routes.execute_returning",
        lambda query, params: {"id": 20, "name": "Researcher", "internet_enabled": True, "multimodal_enabled": False, "enabled": True},
    )

    class FakeAuditStore:
        def add_log(self, actor_user_id, action, target_type, target_id, metadata):
            captured.update({"actor_user_id": actor_user_id, "action": action, "target_type": target_type, "target_id": target_id, "metadata": metadata})

    monkeypatch.setattr("app.admin.routes.AuditStore", FakeAuditStore)
    payload = AgentPayload(name="Researcher", description="", system_prompt="Research.", internet_enabled=True, multimodal_enabled=False, enabled=True)

    create_agent(payload, FakeRequest())

    assert captured == {
        "actor_user_id": 1,
        "action": "agent.created",
        "target_type": "agent",
        "target_id": 20,
        "metadata": {"name": "Researcher", "internet_enabled": True, "multimodal_enabled": False, "enabled": True},
    }


def test_assign_agent_skill_records_audit_log(monkeypatch):
    captured = {}
    monkeypatch.setattr("app.admin.routes.require_admin", lambda request: 1)
    monkeypatch.setattr("app.admin.routes.execute_returning", lambda query, params: {"agent_id": params[0], "skill_id": params[1]})

    class FakeAuditStore:
        def add_log(self, actor_user_id, action, target_type, target_id, metadata):
            captured.update({"actor_user_id": actor_user_id, "action": action, "target_type": target_type, "target_id": target_id, "metadata": metadata})

    monkeypatch.setattr("app.admin.routes.AuditStore", FakeAuditStore)

    assign_agent_skill(2, 3, FakeRequest())

    assert captured == {
        "actor_user_id": 1,
        "action": "agent_skill.assigned",
        "target_type": "agent",
        "target_id": 2,
        "metadata": {"skill_id": 3},
    }


def test_assign_agent_mcp_records_audit_log(monkeypatch):
    captured = {}
    monkeypatch.setattr("app.admin.routes.require_admin", lambda request: 1)
    monkeypatch.setattr("app.admin.routes.execute_returning", lambda query, params: {"agent_id": params[0], "mcp_server_id": params[1]})

    class FakeAuditStore:
        def add_log(self, actor_user_id, action, target_type, target_id, metadata):
            captured.update({"actor_user_id": actor_user_id, "action": action, "target_type": target_type, "target_id": target_id, "metadata": metadata})

    monkeypatch.setattr("app.admin.routes.AuditStore", FakeAuditStore)

    assign_agent_mcp(2, 4, FakeRequest())

    assert captured == {
        "actor_user_id": 1,
        "action": "agent_mcp.assigned",
        "target_type": "agent",
        "target_id": 2,
        "metadata": {"mcp_server_id": 4},
    }


def test_remove_agent_skill_records_audit_log(monkeypatch):
    captured = {}
    monkeypatch.setattr("app.admin.routes.require_admin", lambda request: 1)

    class FakeCursor:
        def __enter__(self):
            return self

        def __exit__(self, exc_type, exc, traceback):
            return False

        def execute(self, query, params=()):
            pass

    class FakeConnection:
        def __enter__(self):
            return self

        def __exit__(self, exc_type, exc, traceback):
            return False

        def cursor(self):
            return FakeCursor()

    class FakeAuditStore:
        def add_log(self, actor_user_id, action, target_type, target_id, metadata):
            captured.update({"actor_user_id": actor_user_id, "action": action, "target_type": target_type, "target_id": target_id, "metadata": metadata})

    monkeypatch.setattr("app.admin.routes.connect", lambda: FakeConnection())
    monkeypatch.setattr("app.admin.routes.AuditStore", FakeAuditStore)

    remove_agent_skill(2, 3, FakeRequest())

    assert captured == {
        "actor_user_id": 1,
        "action": "agent_skill.removed",
        "target_type": "agent",
        "target_id": 2,
        "metadata": {"skill_id": 3},
    }


def test_remove_agent_mcp_records_audit_log(monkeypatch):
    captured = {}
    monkeypatch.setattr("app.admin.routes.require_admin", lambda request: 1)

    class FakeCursor:
        def __enter__(self):
            return self

        def __exit__(self, exc_type, exc, traceback):
            return False

        def execute(self, query, params=()):
            pass

    class FakeConnection:
        def __enter__(self):
            return self

        def __exit__(self, exc_type, exc, traceback):
            return False

        def cursor(self):
            return FakeCursor()

    class FakeAuditStore:
        def add_log(self, actor_user_id, action, target_type, target_id, metadata):
            captured.update({"actor_user_id": actor_user_id, "action": action, "target_type": target_type, "target_id": target_id, "metadata": metadata})

    monkeypatch.setattr("app.admin.routes.connect", lambda: FakeConnection())
    monkeypatch.setattr("app.admin.routes.AuditStore", FakeAuditStore)

    remove_agent_mcp(2, 4, FakeRequest())

    assert captured == {
        "actor_user_id": 1,
        "action": "agent_mcp.removed",
        "target_type": "agent",
        "target_id": 2,
        "metadata": {"mcp_server_id": 4},
    }


def test_mcp_payload_requires_command_or_url_matching_connection_type():
    command_payload = McpServerPayload(
        name="Filesystem",
        description="Local filesystem MCP",
        connection_type="command",
        command="npx -y @modelcontextprotocol/server-filesystem .",
        url=None,
        enabled=False,
    )

    assert command_payload.command.startswith("npx")

    with pytest.raises(ValidationError):
        McpServerPayload(
            name="Broken",
            description="Missing URL",
            connection_type="url",
            command=None,
            url=None,
            enabled=False,
        )


def test_create_mcp_server_records_audit_log(monkeypatch):
    captured = {}
    monkeypatch.setattr("app.admin.routes.require_admin", lambda request: 1)
    monkeypatch.setattr(
        "app.admin.routes.execute_returning",
        lambda query, params: {"id": 40, "name": "Filesystem", "connection_type": "command", "enabled": False},
    )

    class FakeAuditStore:
        def add_log(self, actor_user_id, action, target_type, target_id, metadata):
            captured.update({"actor_user_id": actor_user_id, "action": action, "target_type": target_type, "target_id": target_id, "metadata": metadata})

    monkeypatch.setattr("app.admin.routes.AuditStore", FakeAuditStore)
    payload = McpServerPayload(
        name="Filesystem",
        description="Local files",
        connection_type="command",
        command="npx server",
        url=None,
        enabled=False,
    )

    create_mcp_server(payload, FakeRequest())

    assert captured == {
        "actor_user_id": 1,
        "action": "mcp_server.created",
        "target_type": "mcp_server",
        "target_id": 40,
        "metadata": {"name": "Filesystem", "connection_type": "command", "enabled": False},
    }


def test_validate_mcp_server_returns_non_executing_validation(monkeypatch):
    monkeypatch.setattr("app.admin.routes.require_admin", lambda request: 1)
    payload = McpServerPayload(
        name="Filesystem",
        description="Local files",
        connection_type="command",
        command='npx -y "@modelcontextprotocol/server-filesystem" .',
        url=None,
        enabled=False,
    )

    result = validate_mcp_server(payload, FakeRequest())

    assert result["validation"]["command_args"] == ["npx", "-y", "@modelcontextprotocol/server-filesystem", "."]


def test_mcp_run_payload_requires_method():
    payload = McpRunPayload(method="tools/list", params={})

    assert payload.method == "tools/list"

    with pytest.raises(ValidationError):
        McpRunPayload(method="", params={})


def test_run_mcp_server_invokes_command_server(monkeypatch):
    monkeypatch.setattr("app.admin.routes.require_admin", lambda request: 1)
    monkeypatch.setattr("app.admin.routes.AuditStore", lambda: type("FakeAuditStore", (), {"add_log": lambda self, *args, **kwargs: None})())
    monkeypatch.setattr("app.admin.routes.TraceStore", _fake_trace_store_factory())
    monkeypatch.setattr(
        "app.admin.routes.fetch_one",
        lambda query, params: {
            "id": 7,
            "name": "filesystem",
            "description": "Local files",
            "connection_type": "command",
            "command": "node server.js",
            "url": None,
            "enabled": True,
        },
    )
    monkeypatch.setattr("app.admin.routes.McpGateway.call_command", lambda self, command, method, params: {"result": {"tools": []}})

    result = run_mcp_server(7, McpRunPayload(method="tools/list", params={}), FakeRequest())

    assert result == {"mcp_server_id": 7, "response": {"result": {"tools": []}}}


def test_run_mcp_server_invokes_url_server(monkeypatch):
    monkeypatch.setattr("app.admin.routes.require_admin", lambda request: 1)
    monkeypatch.setattr("app.admin.routes.AuditStore", lambda: type("FakeAuditStore", (), {"add_log": lambda self, *args, **kwargs: None})())
    monkeypatch.setattr("app.admin.routes.TraceStore", _fake_trace_store_factory())
    monkeypatch.setattr(
        "app.admin.routes.fetch_one",
        lambda query, params: {
            "id": 8,
            "name": "remote",
            "description": "Remote MCP",
            "connection_type": "url",
            "command": None,
            "url": "https://mcp.example.com",
            "enabled": True,
        },
    )
    monkeypatch.setattr("app.admin.routes.McpGateway.call_url", lambda self, url, method, params: {"result": {"tools": []}})

    result = run_mcp_server(8, McpRunPayload(method="tools/list", params={}), FakeRequest())

    assert result == {"mcp_server_id": 8, "response": {"result": {"tools": []}}}


def test_run_mcp_server_records_audit_log(monkeypatch):
    captured = {}
    monkeypatch.setattr("app.admin.routes.require_admin", lambda request: 1)
    monkeypatch.setattr(
        "app.admin.routes.fetch_one",
        lambda query, params: {
            "id": 7,
            "name": "filesystem",
            "description": "Local files",
            "connection_type": "command",
            "command": "node server.js",
            "url": None,
            "enabled": True,
        },
    )
    monkeypatch.setattr("app.admin.routes.McpGateway.call_command", lambda self, command, method, params: {"result": {"tools": []}})
    monkeypatch.setattr("app.admin.routes.TraceStore", _fake_trace_store_factory())

    class FakeAuditStore:
        def add_log(self, actor_user_id, action, target_type, target_id, metadata):
            captured.update({"actor_user_id": actor_user_id, "action": action, "target_type": target_type, "target_id": target_id, "metadata": metadata})

    monkeypatch.setattr("app.admin.routes.AuditStore", FakeAuditStore)

    run_mcp_server(7, McpRunPayload(method="tools/list", params={"secret": "redacted"}), FakeRequest())

    assert captured == {
        "actor_user_id": 1,
        "action": "mcp_server.run.completed",
        "target_type": "mcp_server",
        "target_id": 7,
        "metadata": {"name": "filesystem", "method": "tools/list", "connection_type": "command"},
    }


def test_run_mcp_server_records_tool_call_when_agent_run_is_provided(monkeypatch):
    captured = {}
    monkeypatch.setattr("app.admin.routes.require_admin", lambda request: 1)
    monkeypatch.setattr("app.admin.routes.AuditStore", lambda: type("FakeAuditStore", (), {"add_log": lambda self, *args, **kwargs: None})())
    monkeypatch.setattr(
        "app.admin.routes.fetch_one",
        lambda query, params: {
            "id": 7,
            "name": "filesystem",
            "description": "Local files",
            "connection_type": "command",
            "command": "node server.js",
            "url": None,
            "enabled": True,
        },
    )
    monkeypatch.setattr("app.admin.routes.McpGateway.call_command", lambda self, command, method, params: {"result": {"tools": []}})

    class FakeTraceStore:
        def add_tool_call(self, agent_run_id, skill_name, input_summary, output_summary, status):
            captured.update(
                {
                    "agent_run_id": agent_run_id,
                    "skill_name": skill_name,
                    "input_summary": input_summary,
                    "output_summary": output_summary,
                    "status": status,
                }
            )

        def add_mcp_call(self, *args, **kwargs):
            pass

    monkeypatch.setattr("app.admin.routes.TraceStore", FakeTraceStore)

    run_mcp_server(7, McpRunPayload(method="tools/list", params={}, agent_run_id=42), FakeRequest())

    assert captured["agent_run_id"] == 42
    assert captured["skill_name"] == "mcp:filesystem"
    assert captured["status"] == "completed"


def test_run_mcp_server_records_failed_tool_call_when_execution_fails(monkeypatch):
    captured = {}
    monkeypatch.setattr("app.admin.routes.require_admin", lambda request: 1)
    monkeypatch.setattr("app.admin.routes.AuditStore", lambda: type("FakeAuditStore", (), {"add_log": lambda self, *args, **kwargs: None})())
    monkeypatch.setattr(
        "app.admin.routes.fetch_one",
        lambda query, params: {
            "id": 7,
            "name": "filesystem",
            "description": "Local files",
            "connection_type": "command",
            "command": "node server.js",
            "url": None,
            "enabled": True,
        },
    )

    def fail_command(self, command, method, params):
        raise RuntimeError("MCP command failed: boom")

    monkeypatch.setattr("app.admin.routes.McpGateway.call_command", fail_command)

    class FakeTraceStore:
        def add_tool_call(self, agent_run_id, skill_name, input_summary, output_summary, status):
            captured.update(
                {
                    "agent_run_id": agent_run_id,
                    "skill_name": skill_name,
                    "input_summary": input_summary,
                    "output_summary": output_summary,
                    "status": status,
                }
            )

        def add_mcp_call(self, *args, **kwargs):
            pass

    monkeypatch.setattr("app.admin.routes.TraceStore", FakeTraceStore)

    with pytest.raises(HTTPException) as error:
        run_mcp_server(7, McpRunPayload(method="tools/list", params={}, agent_run_id=42), FakeRequest())

    assert error.value.status_code == 502
    assert captured["status"] == "failed"
    assert captured["output_summary"] == "MCP command failed: boom"


def test_run_mcp_server_records_failed_audit_log(monkeypatch):
    captured = {}
    monkeypatch.setattr("app.admin.routes.require_admin", lambda request: 1)
    monkeypatch.setattr(
        "app.admin.routes.fetch_one",
        lambda query, params: {
            "id": 7,
            "name": "filesystem",
            "description": "Local files",
            "connection_type": "command",
            "command": "node server.js",
            "url": None,
            "enabled": True,
        },
    )

    def fail_command(self, command, method, params):
        raise RuntimeError("MCP command failed: boom")

    class FakeAuditStore:
        def add_log(self, actor_user_id, action, target_type, target_id, metadata):
            captured.update({"actor_user_id": actor_user_id, "action": action, "target_type": target_type, "target_id": target_id, "metadata": metadata})

    monkeypatch.setattr("app.admin.routes.McpGateway.call_command", fail_command)
    monkeypatch.setattr("app.admin.routes.AuditStore", FakeAuditStore)
    monkeypatch.setattr("app.admin.routes.TraceStore", _fake_trace_store_factory())

    with pytest.raises(HTTPException):
        run_mcp_server(7, McpRunPayload(method="tools/list", params={}), FakeRequest())

    assert captured == {
        "actor_user_id": 1,
        "action": "mcp_server.run.failed",
        "target_type": "mcp_server",
        "target_id": 7,
        "metadata": {"name": "filesystem", "method": "tools/list", "connection_type": "command"},
    }


def test_run_mcp_server_records_mcp_call_without_agent_run(monkeypatch):
    captured = {}
    monkeypatch.setattr("app.admin.routes.require_admin", lambda request: 1)
    monkeypatch.setattr("app.admin.routes.AuditStore", lambda: type("FakeAuditStore", (), {"add_log": lambda self, *args, **kwargs: None})())
    monkeypatch.setattr(
        "app.admin.routes.fetch_one",
        lambda query, params: {
            "id": 7,
            "name": "filesystem",
            "description": "Local files",
            "connection_type": "command",
            "command": "node server.js",
            "url": None,
            "enabled": True,
        },
    )
    monkeypatch.setattr("app.admin.routes.McpGateway.call_command", lambda self, command, method, params: {"result": {"tools": []}})

    class FakeTraceStore:
        def add_tool_call(self, agent_run_id, skill_name, input_summary, output_summary, status):
            captured["tool_call"] = (agent_run_id, skill_name, status)

        def add_mcp_call(self, agent_run_id, mcp_server_id, tool_name, input_summary, output_summary, status):
            captured["mcp_call"] = (agent_run_id, mcp_server_id, tool_name, status)

    monkeypatch.setattr("app.admin.routes.TraceStore", FakeTraceStore)

    run_mcp_server(7, McpRunPayload(method="tools/list", params={}), FakeRequest())

    assert captured["mcp_call"] == (None, 7, "tools/list", "completed")
    assert "tool_call" not in captured


def test_delete_mcp_server_records_audit_log(monkeypatch):
    captured = {}
    monkeypatch.setattr("app.admin.routes.require_admin", lambda request: 1)
    monkeypatch.setattr(
        "app.admin.routes.execute_returning",
        lambda query, params: {"id": 7, "name": "filesystem"},
    )

    class FakeAuditStore:
        def add_log(self, actor_user_id, action, target_type, target_id, metadata):
            captured.update({"action": action, "target_type": target_type, "target_id": target_id, "metadata": metadata})

    monkeypatch.setattr("app.admin.routes.AuditStore", FakeAuditStore)

    result = delete_mcp_server(7, FakeRequest())

    assert result == {"id": 7, "deleted": True}
    assert captured["action"] == "mcp_server.deleted"
    assert captured["metadata"] == {"name": "filesystem"}


def test_inspect_mcp_server_returns_discovered_tools(monkeypatch):
    captured = {}
    monkeypatch.setattr("app.admin.routes.require_admin", lambda request: 1)
    monkeypatch.setattr(
        "app.admin.routes.fetch_one",
        lambda query, params: {"id": 7, "name": "filesystem", "connection_type": "command", "command": "node server.js", "url": None},
    )
    monkeypatch.setattr(
        "app.admin.routes.McpGateway.inspect_command",
        lambda self, command: {"server_info": {"name": "filesystem"}, "tools": [{"name": "read_file", "description": "Read a file"}]},
    )
    monkeypatch.setattr("app.admin.routes.AuditStore", lambda: type("FakeAuditStore", (), {"add_log": lambda self, *args, **kwargs: None})())

    result = inspect_mcp_server(7, FakeRequest())

    assert result["mcp_server_id"] == 7
    assert result["server_info"] == {"name": "filesystem"}
    assert result["tools"][0]["name"] == "read_file"


def test_inspect_mcp_server_maps_gateway_errors_to_502(monkeypatch):
    monkeypatch.setattr("app.admin.routes.require_admin", lambda request: 1)
    monkeypatch.setattr(
        "app.admin.routes.fetch_one",
        lambda query, params: {"id": 7, "name": "filesystem", "connection_type": "url", "command": None, "url": "https://mcp.example.com"},
    )

    def failing_inspect(self, url):
        raise RuntimeError("MCP server did not respond to initialize.")

    monkeypatch.setattr("app.admin.routes.McpGateway.inspect_url", failing_inspect)

    with pytest.raises(HTTPException) as error:
        inspect_mcp_server(7, FakeRequest())

    assert error.value.status_code == 502


def test_update_mcp_server_updates_existing_server(monkeypatch):
    monkeypatch.setattr("app.admin.routes.require_admin", lambda request: 1)
    monkeypatch.setattr("app.admin.routes.AuditStore", lambda: type("FakeAuditStore", (), {"add_log": lambda self, *args, **kwargs: None})())

    def fake_execute_returning(query, params):
        assert "UPDATE mcp_servers" in query
        assert params == ("Filesystem", "Local files", "command", "node server.js", None, True, 7)
        return {
            "id": 7,
            "name": "Filesystem",
            "description": "Local files",
            "connection_type": "command",
            "command": "node server.js",
            "url": None,
            "enabled": True,
        }

    monkeypatch.setattr("app.admin.routes.execute_returning", fake_execute_returning)
    payload = McpServerPayload(
        name="Filesystem",
        description="Local files",
        connection_type="command",
        command="node server.js",
        url=None,
        enabled=True,
    )

    result = update_mcp_server(7, payload, FakeRequest())

    assert result["mcp_server"]["enabled"] is True


def test_create_skill_records_audit_log(monkeypatch):
    captured = {}
    monkeypatch.setattr("app.admin.routes.require_admin", lambda request: 1)
    monkeypatch.setattr("app.admin.routes.write_skill_files", lambda skill, previous_name=None: None)
    monkeypatch.setattr(
        "app.admin.routes.execute_returning",
        lambda query, params: {"id": 50, "name": "summarize", "description": "Summarize text", "enabled": True},
    )

    class FakeAuditStore:
        def add_log(self, actor_user_id, action, target_type, target_id, metadata):
            captured.update({"actor_user_id": actor_user_id, "action": action, "target_type": target_type, "target_id": target_id, "metadata": metadata})

    monkeypatch.setattr("app.admin.routes.AuditStore", FakeAuditStore)

    create_skill(SkillPayload(name="summarize", description="Summarize text", enabled=True), FakeRequest())

    assert captured == {
        "actor_user_id": 1,
        "action": "skill.created",
        "target_type": "skill",
        "target_id": 50,
        "metadata": {"name": "summarize", "enabled": True},
    }


def test_update_skill_records_audit_log(monkeypatch):
    captured = {}
    monkeypatch.setattr("app.admin.routes.require_admin", lambda request: 1)
    monkeypatch.setattr("app.admin.routes.fetch_one", lambda query, params: {"name": "summarize"})
    monkeypatch.setattr("app.admin.routes.write_skill_files", lambda skill, previous_name=None: None)

    def fake_execute_returning(query, params):
        assert "UPDATE skills" in query
        assert params[0:4] == ("summarize", "Summarize text", "", ["user"])
        assert params[-2:] == (False, 50)
        return {"id": 50, "name": "summarize", "description": "Summarize text", "argument_hint": "", "triggers": ["user"], "body": params[4], "resources": "", "enabled": False}

    monkeypatch.setattr("app.admin.routes.execute_returning", fake_execute_returning)

    class FakeAuditStore:
        def add_log(self, actor_user_id, action, target_type, target_id, metadata):
            captured.update({"actor_user_id": actor_user_id, "action": action, "target_type": target_type, "target_id": target_id, "metadata": metadata})

    monkeypatch.setattr("app.admin.routes.AuditStore", FakeAuditStore)

    result = update_skill(50, SkillPayload(name="summarize", description="Summarize text", enabled=False), FakeRequest())

    assert result["skill"]["enabled"] is False
    assert captured == {
        "actor_user_id": 1,
        "action": "skill.updated",
        "target_type": "skill",
        "target_id": 50,
        "metadata": {"name": "summarize", "enabled": False},
    }


def test_delete_skill_records_audit_log(monkeypatch):
    captured = {}
    monkeypatch.setattr("app.admin.routes.require_admin", lambda request: 1)
    monkeypatch.setattr("app.admin.routes.delete_skill_files", lambda name: None)

    def fake_execute_returning(query, params):
        assert "DELETE FROM skills" in query
        assert params == (50,)
        return {"id": 50, "name": "summarize"}

    monkeypatch.setattr("app.admin.routes.execute_returning", fake_execute_returning)

    class FakeAuditStore:
        def add_log(self, actor_user_id, action, target_type, target_id, metadata):
            captured.update({"actor_user_id": actor_user_id, "action": action, "target_type": target_type, "target_id": target_id, "metadata": metadata})

    monkeypatch.setattr("app.admin.routes.AuditStore", FakeAuditStore)

    result = delete_skill(50, FakeRequest())

    assert result == {"id": 50, "deleted": True}
    assert captured == {
        "actor_user_id": 1,
        "action": "skill.deleted",
        "target_type": "skill",
        "target_id": 50,
        "metadata": {"name": "summarize"},
    }


def test_generate_skill_returns_safe_draft_and_records_audit_log(monkeypatch):
    captured = {}
    monkeypatch.setattr("app.admin.routes.require_admin", lambda request: 1)

    class FakeAuditStore:
        def add_log(self, actor_user_id, action, target_type, target_id, metadata):
            captured.update({"actor_user_id": actor_user_id, "action": action, "target_type": target_type, "target_id": target_id, "metadata": metadata})

    monkeypatch.setattr("app.admin.routes.AuditStore", FakeAuditStore)

    result = generate_skill(SkillGeneratePayload(prompt="Analyze invoices and flag risky payments"), FakeRequest())

    assert result["draft"]["name"] == "analyze_invoices_and_flag_risky_payments_skill"
    assert "arbitrary generated code" in result["draft"]["instructions"]
    assert captured == {
        "actor_user_id": 1,
        "action": "skill.generated",
        "target_type": "skill",
        "target_id": None,
        "metadata": {"name": "analyze_invoices_and_flag_risky_payments_skill"},
    }


def test_build_skill_draft_truncates_description():
    draft = build_skill_draft("x" * 220)

    assert draft["name"] == "xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx"
    assert len(draft["description"]) == 180


def test_render_skill_md_uses_agent_skills_standard():
    skill_md = render_skill_md(
        {
            "name": "invoice-risk",
            "description": "Detect risky invoices.",
            "argument_hint": "Invoice text or CSV",
            "triggers": ["user"],
            "body": "# Instrucciones principales\n1. Parse invoices.",
            "resources": "examples/input.csv",
        }
    )

    assert skill_md.startswith("---\nname: invoice-risk\ndescription: Detect risky invoices.\nargument-hint: Invoice text or CSV\ntriggers: [\"user\"]\n---")
    assert "# Instrucciones principales" in skill_md
    assert "## Recursos opcionales" in skill_md


def test_resource_paths_rejects_unsafe_paths():
    with pytest.raises(HTTPException):
        resource_paths("../secret.txt")

    with pytest.raises(HTTPException):
        resource_paths("/absolute/path.txt")


def test_write_skill_files_creates_skill_md_and_resources(tmp_path, monkeypatch):
    monkeypatch.setattr("app.admin.routes.SKILLS_ROOT", tmp_path)

    write_skill_files(
        {
            "name": "invoice_skill",
            "description": "Review invoices.",
            "argument_hint": "Invoice text",
            "triggers": ["user"],
            "body": "# Instrucciones principales\n1. Review invoice.",
            "resources": "examples/invoice.md\ntemplates/report.md",
            "enabled": True,
        }
    )

    assert (tmp_path / "invoice_skill" / "SKILL.md").exists()
    assert (tmp_path / "invoice_skill" / "examples" / "invoice.md").exists()
    assert (tmp_path / "invoice_skill" / "templates" / "report.md").exists()
    assert "name: invoice_skill" in (tmp_path / "invoice_skill" / "SKILL.md").read_text(encoding="utf-8")


def test_write_skill_files_renames_previous_skill_directory(tmp_path, monkeypatch):
    monkeypatch.setattr("app.admin.routes.SKILLS_ROOT", tmp_path)
    (tmp_path / "old_skill").mkdir(parents=True)
    (tmp_path / "old_skill" / "SKILL.md").write_text("old", encoding="utf-8")

    write_skill_files(
        {
            "name": "new_skill",
            "description": "New skill.",
            "argument_hint": "",
            "triggers": ["user"],
            "body": "# Instrucciones principales\n1. Run.",
            "resources": "",
            "enabled": True,
        },
        previous_name="old_skill",
    )

    assert not (tmp_path / "old_skill").exists()
    assert (tmp_path / "new_skill" / "SKILL.md").exists()


def test_delete_skill_files_removes_skill_directory(tmp_path, monkeypatch):
    monkeypatch.setattr("app.admin.routes.SKILLS_ROOT", tmp_path)
    (tmp_path / "delete_me").mkdir(parents=True)
    (tmp_path / "delete_me" / "SKILL.md").write_text("content", encoding="utf-8")

    delete_skill_files("delete_me")

    assert not (tmp_path / "delete_me").exists()


def test_agent_payload_accepts_agentic_mode():
    payload = AgentPayload(
        name="Agentico",
        system_prompt="You are an agent with tools.",
        provider_id=6,
        model_id=6,
        agentic_mode=True,
    )

    assert payload.agentic_mode is True


def test_set_agent_tools_replaces_permissions_and_audits(monkeypatch):
    captured = {}
    executed = []
    monkeypatch.setattr("app.admin.routes.require_admin", lambda request: 1)
    monkeypatch.setattr("app.admin.routes.fetch_one", lambda query, params: {"id": 4, "name": "Agentico"})
    monkeypatch.setattr(
        "app.admin.routes.fetch_all",
        lambda query, params=(): executed.append((query, params)) or [{"agent_id": 4, "tool_name": "read_file", "allowed": True}],
    )

    class FakeCursor:
        description = []

        def __enter__(self):
            return self

        def __exit__(self, exc_type, exc, traceback):
            return False

        def execute(self, query, params=()):
            executed.append((query, params))

    class FakeConnection:
        def __enter__(self):
            return self

        def __exit__(self, exc_type, exc, traceback):
            return False

        def cursor(self):
            return FakeCursor()

    monkeypatch.setattr("app.admin.routes.connect", lambda: FakeConnection())

    class FakeAuditStore:
        def add_log(self, actor_user_id, action, target_type, target_id, metadata):
            captured.update({"action": action, "target_id": target_id, "metadata": metadata})

    monkeypatch.setattr("app.admin.routes.AuditStore", FakeAuditStore)

    result = set_agent_tools(4, AgentToolsPayload(tools=["read_file", "list_dir"]), FakeRequest())

    assert result == {"agent_id": 4, "tools": ["read_file", "list_dir"]}
    assert captured["action"] == "agent_tools.updated"
    assert captured["metadata"] == {"tools": ["read_file", "list_dir"]}
    assert any("DELETE FROM agent_tool_permissions" in query for query, _ in executed)
    assert any("INSERT INTO agent_tool_permissions" in query for query, _ in executed)


def test_set_agent_tools_accepts_dispatch_and_connector_tools(monkeypatch):
    monkeypatch.setattr("app.admin.routes.require_admin", lambda request: 1)
    monkeypatch.setattr("app.admin.routes.fetch_one", lambda query, params: {"id": 4, "name": "Agentico"})
    monkeypatch.setattr("app.admin.routes.fetch_all", lambda query, params=(): [])
    monkeypatch.setattr("app.admin.routes.connect", lambda: type("FakeConnection", (), {"__enter__": lambda self: self, "__exit__": lambda self, *args: False, "cursor": lambda self: type("FakeCursor", (), {"__enter__": lambda self: self, "__exit__": lambda self, *args: False, "execute": lambda self, query, params=(): None, "description": []})()})())
    monkeypatch.setattr("app.admin.routes.AuditStore", lambda: type("FakeAuditStore", (), {"add_log": lambda self, *args, **kwargs: None})())

    result = set_agent_tools(4, AgentToolsPayload(tools=["dispatch_subagents", "github_search_repos", "drive_search_files"]), FakeRequest())

    assert result["tools"] == ["dispatch_subagents", "github_search_repos", "drive_search_files"]


def test_set_agent_tools_rejects_unknown_tool(monkeypatch):
    monkeypatch.setattr("app.admin.routes.require_admin", lambda request: 1)

    with pytest.raises(HTTPException) as error:
        set_agent_tools(4, AgentToolsPayload(tools=["no_existe"]), FakeRequest())

    assert error.value.status_code == 400
    assert "no_existe" in error.value.detail


def test_guardrail_settings_roundtrip(monkeypatch):
    monkeypatch.setattr("app.admin.routes.require_admin", lambda request: 1)
    stored = {}

    def fake_fetch_one(query, params=()):
        if "app_settings" in query:
            return {"value": {"max_iterations": 5}}
        return None

    monkeypatch.setattr("app.admin.routes.fetch_one", fake_fetch_one)

    result = list_guardrail_settings(FakeRequest())

    assert result == {"guardrails": {"max_iterations": 5}}

    def fake_execute_returning(query, params):
        stored["query"] = query
        stored["params"] = params
        return {"value": json.loads(params[0])}

    monkeypatch.setattr("app.admin.routes.execute_returning", fake_execute_returning)
    monkeypatch.setattr(
        "app.admin.routes.AuditStore",
        lambda: type("FakeAuditStore", (), {"add_log": lambda self, *args, **kwargs: None})(),
    )

    updated = update_guardrail_settings(GuardrailSettingsPayload(max_iterations=7, max_tool_calls=30), FakeRequest())

    assert updated == {"guardrails": {"max_iterations": 7, "max_tool_calls": 30}}
    assert json.loads(stored["params"][0]) == {"max_iterations": 7, "max_tool_calls": 30}


def test_skill_run_payload_accepts_registered_internet_skill():
    payload = SkillRunPayload(skill_name="read_url", payload={"url": "https://example.com"})

    assert payload.skill_name == "read_url"
    assert payload.payload["url"] == "https://example.com"


def test_skill_run_payload_rejects_unregistered_skill():
    with pytest.raises(ValidationError):
        SkillRunPayload(skill_name="delete_everything", payload={})


def test_workflow_payload_accepts_reviewer_workflow_with_agent_ids():
    payload = WorkflowPayload(name="Review Flow", workflow_type="reviewer", agent_ids=[1, 2], enabled=True)

    assert payload.workflow_type == "reviewer"
    assert payload.agent_ids == [1, 2]


def test_workflow_payload_rejects_unknown_workflow_type():
    with pytest.raises(ValidationError):
        WorkflowPayload(name="Bad", workflow_type="unknown", agent_ids=[])


def test_create_workflow_records_audit_log(monkeypatch):
    captured = {}
    monkeypatch.setattr("app.admin.routes.require_admin", lambda request: 1)

    class FakeCursor:
        description = []

        def __enter__(self):
            return self

        def __exit__(self, exc_type, exc, traceback):
            return False

        def execute(self, query, params=()):
            if query.strip().startswith("INSERT INTO workflows"):
                self.description = [type("Column", (), {"name": name}) for name in ["id", "name", "workflow_type", "enabled"]]

        def fetchone(self):
            return (30, "Review", "reviewer", True)

    class FakeConnection:
        def __enter__(self):
            return self

        def __exit__(self, exc_type, exc, traceback):
            return False

        def cursor(self):
            return FakeCursor()

    monkeypatch.setattr("app.admin.routes.connect", lambda: FakeConnection())

    class FakeAuditStore:
        def add_log(self, actor_user_id, action, target_type, target_id, metadata):
            captured.update({"actor_user_id": actor_user_id, "action": action, "target_type": target_type, "target_id": target_id, "metadata": metadata})

    monkeypatch.setattr("app.admin.routes.AuditStore", FakeAuditStore)
    payload = WorkflowPayload(name="Review", workflow_type="reviewer", agent_ids=[1], enabled=True)

    create_workflow(payload, FakeRequest())

    assert captured == {
        "actor_user_id": 1,
        "action": "workflow.created",
        "target_type": "workflow",
        "target_id": 30,
        "metadata": {"name": "Review", "workflow_type": "reviewer", "step_count": 1, "enabled": True},
    }


def test_update_workflow_replaces_steps_transactionally(monkeypatch):
    monkeypatch.setattr("app.admin.routes.require_admin", lambda request: 1)
    monkeypatch.setattr("app.admin.routes.AuditStore", lambda: type("FakeAuditStore", (), {"add_log": lambda self, *args, **kwargs: None})())
    statements = []

    class FakeCursor:
        description = []

        def __enter__(self):
            return self

        def __exit__(self, exc_type, exc, traceback):
            return False

        def execute(self, query, params=()):
            statements.append((query.strip(), params))
            self.description = [type("Column", (), {"name": name}) for name in ["id", "name", "workflow_type", "enabled"]]

        def fetchone(self):
            return (3, "Updated", "sequential", True)

    class FakeConnection:
        def __enter__(self):
            return self

        def __exit__(self, exc_type, exc, traceback):
            return False

        def cursor(self):
            return FakeCursor()

    monkeypatch.setattr("app.admin.routes.connect", lambda: FakeConnection())

    result = update_workflow(3, WorkflowPayload(name="Updated", workflow_type="sequential", agent_ids=[2, 4], enabled=True), FakeRequest())

    assert result["workflow"]["id"] == 3
    assert any(statement[0].startswith("DELETE FROM workflow_steps") for statement in statements)
    assert [statement[1] for statement in statements if statement[0].startswith("INSERT INTO workflow_steps")] == [
        (3, 2, 1, "Step 1"),
        (3, 4, 2, "Step 2"),
    ]


def test_ensure_positive_id_accepts_positive_integer():
    assert ensure_positive_id(7, "agent_id") == 7


def test_ensure_positive_id_rejects_zero_or_negative_integer():
    with pytest.raises(ValueError, match="agent_id must be a positive integer"):
        ensure_positive_id(0, "agent_id")

    with pytest.raises(ValueError, match="skill_id must be a positive integer"):
        ensure_positive_id(-1, "skill_id")


def test_user_role_payload_accepts_known_roles():
    assert UserRolePayload(role="admin").role == "admin"
    assert UserRolePayload(role="user").role == "user"


def test_user_role_payload_rejects_unknown_role():
    with pytest.raises(ValidationError):
        UserRolePayload(role="owner")


def test_update_user_role_records_audit_log(monkeypatch):
    captured = {}
    monkeypatch.setattr("app.admin.routes.require_admin", lambda request: 1)

    def fake_fetch_one(query, params):
        if "COUNT(*) AS admin_count" in query:
            return {"admin_count": 2}
        return {"id": 2, "role": "user"}

    monkeypatch.setattr("app.admin.routes.fetch_one", fake_fetch_one)
    monkeypatch.setattr(
        "app.admin.routes.execute_returning",
        lambda query, params: {"id": 2, "username": "ada", "email": "ada@example.com", "role": "admin", "created_at": "created"},
    )

    class FakeAuditStore:
        def add_log(self, actor_user_id, action, target_type, target_id, metadata):
            captured.update(
                {
                    "actor_user_id": actor_user_id,
                    "action": action,
                    "target_type": target_type,
                    "target_id": target_id,
                    "metadata": metadata,
                }
            )

    monkeypatch.setattr("app.admin.routes.AuditStore", FakeAuditStore)

    update_user_role(2, UserRolePayload(role="admin"), FakeRequest())

    assert captured == {
        "actor_user_id": 1,
        "action": "user.role_updated",
        "target_type": "user",
        "target_id": 2,
        "metadata": {"previous_role": "user", "next_role": "admin"},
    }


def test_admin_role_change_rejects_demoting_last_admin():
    with pytest.raises(ValueError, match="At least one admin user is required"):
        ensure_admin_role_change_allowed(current_role="admin", next_role="user", admin_count=1)


def test_admin_role_change_allows_promoting_user():
    ensure_admin_role_change_allowed(current_role="user", next_role="admin", admin_count=1)
