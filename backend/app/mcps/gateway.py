from dataclasses import dataclass
import json
import shlex
import subprocess
from typing import Literal
from urllib.error import HTTPError
from urllib.request import Request, urlopen

from ..url_safety import UnsafeUrlError, validate_public_url

# Streamable HTTP MCP servers (e.g. https://mcp.apify.com) reject requests that do not
# accept both content types, and answer single RPC calls framed as SSE `data:` events.
MCP_STREAMABLE_HTTP_ACCEPT = "application/json, text/event-stream"


def _extract_rpc_payloads(raw_body: str) -> list[dict]:
    """Parses a JSON or SSE-framed MCP response body into its JSON-RPC payloads."""
    try:
        payload = json.loads(raw_body)
    except json.JSONDecodeError:
        payloads = []
        for line in raw_body.splitlines():
            line = line.strip()
            if not line.startswith("data:"):
                continue
            try:
                payload = json.loads(line[len("data:"):].strip())
            except json.JSONDecodeError:
                continue
            if isinstance(payload, dict):
                payloads.append(payload)
        return payloads
    return [payload] if isinstance(payload, dict) else []


def _payloads_as_json_lines(raw_body: str) -> str:
    return "\n".join(json.dumps(payload) for payload in _extract_rpc_payloads(raw_body))


@dataclass(frozen=True)
class McpServerConfig:
    name: str
    description: str
    connection_type: Literal["command", "url"]
    command: str | None
    url: str | None
    enabled: bool


class McpGateway:
    def __init__(self):
        self.servers: list[McpServerConfig] = []

    def register(self, config: McpServerConfig) -> None:
        name = config.name.strip()
        if not name:
            raise ValueError("MCP server name is required.")
        if config.connection_type == "command" and not (config.command and config.command.strip()):
            raise ValueError("Command MCP servers require a command.")
        if config.connection_type == "command" and config.command:
            parse_command(config.command)
        if config.connection_type == "url" and not (config.url and config.url.strip()):
            raise ValueError("URL MCP servers require a URL.")
        if config.connection_type == "url" and config.url:
            validate_url(config.url)
        self.servers.append(config)

    def validate(self, config: McpServerConfig) -> dict:
        name = config.name.strip()
        if not name:
            raise ValueError("MCP server name is required.")
        if config.connection_type == "command":
            if not (config.command and config.command.strip()):
                raise ValueError("Command MCP servers require a command.")
            return {"valid": True, "connection_type": "command", "command_args": parse_command(config.command)}
        if not (config.url and config.url.strip()):
            raise ValueError("URL MCP servers require a URL.")
        return {"valid": True, "connection_type": "url", "url": validate_url(config.url)}

    def list_servers(self) -> list[McpServerConfig]:
        return list(self.servers)

    def call_command(
        self,
        command: str,
        method: str,
        params: dict,
        request_id: int = 1,
        timeout_seconds: int = 10,
    ) -> dict:
        request = {"jsonrpc": "2.0", "id": request_id, "method": method, "params": params}
        result = subprocess.run(
            parse_command(command),
            input=json.dumps(request) + "\n",
            text=True,
            capture_output=True,
            timeout=timeout_seconds,
            shell=False,
        )
        if result.returncode != 0:
            raise RuntimeError(f"MCP command failed: {result.stderr.strip() or result.returncode}")
        try:
            return json.loads(result.stdout.strip())
        except json.JSONDecodeError as error:
            raise RuntimeError("MCP command returned invalid JSON.") from error

    def call_url(
        self,
        url: str,
        method: str,
        params: dict,
        request_id: int = 1,
        timeout_seconds: int = 10,
    ) -> dict:
        target = validate_url(url)
        request_body = json.dumps({"jsonrpc": "2.0", "id": request_id, "method": method, "params": params}).encode("utf-8")
        try:
            raw_body, _ = _post_rpc(target, request_body, timeout_seconds)
        except HTTPError as error:
            if error.code not in (400, 404):
                raise
            # Session-bound streamable HTTP servers (e.g. https://mcp.apify.com) reject
            # stateless single-request calls; open a session and retry with it.
            session_id, _ = _open_session(target, timeout_seconds)
            try:
                raw_body, _ = _post_rpc(target, request_body, timeout_seconds, session_id)
            finally:
                _close_session(target, session_id, timeout_seconds)
        payloads = _extract_rpc_payloads(raw_body)
        if not payloads:
            raise RuntimeError("MCP URL returned invalid JSON.")
        for payload in payloads:
            if payload.get("id") == request_id:
                return payload
        return payloads[-1]

    def inspect_command(self, command: str, timeout_seconds: int = 20) -> dict:
        stdin = "\n".join(
            [
                json.dumps(_initialize_request(1)),
                json.dumps({"jsonrpc": "2.0", "method": "notifications/initialized"}),
                json.dumps({"jsonrpc": "2.0", "id": 2, "method": "tools/list", "params": {}}),
            ]
        ) + "\n"
        result = subprocess.run(
            parse_command(command),
            input=stdin,
            text=True,
            capture_output=True,
            timeout=timeout_seconds,
            shell=False,
        )
        if result.returncode != 0:
            raise RuntimeError(f"MCP command failed: {result.stderr.strip() or result.returncode}")
        return _parse_inspect_output(result.stdout)

    def inspect_url(self, url: str, timeout_seconds: int = 20) -> dict:
        target = validate_url(url)
        session_id, initialize_raw = _open_session(target, timeout_seconds)
        headers = {"Content-Type": "application/json", "Accept": MCP_STREAMABLE_HTTP_ACCEPT}
        if session_id:
            headers["Mcp-Session-Id"] = session_id
        with urlopen(
            Request(
                target,
                data=json.dumps({"jsonrpc": "2.0", "id": 2, "method": "tools/list", "params": {}}).encode("utf-8"),
                headers=headers,
                method="POST",
            ),
            timeout=timeout_seconds,
        ) as tools_response:
            tools_raw = tools_response.read().decode("utf-8")
        return _parse_inspect_output(_payloads_as_json_lines(initialize_raw) + "\n" + _payloads_as_json_lines(tools_raw))


