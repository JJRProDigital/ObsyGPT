"""Bridge registering connector tools and MCP server tools into agent tool registries."""

import json
import logging
import os
import re
import time

from ..agent.tools.base import Permission, Tool, ToolRegistry, ToolResult, ToolSpec
from ..db import connect
from ..mcps.gateway import McpGateway
from .catalog import CONNECTOR_DEFINITIONS
from .crypto import decrypt_credential
from .store import ConnectorStore

MCP_INSPECT_TTL_SECONDS = 300
# A failed inspection (server mid-restart) must not poison tool registration for the
# full TTL: retry quickly so MCP tools reappear as soon as the server answers again.
MCP_INSPECT_FAILURE_TTL_SECONDS = 15
MCP_MAX_TOOLS_PER_SERVER = 16
MCP_TOOL_OUTPUT_LIMIT = 10000
# Image-generation MCPs (and other slow tools) can raise this via MCP_TOOL_TIMEOUT.
MCP_TOOL_CALL_TIMEOUT = int(os.getenv("MCP_TOOL_TIMEOUT", "180"))
# Appended to failed MCP tool outputs: the model must report the real error instead
# of fabricating plausible-looking results (seen with Apify actor validation errors).
NO_FABRICATION_REMINDER = (
    "(Importante: NO inventes datos. Los unicos resultados validos son los de TOOL RESULT; "
    "si no hay datos, informa del fallo al usuario con el error real.)"
)

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
        if definition.auth_type == "oauth":
            registry.register_many(definition.build_tools(token, user_id=user_id))
        else:
            registry.register_many(definition.build_tools(token))


def _assigned_mcp_servers(agent_id: int) -> list[dict]:
    with connect() as connection:
        with connection.cursor() as cursor:
            cursor.execute(
                """
                SELECT s.id, s.name, s.connection_type, s.command, s.url, s.tool_permission
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
    if cached:
        ttl = MCP_INSPECT_TTL_SECONDS if cached[1] is not None else MCP_INSPECT_FAILURE_TTL_SECONDS
        if now - cached[0] < ttl:
            return cached[1]
    gateway = McpGateway()
    try:
        if server["connection_type"] == "command":
            inspection = gateway.inspect_command(server["command"], timeout_seconds=15)
        else:
            inspection = gateway.inspect_url(server["url"], timeout_seconds=15)
        tools = inspection.get("tools", [])[:MCP_MAX_TOOLS_PER_SERVER]
    except Exception as error:  # noqa: BLE001
        tools = None
        logging.getLogger("obsygpt.connectors.bridge").warning(
            "MCP inspection failed for %s (%s): %s", server["name"], server.get("url") or server.get("command"), error
        )
    _inspect_cache[cache_key] = (now, tools)
    return tools


def _inline_image_markdown(text: str) -> str:
    """Flow tool outputs list /data/images paths; rewrite each to its workspace path
    plus a ready-to-paste inline markdown link (the chat only renders
    /api/workspace-image and https URLs)."""
    def repl(match: re.Match) -> str:
        name = match.group(1)
        workspace_path = f"/data/workspace/flow-images/{name}"
        return f"{workspace_path}\n![image](/api/workspace-image?path={workspace_path})"

    return re.sub(r"/data/images/([\w.-]+\.(?:jpe?g|png|webp|gif))", repl, text)


def _strip_empty_tool_values(args: dict) -> dict:
    """Drops empty-string and None values recursively: actors treat absent fields
    as 'use the default', while "" often fails pattern/enum validation (Apify
    Google Maps actors reject minRating: "" with 'Input validation failed')."""
    cleaned: dict = {}
    for key, value in args.items():
        if isinstance(value, dict):
            cleaned[key] = _strip_empty_tool_values(value)
        elif value is None or (isinstance(value, str) and not value.strip()):
            continue
        else:
            cleaned[key] = value
    return cleaned


class McpAgentTool:
    def __init__(self, spec: ToolSpec, server: dict, original_name: str):
        self.spec = spec
        self.server = server
        self.original_name = original_name

    def run(self, args: dict) -> ToolResult:
        gateway = McpGateway()
        params = {
            "name": self.original_name,
            "arguments": _strip_empty_tool_values(args) if isinstance(args, dict) else args,
        }
        try:
            if self.server["connection_type"] == "command":
                response = gateway.call_command(self.server["command"], "tools/call", params, timeout_seconds=MCP_TOOL_CALL_TIMEOUT)
            else:
                response = gateway.call_url(self.server["url"], "tools/call", params, timeout_seconds=MCP_TOOL_CALL_TIMEOUT)
        except Exception as error:  # noqa: BLE001
            return ToolResult(ok=False, output=f"{self.spec.name} failed: {error} {NO_FABRICATION_REMINDER}")
        if "error" in response:
            return ToolResult(
                ok=False,
                output=f"{self.spec.name} error: {response['error'].get('message', 'unknown MCP error')} {NO_FABRICATION_REMINDER}",
            )
        result = response.get("result", {})
        if result.get("isError"):
            text = "\n".join(part.get("text", "") for part in result.get("content", []) if isinstance(part, dict))
            return ToolResult(ok=False, output=f"{self.spec.name} error: {text or 'MCP tool reported an error'} {NO_FABRICATION_REMINDER}")
        content = result.get("content", [])
        text = "\n".join(part.get("text", "") for part in content if isinstance(part, dict) and part.get("type") == "text")
        return ToolResult(ok=True, output=_inline_image_markdown(text or json.dumps(result))[:MCP_TOOL_OUTPUT_LIMIT])


def register_mcp_agent_tools(registry: ToolRegistry, agent_id: int) -> list[str]:
    """Registers tools of the MCP servers assigned to the agent; returns their names.

    Assignment of a server to the agent is the grant: callers must include these
    tools regardless of per-tool permission rows. Servers register as sensitive by
    default (each call needs approval), but an admin can mark a whole server as
    `tool_permission='safe'` so its tools run in headless readonly runs (daily
    briefs) without pausing. Tool names stay short (the MCP tool's own name) when
    unique: smaller models flub long names like mcp_google_flow_flow_upload_file.
    """
    registered: list[str] = []
    for server in _assigned_mcp_servers(agent_id):
        tools = _cached_inspection(server)
        if not tools:
            continue
        server_slug = _sanitize_tool_name("mcp", server["name"])
        permission: Permission = "safe" if server.get("tool_permission") == "safe" else "sensitive"
        for mcp_tool in tools:
            tool_name = mcp_tool.get("name", "")
            if not tool_name:
                continue
            short_name = _sanitize_tool_name(tool_name)
            full_name = f"{server_slug}_{short_name}"
            spec_name = short_name if short_name not in registry._tools else full_name
            description = str(mcp_tool.get("description", "") or f"MCP tool {tool_name} from {server['name']}")[:200]
            if re.search(r"image|file|photo|imagen", f"{description} {tool_name}", re.I):
                # Tool outputs with container paths are invisible to the user: teach the
                # model to embed workspace images inline (same-origin, session-authenticated).
                description += (
                    " Output paths are inside the container. To show a generated image to the"
                    " user, embed it inline in your reply as"
                    " ![image](/api/workspace-image?path=<absolute path>)."
                )
            input_schema = mcp_tool.get("inputSchema")
            parameters = json.dumps(input_schema)[:500] if isinstance(input_schema, dict) else "{}"
            spec = ToolSpec(
                name=spec_name,
                description=description,
                parameters=parameters,
                permission=permission,
            )
            registry.register(McpAgentTool(spec, server, tool_name))
            registered.append(spec_name)
    return registered
