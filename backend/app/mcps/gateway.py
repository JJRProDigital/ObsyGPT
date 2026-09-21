from dataclasses import dataclass
import ipaddress
import json
import shlex
import subprocess
from typing import Literal
from urllib.parse import urlparse
from urllib.request import Request, urlopen


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
        request_body = json.dumps({"jsonrpc": "2.0", "id": request_id, "method": method, "params": params}).encode("utf-8")
        request = Request(validate_url(url), data=request_body, headers={"Content-Type": "application/json"}, method="POST")
        with urlopen(request, timeout=timeout_seconds) as response:
            raw_body = response.read().decode("utf-8")
        try:
            return json.loads(raw_body)
        except json.JSONDecodeError as error:
            raise RuntimeError("MCP URL returned invalid JSON.") from error

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
        session_id: str | None = None
        with urlopen(
            Request(target, data=json.dumps(_initialize_request(1)).encode("utf-8"), headers={"Content-Type": "application/json"}, method="POST"),
            timeout=timeout_seconds,
        ) as initialize_response:
            session_id = initialize_response.headers.get("Mcp-Session-Id") or initialize_response.headers.get("mcp-session-id")
            initialize_raw = initialize_response.read().decode("utf-8")
        extra_headers = {"Mcp-Session-Id": session_id} if session_id else {}
        with urlopen(
            Request(
                target,
                data=json.dumps({"jsonrpc": "2.0", "method": "notifications/initialized"}).encode("utf-8"),
                headers={"Content-Type": "application/json", **extra_headers},
                method="POST",
            ),
            timeout=timeout_seconds,
        ) as _notification_response:
            _notification_response.read()
        with urlopen(
            Request(
                target,
                data=json.dumps({"jsonrpc": "2.0", "id": 2, "method": "tools/list", "params": {}}).encode("utf-8"),
                headers={"Content-Type": "application/json", **extra_headers},
                method="POST",
            ),
            timeout=timeout_seconds,
        ) as tools_response:
            tools_raw = tools_response.read().decode("utf-8")
        return _parse_inspect_output(initialize_raw + "\n" + tools_raw)


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
    cleaned = url.strip().rstrip("/")
    parsed = urlparse(cleaned)
    if parsed.scheme not in {"http", "https"}:
        raise ValueError("Only HTTP and HTTPS MCP URLs are allowed.")
    if not parsed.hostname:
        raise ValueError("MCP URL host is required.")

    hostname = parsed.hostname.lower()
    if hostname == "localhost" or hostname.endswith(".localhost"):
        raise ValueError("Private or local MCP URLs are not allowed.")
    try:
        address = ipaddress.ip_address(hostname)
    except ValueError:
        return cleaned
    if address.is_private or address.is_loopback or address.is_link_local or address.is_reserved:
        raise ValueError("Private or local MCP URLs are not allowed.")
    return cleaned
