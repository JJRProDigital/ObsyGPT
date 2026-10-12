"""Bridge registering connector tools and MCP server tools into agent tool registries."""

import json
import re
import time

from ..agent.tools.base import Tool, ToolRegistry, ToolResult, ToolSpec
from ..db import connect
from ..mcps.gateway import McpGateway
from .catalog import CONNECTOR_DEFINITIONS
from .crypto import decrypt_credential
from .store import ConnectorStore

MCP_INSPECT_TTL_SECONDS = 300
MCP_MAX_TOOLS_PER_SERVER = 10
MCP_TOOL_OUTPUT_LIMIT = 10000

_inspect_cache: dict[str, tuple[float, list[dict] | None]] = {}


def _sanitize_tool_name(*parts: str) -> str:
    joined = "_".join(part for part in parts if part)
    collapsed = re.sub(r"[^a-z0-9_]+", "_", joined.lower())
    return re.sub(r"_+", "_", collapsed).strip("_")[:80]


def register_connector_tools(registry: ToolRegistry, user_id: int) -> None:
    store = ConnectorStore()
    for slug in store.connected_slugs(user_id):
        definition = CONNECTOR_DEFINITIONS.get(slug)
        if not definition:
            continue
        encrypted = store.get_credential(user_id, slug)
        if not encrypted:
            continue
        try:
            token = decrypt_credential(encrypted)
        except ValueError:
            continue
        registry.register_many(definition.build_tools(token))


def _assigned_mcp_servers(agent_id: int) -> list[dict]:
    with connect() as connection:
        with connection.cursor() as cursor:
            cursor.execute(
                """
                SELECT s.id, s.name, s.connection_type, s.command, s.url
                FROM mcp_servers s
                JOIN agent_mcps am ON am.mcp_server_id = s.id
                WHERE am.agent_id = %s AND s.enabled = true
                ORDER BY s.name;
                """,
                (agent_id,),
            )
            columns = [column.name for column in cursor.description]
            return [dict(zip(columns, row)) for row in cursor.fetchall()]


def _cached_inspection(server: dict) -> list[dict] | None:
    cache_key = f"{server['id']}:{server.get('command') or server.get('url')}"
    now = time.monotonic()
    cached = _inspect_cache.get(cache_key)
    if cached and now - cached[0] < MCP_INSPECT_TTL_SECONDS:
        return cached[1]
    gateway = McpGateway()
    try:
        if server["connection_type"] == "command":
            inspection = gateway.inspect_command(server["command"], timeout_seconds=15)
        else:
            inspection = gateway.inspect_url(server["url"], timeout_seconds=15)
        tools = inspection.get("tools", [])[:MCP_MAX_TOOLS_PER_SERVER]
    except Exception:  # noqa: BLE001
        tools = None
    _inspect_cache[cache_key] = (now, tools)
    return tools


class McpAgentTool:
    def __init__(self, spec: ToolSpec, server: dict, original_name: str):
        self.spec = spec
        self.server = server
        self.original_name = original_name

    def run(self, args: dict) -> ToolResult:
        gateway = McpGateway()
        params = {"name": self.original_name, "arguments": args}
        try:
            if self.server["connection_type"] == "command":
                response = gateway.call_command(self.server["command"], "tools/call", params, timeout_seconds=30)
            else:
                response = gateway.call_url(self.server["url"], "tools/call", params, timeout_seconds=30)
        except Exception as error:  # noqa: BLE001
            return ToolResult(ok=False, output=f"{self.spec.name} failed: {error}")
        if "error" in response:
            return ToolResult(ok=False, output=f"{self.spec.name} error: {response['error'].get('message', 'unknown MCP error')}")
        result = response.get("result", {})
        if result.get("isError"):
            text = "\n".join(part.get("text", "") for part in result.get("content", []) if isinstance(part, dict))
            return ToolResult(ok=False, output=f"{self.spec.name} error: {text or 'MCP tool reported an error'}")
        content = result.get("content", [])
        text = "\n".join(part.get("text", "") for part in content if isinstance(part, dict) and part.get("type") == "text")
        return ToolResult(ok=True, output=(text or json.dumps(result))[:MCP_TOOL_OUTPUT_LIMIT])


def register_mcp_agent_tools(registry: ToolRegistry, agent_id: int) -> None:
    for server in _assigned_mcp_servers(agent_id):
        tools = _cached_inspection(server)
        if not tools:
            continue
        server_slug = _sanitize_tool_name("mcp", server["name"])
        for mcp_tool in tools:
            tool_name = mcp_tool.get("name", "")
            if not tool_name:
                continue
            description = str(mcp_tool.get("description", "") or f"MCP tool {tool_name} from {server['name']}")[:200]
            input_schema = mcp_tool.get("inputSchema")
            parameters = json.dumps(input_schema)[:500] if isinstance(input_schema, dict) else "{}"
            spec = ToolSpec(
                name=f"{server_slug}_{_sanitize_tool_name(tool_name)}",
                description=description,
                parameters=parameters,
                permission="sensitive",
            )
            registry.register(McpAgentTool(spec, server, tool_name))