def _post_rpc(url: str, body: bytes | None, timeout_seconds: int, session_id: str | None = None, http_method: str = "POST") -> tuple[str, str | None]:
    headers = {"Content-Type": "application/json", "Accept": MCP_STREAMABLE_HTTP_ACCEPT}
    if session_id:
        headers["Mcp-Session-Id"] = session_id
    request = Request(url, data=body, headers=headers, method=http_method)
    with urlopen(request, timeout=timeout_seconds) as response:
        session = response.headers.get("Mcp-Session-Id") or response.headers.get("mcp-session-id")
        return response.read().decode("utf-8"), session


def _open_session(url: str, timeout_seconds: int) -> tuple[str | None, str]:
    """Runs the initialize + notifications/initialized handshake.

    Returns the granted Mcp-Session-Id (None for stateless servers) and the raw
    initialize response body (needed by inspect_url to surface serverInfo).
    """
    initialize_raw, session_id = _post_rpc(url, json.dumps(_initialize_request(1)).encode("utf-8"), timeout_seconds)
    initialize = next((payload for payload in _extract_rpc_payloads(initialize_raw) if payload.get("id") == 1), None)
    if not initialize:
        raise RuntimeError("MCP server did not respond to initialize.")
    if "error" in initialize:
        raise RuntimeError(f"MCP initialize failed: {initialize['error'].get('message', 'unknown error')}")
    try:
        _post_rpc(url, json.dumps({"jsonrpc": "2.0", "method": "notifications/initialized"}).encode("utf-8"), timeout_seconds, session_id)
    except Exception:  # noqa: BLE001 — the notification is advisory; some servers close early
        pass
    return session_id, initialize_raw


def _close_session(url: str, session_id: str | None, timeout_seconds: int) -> None:
    if not session_id:
        return
    try:
        _post_rpc(url, None, timeout_seconds, session_id, http_method="DELETE")
    except Exception:  # noqa: BLE001 — best-effort session termination
        pass


def _initialize_request(request_id: int) -> dict:
    return {
        "jsonrpc": "2.0",
        "id": request_id,
        "method": "initialize",
        "params": {
            "protocolVersion": "2024-11-05",
            "capabilities": {},
            "clientInfo": {"name": "obsygpt", "version": "1.0.0"},
        },
    }


def _parse_inspect_output(stdout: str) -> dict:
    responses: dict[int, dict] = {}
    for line in stdout.splitlines():
        line = line.strip()
        if not line:
            continue
        try:
            message = json.loads(line)
        except json.JSONDecodeError:
            continue
        if isinstance(message, dict) and message.get("id") in (1, 2):
            responses[message["id"]] = message
    if 1 not in responses:
        raise RuntimeError("MCP server did not respond to initialize.")
    if "error" in responses[1]:
        raise RuntimeError(f"MCP initialize failed: {responses[1]['error'].get('message', 'unknown error')}")
    if 2 not in responses:
        raise RuntimeError("MCP server did not respond to tools/list.")
    if "error" in responses[2]:
        raise RuntimeError(f"MCP tools/list failed: {responses[2]['error'].get('message', 'unknown error')}")
    return {
        "server_info": responses[1].get("result", {}),
        "tools": responses[2].get("result", {}).get("tools", []),
    }


def parse_command(command: str) -> list[str]:
    if not command.strip():
        raise ValueError("Command is required.")

    parts = shlex.split(command, posix=False)
    if any(part in {"&&", "||", ";", "|", ">", ">>", "<"} for part in parts):
        raise ValueError("Shell operators are not allowed in MCP commands.")
    return [part.strip('"') for part in parts]


def validate_url(url: str) -> str:
    try:
        return validate_public_url(url, resolve_dns=False, label="MCP URLs")
    except UnsafeUrlError as error:
        raise ValueError(str(error)) from error
