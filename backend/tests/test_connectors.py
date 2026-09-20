import base64
import json

import pytest

from app.agent.tools.base import ToolRegistry
from app.connectors import catalog, crypto, gdrive, github
from app.connectors.bridge import McpAgentTool, _sanitize_tool_name, register_connector_tools, register_mcp_agent_tools
from app.connectors.catalog import CONNECTOR_DEFINITIONS, get_connector_definition


class FakeRequest:
    session = {"user_id": 1, "role": "user"}


def test_connector_credentials_roundtrip(monkeypatch):
    monkeypatch.delenv("CONNECTOR_ENCRYPTION_KEY", raising=False)
    encrypted = crypto.encrypt_credential("ghp_supersecret")
    assert encrypted != "ghp_supersecret"
    assert crypto.decrypt_credential(encrypted) == "ghp_supersecret"


def test_connector_credentials_reject_tampered_value():
    with pytest.raises(ValueError, match="cannot be decrypted"):
        crypto.decrypt_credential("not-a-fernet-token")


def test_mask_credential_hides_middle():
    assert crypto.mask_credential("ghp_1234567890abcd") == "ghp_...abcd"


def test_catalog_has_github_and_gdrive_definitions():
    assert set(CONNECTOR_DEFINITIONS) >= {"github", "gdrive"}
    github_definition = get_connector_definition("github")
    assert github_definition.tool_names == ["github_search_repos", "github_list_issues", "github_read_file", "github_create_issue"]
    with pytest.raises(ValueError, match="Unknown connector"):
        get_connector_definition("nope")


def test_github_build_tools_names_and_permissions():
    tools = github.build_tools("token")
    permissions = {tool.spec.name: tool.spec.permission for tool in tools}
    assert permissions == {
        "github_search_repos": "safe",
        "github_list_issues": "safe",
        "github_read_file": "safe",
        "github_create_issue": "sensitive",
    }


def _fake_urlopen_factory(responses):
    calls = []

    class FakeResponse:
        def __init__(self, body):
            self._body = body

        def __enter__(self):
            return self

        def __exit__(self, exc_type, exc, traceback):
            return False

        def read(self):
            return self._body

    def fake_urlopen(request, timeout=20):
        calls.append({"url": request.full_url, "method": request.get_method(), "headers": dict(request.headers), "data": request.data})
        return FakeResponse(responses.pop(0).encode("utf-8"))

    return fake_urlopen, calls


def test_github_search_repos_tool_queries_api(monkeypatch):
    fake_urlopen, calls = _fake_urlopen_factory([json.dumps({"items": [{"full_name": "tiangolo/fastapi", "stargazers_count": 80, "description": "web framework"}]})])
    monkeypatch.setattr("app.connectors.github.urlopen", fake_urlopen)

    result = github.GitHubSearchReposTool("ghp_token").run({"query": "fastapi", "limit": 3})

    assert result.ok
    assert "tiangolo/fastapi (stars 80)" in result.output
    assert calls[0]["url"].startswith("https://api.github.com/search/repositories")
    assert "q=fastapi" in calls[0]["url"]
    assert "per_page=3" in calls[0]["url"]
    assert calls[0]["headers"]["Authorization"] == "Bearer ghp_token"


def test_github_read_file_tool_decodes_base64(monkeypatch):
    content = base64.b64encode(b"# hello world").decode("ascii")
    fake_urlopen, calls = _fake_urlopen_factory([json.dumps({"encoding": "base64", "content": content, "size": 13})])
    monkeypatch.setattr("app.connectors.github.urlopen", fake_urlopen)

    result = github.GitHubReadFileTool("ghp_token").run({"owner": "tiangolo", "repo": "fastapi", "path": "README.md"})

    assert result.ok
    assert result.output == "# hello world"
    assert "/repos/tiangolo/fastapi/contents/README.md" in calls[0]["url"]


def test_github_create_issue_posts_payload(monkeypatch):
    fake_urlopen, calls = _fake_urlopen_factory([json.dumps({"html_url": "https://github.com/x/y/issues/1", "number": 1})])
    monkeypatch.setattr("app.connectors.github.urlopen", fake_urlopen)

    result = github.GitHubCreateIssueTool("ghp_token").run({"owner": "x", "repo": "y", "title": "Bug"})

    assert result.ok
    assert "https://github.com/x/y/issues/1" in result.output
    assert calls[0]["method"] == "POST"
    assert json.loads(calls[0]["data"]) == {"title": "Bug", "body": ""}


def test_github_test_token_reports_login(monkeypatch):
    fake_urlopen, _ = _fake_urlopen_factory([json.dumps({"login": "octocat"})])
    monkeypatch.setattr("app.connectors.github.urlopen", fake_urlopen)

    assert github.test_token("ghp_token") == {"ok": True, "detail": "Autenticado como octocat"}


