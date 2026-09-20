import pytest

from app.mcps.gateway import McpGateway, McpServerConfig, parse_command, validate_url


def test_mcp_gateway_lists_registered_servers_without_executing_them():
    gateway = McpGateway()
    gateway.register(
        McpServerConfig(
            name="filesystem",
            description="Local files",
            connection_type="command",
            command="npx -y @modelcontextprotocol/server-filesystem .",
            url=None,
            enabled=False,
        )
    )

    assert gateway.list_servers()[0].name == "filesystem"
    assert gateway.list_servers()[0].enabled is False


def test_mcp_gateway_rejects_url_server_without_url():
    gateway = McpGateway()

    with pytest.raises(ValueError, match="URL MCP servers require a URL"):
        gateway.register(
            McpServerConfig(
                name="broken",
                description="Broken",
                connection_type="url",
                command=None,
                url=None,
                enabled=True,
            )
        )


def test_mcp_gateway_rejects_command_server_without_command():
    gateway = McpGateway()

    with pytest.raises(ValueError, match="Command MCP servers require a command"):
        gateway.register(
            McpServerConfig(
                name="broken",
                description="Broken",
                connection_type="command",
                command=None,
                url=None,
                enabled=True,
            )
        )


def test_parse_command_splits_quoted_arguments():
    assert parse_command('npx -y "@modelcontextprotocol/server-filesystem" "C:/Users/Juan Jose"') == [
        "npx",
        "-y",
        "@modelcontextprotocol/server-filesystem",
        "C:/Users/Juan Jose",
    ]


def test_parse_command_rejects_empty_command():
    with pytest.raises(ValueError, match="Command is required"):
        parse_command("   ")


def test_parse_command_rejects_shell_metacharacters():
    with pytest.raises(ValueError, match="Shell operators are not allowed"):
        parse_command("npx server && rm -rf .")


def test_mcp_gateway_validate_command_returns_parsed_args_without_registering():
    gateway = McpGateway()
    result = gateway.validate(
        McpServerConfig(
            name="filesystem",
            description="Local files",
            connection_type="command",
            command='npx -y "@modelcontextprotocol/server-filesystem" .',
            url=None,
            enabled=True,
        )
    )

    assert result == {
        "valid": True,
        "connection_type": "command",
        "command_args": ["npx", "-y", "@modelcontextprotocol/server-filesystem", "."],
    }
    assert gateway.list_servers() == []


def test_mcp_gateway_validate_url_returns_target_without_registering():
    gateway = McpGateway()
    result = gateway.validate(
        McpServerConfig(
            name="remote",
            description="Remote MCP",
            connection_type="url",
            command=None,
            url="https://mcp.example.com",
            enabled=True,
        )
    )

    assert result == {"valid": True, "connection_type": "url", "url": "https://mcp.example.com"}
    assert gateway.list_servers() == []


def test_mcp_gateway_call_command_sends_json_rpc_without_shell(monkeypatch):
    captured = {}

    def fake_run(args, input, text, capture_output, timeout, shell):
        captured.update(
            {
                "args": args,
                "input": input,
                "text": text,
                "capture_output": capture_output,
                "timeout": timeout,
                "shell": shell,
            }
        )

        class Result:
            returncode = 0
            stdout = '{"jsonrpc":"2.0","id":1,"result":{"tools":[]}}\n'
            stderr = ""

        return Result()

    monkeypatch.setattr("app.mcps.gateway.subprocess.run", fake_run)
    gateway = McpGateway()

    response = gateway.call_command(
        command='node "server.js"',
        method="tools/list",
        params={},
        request_id=1,
        timeout_seconds=3,
    )

    assert captured["args"] == ["node", "server.js"]
    assert '"method": "tools/list"' in captured["input"]
    assert captured["shell"] is False
    assert captured["timeout"] == 3
    assert response == {"jsonrpc": "2.0", "id": 1, "result": {"tools": []}}


def test_mcp_gateway_call_command_rejects_nonzero_exit(monkeypatch):
    def fake_run(*args, **kwargs):
        class Result:
            returncode = 1
            stdout = ""
            stderr = "boom"

        return Result()

    monkeypatch.setattr("app.mcps.gateway.subprocess.run", fake_run)

    with pytest.raises(RuntimeError, match="MCP command failed"):
        McpGateway().call_command("node server.js", "tools/list", {})


def test_mcp_gateway_call_url_posts_json_rpc(monkeypatch):
    captured = {}

    class FakeResponse:
        def __enter__(self):
            return self

        def __exit__(self, exc_type, exc, traceback):
            return False

        def read(self):
            return b'{"jsonrpc":"2.0","id":2,"result":{"tools":[]}}'

    def fake_urlopen(request, timeout):
        captured["url"] = request.full_url
        captured["body"] = request.data.decode("utf-8")
        captured["content_type"] = request.headers["Content-type"]
        captured["timeout"] = timeout
        return FakeResponse()

    monkeypatch.setattr("app.mcps.gateway.urlopen", fake_urlopen)

    response = McpGateway().call_url("https://mcp.example.com", "tools/list", {}, request_id=2, timeout_seconds=4)

    assert captured["url"] == "https://mcp.example.com"
    assert '"method": "tools/list"' in captured["body"]
    assert captured["content_type"] == "application/json"
    assert captured["timeout"] == 4
    assert response == {"jsonrpc": "2.0", "id": 2, "result": {"tools": []}}


