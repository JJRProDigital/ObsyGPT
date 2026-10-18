import base64
import hashlib
import json
import time

import pytest

from app.agent.tools.base import ToolRegistry
from app.connectors import catalog, crypto, gdrive, github, higgsfield, higgsfield_api
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


def test_catalog_includes_higgsfield_oauth_connector():
    definition = get_connector_definition("higgsfield")
    assert definition.auth_type == "oauth"
    without_credentials = definition.build_tools("")
    assert [tool.spec.name for tool in without_credentials] == ["higgsfield_mcp_call"]
    assert "oauth" in definition.token_help.lower()


class FakeHttpResponse:
    def __init__(self, body: str, headers: dict | None = None):
        self._body = body
        self.headers = headers or {}

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc, traceback):
        return False

    def read(self):
        return self._body.encode("utf-8")


def _higgsfield_fake_urlopen(responses):
    calls = []

    def fake_urlopen(request, timeout=20):
        calls.append({"url": request.full_url, "method": request.get_method(), "headers": dict(request.headers), "data": request.data})
        body, headers = responses.pop(0)
        return FakeHttpResponse(body, headers)

    return fake_urlopen, calls


def test_higgsfield_pkce_pair_matches_s256():
    verifier, challenge = higgsfield.create_pkce_pair()
    expected = base64.urlsafe_b64encode(hashlib.sha256(verifier.encode("ascii")).digest()).decode("ascii").rstrip("=")
    assert challenge == expected


def test_higgsfield_authorization_url_contains_pkce_params():
    url = higgsfield.build_authorization_url("cid", "https://cb", "state123", "challenge456")
    assert url.startswith(higgsfield.AUTHORIZE_ENDPOINT)
    assert "client_id=cid" in url
    assert "code_challenge_method=S256" in url
    assert "code_challenge=challenge456" in url
    assert "state=state123" in url


def test_higgsfield_load_credentials_accepts_json_and_plain_token():
    blob = higgsfield.dump_credentials("at", "rt", 3600, "cid")
    creds = higgsfield.load_credentials(blob)
    assert creds["access_token"] == "at"
    assert creds["client_id"] == "cid"
    assert higgsfield.load_credentials("raw_token") == {"access_token": "raw_token"}
    assert higgsfield.load_credentials("") == {}


def test_higgsfield_build_tools_discovers_mcp_tools(monkeypatch):
    blob = higgsfield.dump_credentials("at", "rt", 3600, "cid")
    responses = [
        (json.dumps({"jsonrpc": "2.0", "id": 1, "result": {}}), {"Mcp-Session-Id": "sess-1"}),
        ("", {}),
        ('data: {"jsonrpc":"2.0","id":2,"result":{"tools":[{"name":"Generate Video","description":"Genera un video","inputSchema":{"type":"object"}}]}}\n\n', {}),
    ]
    fake_urlopen, calls = _higgsfield_fake_urlopen(responses)
    monkeypatch.setattr("app.connectors.higgsfield.urlopen", fake_urlopen)

    tools = higgsfield.build_tools(blob)

    names = [tool.spec.name for tool in tools]
    assert "higgsfield_generate_video" in names
    assert "higgsfield_mcp_call" in names
    stable_tool = next(tool for tool in tools if tool.spec.name == "higgsfield_mcp_call")
    assert "Generate Video" in stable_tool.spec.description
    assert tools[0].spec.permission == "sensitive"
    assert calls[0]["headers"]["Authorization"] == "Bearer at"
    sent_session = {key.lower(): value for key, value in calls[2]["headers"].items()}
    assert sent_session.get("mcp-session-id") == "sess-1"