def test_gdrive_search_files_tool_queries_drive(monkeypatch):
    payload = {"files": [{"name": "Informe Q3", "mimeType": "application/vnd.google-apps.document", "webViewLink": "https://drive.google.com/file/d/1"}]}
    fake_urlopen, calls = _fake_urlopen_factory([json.dumps(payload)])
    monkeypatch.setattr("app.connectors.gdrive.urlopen", fake_urlopen)

    result = gdrive.DriveSearchFilesTool("ya29_token").run({"query": "Informe Q3"})

    assert result.ok
    assert "Informe Q3" in result.output
    assert "fullText" in calls[0]["url"]
    assert calls[0]["headers"]["Authorization"] == "Bearer ya29_token"


def test_gdrive_read_file_exports_google_docs(monkeypatch):
    metadata = json.dumps({"name": "Informe", "mimeType": "application/vnd.google-apps.document"}).encode()
    fake_urlopen, calls = _fake_urlopen_factory(["__METADATA__"])

    class FakeResponse:
        def __init__(self, body):
            self._body = body

        def __enter__(self):
            return self

        def __exit__(self, exc_type, exc, traceback):
            return False

        def read(self):
            return self._body

    def fake_urlopen(request, timeout=20):
        calls.append({"url": request.full_url})
        body = metadata if len(calls) == 1 else b"texto del informe"
        return FakeResponse(body)

    monkeypatch.setattr("app.connectors.gdrive.urlopen", fake_urlopen)

    result = gdrive.DriveReadFileTool("ya29_token").run({"file_id": "abc123"})

    assert result.ok
    assert "texto del informe" in result.output
    assert "/files/abc123/export" in calls[1]["url"]


def test_sanitize_tool_name_normalizes_parts():
    assert _sanitize_tool_name("My Server!", "read.file") == "my_server_read_file"


def test_register_connector_tools_adds_connected_accounts(monkeypatch):
    class FakeStore:
        def connected_slugs(self, user_id):
            return ["github"]

        def get_credential(self, user_id, slug):
            return crypto.encrypt_credential("ghp_token")

    monkeypatch.setattr("app.connectors.bridge.ConnectorStore", FakeStore)
    registry = ToolRegistry()
    register_connector_tools(registry, 1)
    assert "github_search_repos" in [spec.name for spec in registry.list_specs()]


def test_register_connector_tools_skips_unknown_and_broken_credentials(monkeypatch):
    class FakeStore:
        def connected_slugs(self, user_id):
            return ["unknown-connector", "gdrive"]

        def get_credential(self, user_id, slug):
            return "not-fernet" if slug == "gdrive" else None

    monkeypatch.setattr("app.connectors.bridge.ConnectorStore", FakeStore)
    registry = ToolRegistry()
    register_connector_tools(registry, 1)
    assert registry.list_specs() == []


def test_register_mcp_agent_tools_registers_discovered_tools(monkeypatch):
    server = {"id": 3, "name": "Filesystem Server", "connection_type": "command", "command": "npx server", "url": None}
    monkeypatch.setattr("app.connectors.bridge._assigned_mcp_servers", lambda agent_id: [server])
    monkeypatch.setattr(
        "app.connectors.bridge._cached_inspection",
        lambda srv: [{"name": "read_file", "description": "Read a file", "inputSchema": {"type": "object"}}],
    )
    registry = ToolRegistry()
    register_mcp_agent_tools(registry, 5)

    specs = {spec.name: spec for spec in registry.list_specs()}
    assert "mcp_filesystem_server_read_file" in specs
    assert specs["mcp_filesystem_server_read_file"].permission == "sensitive"


def test_mcp_agent_tool_runs_tools_call(monkeypatch):
    captured = {}

    def fake_call(self, command, method, params, timeout_seconds=30):
        captured.update({"command": command, "method": method, "params": params})
        return {"jsonrpc": "2.0", "id": 1, "result": {"content": [{"type": "text", "text": "hola desde mcp"}]}}

    monkeypatch.setattr("app.mcps.gateway.McpGateway.call_command", fake_call)
    server = {"id": 3, "name": "srv", "connection_type": "command", "command": "npx server", "url": None}
    from app.agent.tools.base import ToolSpec

    tool = McpAgentTool(ToolSpec(name="mcp_srv_read", description="d", parameters="{}", permission="sensitive"), server, "read")
    result = tool.run({"path": "a.txt"})

    assert result.ok
    assert result.output == "hola desde mcp"
    assert captured["method"] == "tools/call"
    assert captured["params"] == {"name": "read", "arguments": {"path": "a.txt"}}


def test_mcp_agent_tool_reports_mcp_errors(monkeypatch):
    monkeypatch.setattr("app.mcps.gateway.McpGateway.call_command", lambda self, command, method, params, timeout_seconds=30: {"error": {"message": "tool not found"}})
    server = {"id": 3, "name": "srv", "connection_type": "command", "command": "npx server", "url": None}
    from app.agent.tools.base import ToolSpec

    tool = McpAgentTool(ToolSpec(name="mcp_srv_read", description="d", parameters="{}", permission="sensitive"), server, "read")
    result = tool.run({})

    assert not result.ok
    assert "tool not found" in result.output