def test_mcp_gateway_call_url_rejects_invalid_json(monkeypatch):
    class FakeResponse:
        def __enter__(self):
            return self

        def __exit__(self, exc_type, exc, traceback):
            return False

        def read(self):
            return b"not-json"

    monkeypatch.setattr("app.mcps.gateway.urlopen", lambda request, timeout: FakeResponse())

    with pytest.raises(RuntimeError, match="MCP URL returned invalid JSON"):
        McpGateway().call_url("https://mcp.example.com", "tools/list", {})


def test_mcp_gateway_inspect_command_sends_initialize_then_tools_list(monkeypatch):
    captured = {}

    def fake_run(args, input, text, capture_output, timeout, shell):
        captured.update({"args": args, "input": input, "shell": shell, "timeout": timeout})

        class Result:
            returncode = 0
            stdout = (
                '{"jsonrpc":"2.0","id":1,"result":{"serverInfo":{"name":"filesystem","version":"1.0"}}}\n'
                '{"jsonrpc":"2.0","id":2,"result":{"tools":[{"name":"read_file","description":"Read a file"}]}}\n'
            )
            stderr = ""

        return Result()

    monkeypatch.setattr("app.mcps.gateway.subprocess.run", fake_run)

    inspection = McpGateway().inspect_command('node "server.js"', timeout_seconds=5)

    assert captured["args"] == ["node", "server.js"]
    assert captured["shell"] is False
    stdin_lines = [line for line in captured["input"].splitlines() if line.strip()]
    assert len(stdin_lines) == 3
    assert '"method": "initialize"' in stdin_lines[0]
    assert "notifications/initialized" in stdin_lines[1]
    assert '"method": "tools/list"' in stdin_lines[2]
    assert inspection["server_info"] == {"serverInfo": {"name": "filesystem", "version": "1.0"}}
    assert inspection["tools"] == [{"name": "read_file", "description": "Read a file"}]


def test_mcp_gateway_inspect_command_requires_initialize_response(monkeypatch):
    def fake_run(*args, **kwargs):
        class Result:
            returncode = 0
            stdout = '{"jsonrpc":"2.0","id":2,"result":{"tools":[]}}\n'
            stderr = ""

        return Result()

    monkeypatch.setattr("app.mcps.gateway.subprocess.run", fake_run)

    with pytest.raises(RuntimeError, match="did not respond to initialize"):
        McpGateway().inspect_command("node server.js")


def test_mcp_gateway_inspect_url_propagates_session_header(monkeypatch):
    requests = []

    class FakeResponse:
        def __init__(self, body, session_id):
            self._body = body
            self.headers = {"Mcp-Session-Id": session_id} if session_id else {}

        def __enter__(self):
            return self

        def __exit__(self, exc_type, exc, traceback):
            return False

        def read(self):
            return self._body

    def fake_urlopen(request, timeout):
        requests.append({"url": request.full_url, "body": request.data.decode("utf-8"), "headers": dict(request.headers)})
        if len(requests) == 1:
            return FakeResponse(b'{"jsonrpc":"2.0","id":1,"result":{"serverInfo":{"name":"remote"}}}', "session-123")
        if len(requests) == 2:
            return FakeResponse(b"", None)
        return FakeResponse(b'{"jsonrpc":"2.0","id":2,"result":{"tools":[]}}', None)

    monkeypatch.setattr("app.mcps.gateway.urlopen", fake_urlopen)

    inspection = McpGateway().inspect_url("https://mcp.example.com")

    assert len(requests) == 3
    assert '"method": "initialize"' in requests[0]["body"]
    assert "notifications/initialized" in requests[1]["body"]
    assert '"method": "tools/list"' in requests[2]["body"]
    assert "session-123" not in requests[0]["headers"].values()
    assert "session-123" in requests[1]["headers"].values()
    assert "session-123" in requests[2]["headers"].values()
    assert inspection == {"server_info": {"serverInfo": {"name": "remote"}}, "tools": []}


def test_validate_url_accepts_public_http_urls():
    assert validate_url("https://mcp.example.com/rpc") == "https://mcp.example.com/rpc"


def test_validate_url_rejects_non_http_schemes():
    with pytest.raises(ValueError, match="Only HTTP and HTTPS MCP URLs are allowed"):
        validate_url("file:///etc/passwd")


def test_validate_url_rejects_loopback_and_private_hosts():
    for url in ["http://localhost:8080", "http://127.0.0.1:8080", "http://10.0.0.5/rpc", "http://192.168.1.2/rpc"]:
        with pytest.raises(ValueError, match="Private or local MCP URLs are not allowed"):
            validate_url(url)