def test_higgsfield_tool_calls_mcp_and_renders_text(monkeypatch):
    creds = higgsfield.load_credentials(higgsfield.dump_credentials("at", "rt", 3600, "cid"))
    responses = [
        (json.dumps({"jsonrpc": "2.0", "id": 1, "result": {}}), {"Mcp-Session-Id": "sess-1"}),
        ("", {}),
        (json.dumps({"jsonrpc": "2.0", "id": 3, "result": {"content": [{"type": "text", "text": "video listo"}]}}), {}),
    ]
    fake_urlopen, calls = _higgsfield_fake_urlopen(responses)
    monkeypatch.setattr("app.connectors.higgsfield.urlopen", fake_urlopen)

    result = higgsfield.HiggsfieldMcpTool(
        higgsfield.ToolSpec(name="higgsfield_generate_video", description="d", parameters="{}", permission="sensitive"),
        "generate_video",
        creds,
    ).run({"prompt": "gato"})

    assert result.ok
    assert result.output == "video listo"
    tool_call = calls[2]
    assert json.loads(tool_call["data"])["params"] == {"name": "generate_video", "arguments": {"prompt": "gato"}}


def test_higgsfield_coerce_arguments_accepts_object_json_and_python_style():
    assert higgsfield._coerce_arguments({"prompt": "x"}) == {"prompt": "x"}
    assert higgsfield._coerce_arguments('{"prompt": "x"}') == {"prompt": "x"}
    assert higgsfield._coerce_arguments("{'prompt': 'x'}") == {"prompt": "x"}
    assert higgsfield._coerce_arguments("") == {}
    assert higgsfield._coerce_arguments("not json at all") is None
    assert higgsfield._coerce_arguments('["list"]') is None


def test_higgsfield_call_tool_parses_stringified_arguments(monkeypatch):
    creds = higgsfield.load_credentials(higgsfield.dump_credentials("at", "rt", 3600, "cid"))
    responses = [
        (json.dumps({"jsonrpc": "2.0", "id": 1, "result": {}}), {}),
        ("", {}),
        (json.dumps({"jsonrpc": "2.0", "id": 3, "result": {"content": [{"type": "text", "text": "ok"}]}}), {}),
    ]
    fake_urlopen, calls = _higgsfield_fake_urlopen(responses)
    monkeypatch.setattr("app.connectors.higgsfield.urlopen", fake_urlopen)

    tool = higgsfield.HiggsfieldMcpCallTool(creds)
    result = tool.run({"tool": "generate_video", "arguments": "{\"prompt\": \"video de prueba\"}"})

    assert result.ok
    assert json.loads(calls[2]["data"])["params"]["arguments"] == {"params": {"prompt": "video de prueba"}}

    result_bad = tool.run({"tool": "generate_video", "arguments": "esto no es json"})
    assert not result_bad.ok
    assert "Invalid arguments" in result_bad.output


def test_higgsfield_call_tool_accepts_top_level_parameters(monkeypatch):
    creds = higgsfield.load_credentials(higgsfield.dump_credentials("at", "rt", 3600, "cid"))
    responses = [
        (json.dumps({"jsonrpc": "2.0", "id": 1, "result": {}}), {}),
        ("", {}),
        (json.dumps({"jsonrpc": "2.0", "id": 3, "result": {"content": [{"type": "text", "text": "video listo"}]}}), {}),
    ]
    fake_urlopen, calls = _higgsfield_fake_urlopen(responses)
    monkeypatch.setattr("app.connectors.higgsfield.urlopen", fake_urlopen)

    tool = higgsfield.HiggsfieldMcpCallTool(creds)
    result = tool.run({"tool": "generate_video", "prompt": "oficina vintage", "duration": 14})

    assert result.ok
    assert json.loads(calls[2]["data"])["params"] == {
        "name": "generate_video",
        "arguments": {"params": {"prompt": "oficina vintage", "duration": 14}},
    }


def test_higgsfield_call_tool_keeps_explicit_params_and_context(monkeypatch):
    creds = higgsfield.load_credentials(higgsfield.dump_credentials("at", "rt", 3600, "cid"))
    responses = [
        (json.dumps({"jsonrpc": "2.0", "id": 1, "result": {}}), {}),
        ("", {}),
        (json.dumps({"jsonrpc": "2.0", "id": 3, "result": {"content": [{"type": "text", "text": "ok"}]}}), {}),
    ]
    fake_urlopen, calls = _higgsfield_fake_urlopen(responses)
    monkeypatch.setattr("app.connectors.higgsfield.urlopen", fake_urlopen)

    tool = higgsfield.HiggsfieldMcpCallTool(creds)
    result = tool.run(
        {
            "tool": "generate_video",
            "arguments": {"params": {"model": "soul_2", "prompt": "oficina"}, "context": "usuario pide un video"},
        }
    )

    assert result.ok
    assert json.loads(calls[2]["data"])["params"]["arguments"] == {
        "params": {"model": "soul_2", "prompt": "oficina"},
        "context": "usuario pide un video",
    }


def test_higgsfield_call_tool_defaults_to_generate_video_with_bare_prompt(monkeypatch):
    creds = higgsfield.load_credentials(higgsfield.dump_credentials("at", "rt", 3600, "cid"))
    responses = [
        (json.dumps({"jsonrpc": "2.0", "id": 1, "result": {}}), {}),
        ("", {}),
        (json.dumps({"jsonrpc": "2.0", "id": 3, "result": {"content": [{"type": "text", "text": "ok"}]}}), {}),
    ]
    fake_urlopen, calls = _higgsfield_fake_urlopen(responses)
    monkeypatch.setattr("app.connectors.higgsfield.urlopen", fake_urlopen)

    tool = higgsfield.HiggsfieldMcpCallTool(creds)
    result = tool.run({"prompt": "un gato astronauta"})

    assert result.ok
    assert json.loads(calls[2]["data"])["params"]["name"] == "generate_video"


def test_higgsfield_expired_token_refreshes_via_token_endpoint(monkeypatch):
    creds = {"access_token": "stale", "refresh_token": "rt", "client_id": "cid", "expires_at": time.time() - 10}
    responses = [
        (json.dumps({"access_token": "fresh", "refresh_token": "rt2", "expires_in": 3600}), {}),
        (json.dumps({"jsonrpc": "2.0", "id": 1, "result": {}}), {}),
        ("", {}),
        (json.dumps({"jsonrpc": "2.0", "id": 2, "result": {"tools": []}}), {}),
    ]
    fake_urlopen, calls = _higgsfield_fake_urlopen(responses)
    monkeypatch.setattr("app.connectors.higgsfield.urlopen", fake_urlopen)

    tools = higgsfield.build_tools(json.dumps(creds))

    assert calls[0]["url"] == higgsfield.TOKEN_ENDPOINT
    assert "Authorization" not in calls[0]["headers"]
    form = calls[0]["data"].decode("ascii")
    assert "grant_type=refresh_token" in form
    assert "refresh_token=rt" in form
    assert len(tools) == 1 and isinstance(tools[0], higgsfield.HiggsfieldMcpCallTool)


def test_catalog_includes_higgsfield_api_connector():
    definition = get_connector_definition("higgsfield_api")
    assert definition.auth_type == "token"
    assert definition.tool_names == ["higgsfield_api_generate_video", "higgsfield_api_generate_image", "higgsfield_api_request_status"]
    assert len(definition.build_tools("id:secret")) == 3


def test_higgsfield_api_split_credentials_rejects_bad_format():
    with pytest.raises(RuntimeError, match="Formato de credencial invalido"):
        higgsfield_api._split_credentials("solo-un-valor")
    key_id, key_secret = higgsfield_api._split_credentials(" myid:mysecret ")
    assert (key_id, key_secret) == ("myid", "mysecret")


def test_higgsfield_api_auth_header_uses_key_scheme():
    headers = higgsfield_api._auth_header("myid:mysecret")
    assert headers["Authorization"] == "Key myid:mysecret"


def test_higgsfield_api_endpoint_validation_rejects_injection():
    assert higgsfield_api._validate_endpoint(" kling-video/v3.0/std/text-to-video ") == "kling-video/v3.0/std/text-to-video"
    with pytest.raises(RuntimeError, match="Endpoint invalido"):
        higgsfield_api._validate_endpoint("../admin")
    with pytest.raises(RuntimeError, match="Endpoint invalido"):
        higgsfield_api._validate_endpoint("no-slashes")


def test_higgsfield_api_video_tool_submits_and_reports_handle(monkeypatch):
    responses = [
        (json.dumps({"status": "queued", "request_id": "req-1", "status_url": "https://api.higgsfield.ai/requests/req-1/status", "cancel_url": "x"}), {}),
    ]
    fake_urlopen, calls = _higgsfield_fake_urlopen(responses)
    monkeypatch.setattr("app.connectors.higgsfield_api.urlopen", fake_urlopen)

    tool = higgsfield_api.HiggsfieldApiVideoTool("id:secret")
    result = tool.run({"prompt": "un gato astronauta", "duration": 5})

    assert result.ok
    assert "req-1" in result.output
    assert "higgsfield_api_request_status" in result.output
    submitted = json.loads(calls[0]["data"])
    assert submitted == {"prompt": "un gato astronauta", "duration": 5}
    assert calls[0]["url"] == "https://api.higgsfield.ai/kling-video/v3.0/std/text-to-video"
    assert calls[0]["headers"]["Authorization"] == "Key id:secret"


def test_higgsfield_api_status_tool_renders_completed_video(monkeypatch):
    responses = [
        (json.dumps({"status": "completed", "request_id": "req-1", "video": {"url": "https://cdn.example.com/v.mp4"}}), {}),
    ]
    fake_urlopen, calls = _higgsfield_fake_urlopen(responses)
    monkeypatch.setattr("app.connectors.higgsfield_api.urlopen", fake_urlopen)

    tool = higgsfield_api.HiggsfieldApiStatusTool("id:secret")
    result = tool.run({"request_id": "req-1"})

    assert result.ok
    assert "completed" in result.output
    assert "https://cdn.example.com/v.mp4" in result.output
    assert calls[0]["url"] == "https://api.higgsfield.ai/requests/req-1/status"


def test_higgsfield_api_status_tool_waits_until_completed(monkeypatch):
    responses = [
        (json.dumps({"status": "in_progress", "request_id": "req-1"}), {}),
        (json.dumps({"status": "completed", "request_id": "req-1", "video": {"url": "https://cdn.example.com/v.mp4"}}), {}),
    ]
    fake_urlopen, calls = _higgsfield_fake_urlopen(responses)
    monkeypatch.setattr("app.connectors.higgsfield_api.urlopen", fake_urlopen)
    slept: list[float] = []
    monkeypatch.setattr("app.connectors.higgsfield_api.time.sleep", lambda seconds: slept.append(seconds))

    tool = higgsfield_api.HiggsfieldApiStatusTool("id:secret")
    result = tool.run({"request_id": "req-1", "wait_seconds": 60})

    assert result.ok
    assert "completed" in result.output
    assert "https://cdn.example.com/v.mp4" in result.output
    assert len(calls) == 2
    assert slept == [5]


def test_higgsfield_api_status_tool_rejects_foreign_status_url():
    tool = higgsfield_api.HiggsfieldApiStatusTool("id:secret")
    result = tool.run({"status_url": "https://evil.example.com/steal"})
    assert not result.ok


def test_higgsfield_api_test_token_accepts_404_and_rejects_401(monkeypatch):
    from urllib.error import HTTPError

    def fake_urlopen_404(request, timeout=20):
        raise HTTPError(request.full_url, 404, "Not Found", {}, None)

    def fake_urlopen_401(request, timeout=20):
        raise HTTPError(request.full_url, 401, "Unauthorized", {}, None)

    monkeypatch.setattr("app.connectors.higgsfield_api.urlopen", fake_urlopen_404)
    verification = higgsfield_api.test_token("id:secret")
    assert verification["ok"]

    monkeypatch.setattr("app.connectors.higgsfield_api.urlopen", fake_urlopen_401)
    with pytest.raises(RuntimeError, match="Credenciales rechazadas"):
        higgsfield_api.test_token("id:secret")


def test_higgsfield_test_token_reports_tool_count(monkeypatch):
    blob = higgsfield.dump_credentials("at", "rt", 3600, "cid")
    responses = [
        (json.dumps({"jsonrpc": "2.0", "id": 1, "result": {}}), {}),
        ("", {}),
        (json.dumps({"jsonrpc": "2.0", "id": 2, "result": {"tools": [{"name": "a"}, {"name": "b"}]}}), {}),
    ]
    fake_urlopen, _ = _higgsfield_fake_urlopen(responses)
    monkeypatch.setattr("app.connectors.higgsfield.urlopen", fake_urlopen)

    verification = higgsfield.test_token(blob)

    assert verification == {"ok": True, "detail": "Higgsfield MCP con 2 herramientas disponibles"}


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
