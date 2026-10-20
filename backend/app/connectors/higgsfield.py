"""Higgsfield connector: remote MCP server (https://mcp.higgsfield.ai/mcp) with OAuth 2.0.

The server requires a Bearer access token (scopes: openid email offline_access).
Authentication uses the authorization-code flow with PKCE and dynamic client
registration; refresh tokens are stored so expired access tokens renew silently.
Credentials are persisted as a JSON blob ({"access_token", "refresh_token",
"expires_at", "client_id"}) inside the encrypted connector account.
"""

import base64
import hashlib
import json
import secrets
import time
from urllib.error import HTTPError
from urllib.parse import urlencode
from urllib.request import Request, urlopen

from ..agent.tools.base import Tool, ToolResult, ToolSpec

MCP_URL = "https://mcp.higgsfield.ai/mcp"
ISSUER = "https://mcp.higgsfield.ai"
AUTHORIZE_ENDPOINT = f"{ISSUER}/oauth2/authorize"
TOKEN_ENDPOINT = f"{ISSUER}/oauth2/token"
REGISTER_ENDPOINT = f"{ISSUER}/oauth2/register"
OAUTH_SCOPES = "openid email offline_access"
CLIENT_NAME = "obsygpt"
STATE_TTL_SECONDS = 600
MCP_MAX_TOOLS = 10
MAX_OUTPUT_CHARS = 20000
TOKEN_EXPIRY_MARGIN_SECONDS = 60
CLIENT_CACHE_TTL_SECONDS = 3600
MODEL_CATALOG_TTL_SECONDS = 3600
PRIORITY_TOOL_NAMES = [
    "use_higgsfield",
    "generate_video",
    "generate_image",
    "generate_audio",
    "generate_video_batch",
    "generate_image_batch",
    "generate_audio_batch",
    "job_status",
    "show_generations",
    "balance",
]
_video_models_cache: tuple[float, list[str]] | None = None

_client_cache: dict[str, tuple[float, dict]] = {}


def _http_post_json(url: str, payload: dict, headers: dict | None = None, timeout: int = 20) -> tuple[dict, dict]:
    request_headers = {"Content-Type": "application/json", "Accept": "application/json"}
    if headers:
        request_headers.update(headers)
    request = Request(url, data=json.dumps(payload).encode("utf-8"), headers=request_headers, method="POST")
    try:
        with urlopen(request, timeout=timeout) as response:
            response_headers = dict(response.headers.items())
            raw = response.read().decode("utf-8", errors="replace")
    except HTTPError as error:
        detail = error.read().decode("utf-8", errors="replace")[:300]
        raise RuntimeError(f"Higgsfield request {error.code}: {detail}") from error
    return _parse_json_body(raw), response_headers


def _parse_json_body(raw: str) -> dict:
    stripped = raw.strip()
    if not stripped:
        return {}
    if stripped.startswith("{") or stripped.startswith("["):
        try:
            parsed = json.loads(stripped)
            return parsed if isinstance(parsed, dict) else {}
        except json.JSONDecodeError as error:
            raise RuntimeError("Higgsfield returned invalid JSON.") from error
    for line in raw.splitlines():
        line = line.strip()
        if line.startswith("data:"):
            try:
                parsed = json.loads(line[5:].strip())
                if isinstance(parsed, dict):
                    return parsed
            except json.JSONDecodeError:
                continue
    raise RuntimeError("Higgsfield returned an unreadable response.")


def register_client(redirect_uri: str) -> dict:
    """Dynamically registers an OAuth client (RFC 7591) and caches it per redirect URI."""
    cached = _client_cache.get(redirect_uri)
    if cached and time.monotonic() - cached[0] < CLIENT_CACHE_TTL_SECONDS:
        return cached[1]
    payload = {
        "client_name": CLIENT_NAME,
        "redirect_uris": [redirect_uri],
        "grant_types": ["authorization_code", "refresh_token"],
        "response_types": ["code"],
        "token_endpoint_auth_method": "none",
    }
    client, _ = _http_post_json(REGISTER_ENDPOINT, payload)
    if not client.get("client_id"):
        raise RuntimeError("Higgsfield client registration did not return a client_id.")
    _client_cache[redirect_uri] = (time.monotonic(), client)
    return client


def create_pkce_pair() -> tuple[str, str]:
    """Returns (code_verifier, code_challenge) using the S256 method (RFC 7636)."""
    verifier = secrets.token_urlsafe(48)
    digest = hashlib.sha256(verifier.encode("ascii")).digest()
    challenge = base64.urlsafe_b64encode(digest).decode("ascii").rstrip("=")
    return verifier, challenge


def build_authorization_url(client_id: str, redirect_uri: str, state: str, code_challenge: str) -> str:
    params = {
        "response_type": "code",
        "client_id": client_id,
        "redirect_uri": redirect_uri,
        "scope": OAUTH_SCOPES,
        "state": state,
        "code_challenge": code_challenge,
        "code_challenge_method": "S256",
    }
    return f"{AUTHORIZE_ENDPOINT}?{urlencode(params)}"


def _token_request(form: dict) -> dict:
    request = Request(
        TOKEN_ENDPOINT,
        data=urlencode(form).encode("ascii"),
        headers={"Content-Type": "application/x-www-form-urlencoded", "Accept": "application/json"},
        method="POST",
    )
    try:
        with urlopen(request, timeout=20) as response:
            raw = response.read().decode("utf-8", errors="replace")
    except HTTPError as error:
        detail = error.read().decode("utf-8", errors="replace")[:300]
        raise RuntimeError(f"Higgsfield token endpoint {error.code}: {detail}") from error
    return _parse_json_body(raw)


def exchange_code(code: str, code_verifier: str, client_id: str, redirect_uri: str) -> dict:
    return _token_request(
        {
            "grant_type": "authorization_code",
            "code": code,
            "code_verifier": code_verifier,
            "client_id": client_id,
            "redirect_uri": redirect_uri,
        }
    )


def refresh_access_token(refresh_token: str, client_id: str) -> dict:
    return _token_request({"grant_type": "refresh_token", "refresh_token": refresh_token, "client_id": client_id})


def dump_credentials(access_token: str, refresh_token: str, expires_in: int, client_id: str = "") -> str:
    return json.dumps(
        {
            "access_token": access_token,
            "refresh_token": refresh_token,
            "expires_at": time.time() + int(expires_in or 3600) - TOKEN_EXPIRY_MARGIN_SECONDS,
            "client_id": client_id,
        }
    )


def load_credentials(blob: str) -> dict:
    if not blob:
        return {}
    try:
        parsed = json.loads(blob)
    except json.JSONDecodeError:
        return {"access_token": blob} if blob.strip() else {}
    return parsed if isinstance(parsed, dict) else {}


def _persist_refreshed_credentials(user_id: int | None, creds: dict) -> None:
    if user_id is None:
        return
    try:
        from .crypto import encrypt_credential
        from .store import ConnectorStore

        ConnectorStore().update_credentials(user_id, "higgsfield", encrypt_credential(json.dumps(creds)))
    except Exception:  # noqa: BLE001 - persistence of the refreshed token is best-effort
        pass


def _ensure_fresh_access_token(creds: dict, user_id: int | None = None) -> str:
    access_token = str(creds.get("access_token", "")).strip()
    if not access_token:
        raise RuntimeError("No Higgsfield access token stored.")
    expires_at = creds.get("expires_at")
    if not isinstance(expires_at, (int, float)) or time.time() < float(expires_at):
        return access_token
    refresh_token = str(creds.get("refresh_token", "")).strip()
    if not refresh_token:
        return access_token
    client_id = str(creds.get("client_id", "")).strip()
    refreshed = refresh_access_token(refresh_token, client_id)
    if refreshed.get("error"):
        raise RuntimeError(f"Higgsfield token refresh failed: {refreshed['error']}")
    creds["access_token"] = str(refreshed.get("access_token", access_token))
    if refreshed.get("refresh_token"):
        creds["refresh_token"] = str(refreshed["refresh_token"])
    creds["expires_at"] = time.time() + int(refreshed.get("expires_in") or 3600) - TOKEN_EXPIRY_MARGIN_SECONDS
    _persist_refreshed_credentials(user_id, creds)
    return str(creds["access_token"])


def _mcp_post(payload: dict, access_token: str, session_id: str | None = None, timeout: int = 30) -> tuple[dict, str | None]:
    headers = {
        "Content-Type": "application/json",
        "Accept": "application/json, text/event-stream",
        "Authorization": f"Bearer {access_token}",
        "User-Agent": "obsygpt",
    }
    if session_id:
        headers["Mcp-Session-Id"] = session_id
    request = Request(MCP_URL, data=json.dumps(payload).encode("utf-8"), headers=headers, method="POST")
    try:
        with urlopen(request, timeout=timeout) as response:
            raw = response.read().decode("utf-8", errors="replace")
            new_session = response.headers.get("Mcp-Session-Id") or response.headers.get("mcp-session-id")
    except HTTPError as error:
        detail = error.read().decode("utf-8", errors="replace")[:300]
        raise RuntimeError(f"Higgsfield MCP {error.code}: {detail}") from error
    return _parse_json_body(raw), new_session


def _mcp_session(access_token: str) -> str | None:
    initialize = {
        "jsonrpc": "2.0",
        "id": 1,
        "method": "initialize",
        "params": {
            "protocolVersion": "2024-11-05",
            "capabilities": {},
            "clientInfo": {"name": CLIENT_NAME, "version": "1.0.0"},
        },
    }
    response, session_id = _mcp_post(initialize, access_token)
    if response.get("error"):
        raise RuntimeError(f"Higgsfield MCP initialize failed: {response['error'].get('message', 'unknown error')}")
    _mcp_post({"jsonrpc": "2.0", "method": "notifications/initialized"}, access_token, session_id)
    return session_id


def mcp_list_tools(access_token: str) -> list[dict]:
    session_id = _mcp_session(access_token)
    response, _ = _mcp_post({"jsonrpc": "2.0", "id": 2, "method": "tools/list", "params": {}}, access_token, session_id)
    if response.get("error"):
        raise RuntimeError(f"Higgsfield MCP tools/list failed: {response['error'].get('message', 'unknown error')}")
    tools = response.get("result", {}).get("tools", [])
    return tools if isinstance(tools, list) else []


def mcp_call_tool(access_token: str, name: str, arguments: dict) -> str:
    session_id = _mcp_session(access_token)
    response, _ = _mcp_post(
        {"jsonrpc": "2.0", "id": 3, "method": "tools/call", "params": {"name": name, "arguments": arguments}},
        access_token,
        session_id,
    )
    if response.get("error"):
        raise RuntimeError(str(response["error"].get("message", "unknown MCP error")))
    result = response.get("result", {})
    if result.get("isError"):
        text = "\n".join(part.get("text", "") for part in result.get("content", []) if isinstance(part, dict))
        raise RuntimeError(text or "Higgsfield MCP tool reported an error")
    content = result.get("content", [])
    text = "\n".join(part.get("text", "") for part in content if isinstance(part, dict) and part.get("type") == "text")
    return text or json.dumps(result)


class HiggsfieldMcpTool:
    def __init__(self, spec: ToolSpec, original_name: str, creds: dict, user_id: int | None = None):
        self.spec = spec
        self.original_name = original_name
        self.creds = creds
        self.user_id = user_id

    def run(self, args: dict) -> ToolResult:
        try:
            access_token = _ensure_fresh_access_token(self.creds, self.user_id)
            output = mcp_call_tool(access_token, self.original_name, args)
        except Exception as error:  # noqa: BLE001
            return ToolResult(ok=False, output=f"{self.spec.name} failed: {error}")
        return ToolResult(ok=True, output=output[:MAX_OUTPUT_CHARS])


def _video_model_ids(access_token: str) -> list[str]:
    """Best-effort fetch of video-capable model IDs for the tool description."""
    global _video_models_cache
    now = time.monotonic()
    if _video_models_cache and now - _video_models_cache[0] < MODEL_CATALOG_TTL_SECONDS:
        return _video_models_cache[1]
    ids: list[str] = []
    try:
        raw = mcp_call_tool(access_token, "models_explore", {"action": "list"})
        # The tool output can contain several concatenated JSON documents; the
        # model catalog may be split across them.
        for line in raw.splitlines():
            line = line.strip()
            if not line:
                continue
            try:
                parsed = json.loads(line)
            except json.JSONDecodeError:
                continue
            if isinstance(parsed, dict) and isinstance(parsed.get("items"), list):
                ids.extend(str(item.get("id")) for item in parsed["items"] if item.get("output_type") == "video" and item.get("id"))
    except Exception:  # noqa: BLE001 - the description works without the catalog
        ids = []
    _video_models_cache = (now, ids)
    return ids


class HiggsfieldMcpCallTool:
    """Stable-name entry point: calls any Higgsfield MCP tool by name.

    The permission system grants tools per agent by exact name, so a dynamic
    discovery connector must expose one stable tool; discovered tool names are
    listed in the description so the model knows what it can call.
    """

    def __init__(self, creds: dict, user_id: int | None = None, discovered_names: list[str] | None = None, video_models: list[str] | None = None):
        names = ", ".join(discovered_names or [])
        listing = f"Herramientas disponibles: {names}. " if names else ""
        models = f"IDs de modelos de video (params.model, obligatorio): {', '.join(video_models)}. " if video_models else "params.model es obligatorio; consulta los IDs con models_explore(action='list'). "
        self.spec = ToolSpec(
            name="higgsfield_mcp_call",
            description=(
                "Genera con la APP de Higgsfield (gasta CREDITOS de la app, NO dolares). Solo para presets y modelos exclusivos de la app. "
                "Para generacion normal usa higgsfield_api_generate_video / higgsfield_api_generate_image (billing en dolares). "
                f"{listing}{models}Para generate_video los argumentos van anidados en \"params\" (ej. {{\"params\": {{\"model\": \"<id>\", \"prompt\": \"...\"}}}}); "
                "si pasas los argumentos al nivel superior, se envuelven en params automaticamente."
            )[:600],
            parameters='{"tool": "generate_video", "prompt": "un gato astronauta", "model": "soul_2"}',
            permission="sensitive",
        )
        self.creds = creds
        self.user_id = user_id

    def run(self, args: dict) -> ToolResult:
        tool = str(args.get("tool", "")).strip()
        if "arguments" in args:
            arguments = _coerce_arguments(args.get("arguments"))
            if arguments is None:
                return ToolResult(ok=False, output="Invalid arguments: expected a JSON object (or a JSON-encoded object string) in 'arguments'.")
        else:
            arguments = {key: value for key, value in args.items() if key not in ("tool", "arguments")}
            if not tool and "prompt" in arguments:
                tool = "generate_video"
            if not arguments:
                return ToolResult(ok=False, output="Missing arguments: pass 'arguments' as a JSON object, or tool parameters at the top level (e.g. {\"tool\": \"generate_video\", \"prompt\": \"...\"}).")
        if not tool:
            return ToolResult(ok=False, output="Missing required argument: tool")
        if tool == "generate_video" and isinstance(arguments, dict) and "params" not in arguments:
            context = arguments.pop("context", None)
            body: dict = {"params": arguments}
            if context:
                body["context"] = str(context)[:300]
            arguments = body
        try:
            access_token = _ensure_fresh_access_token(self.creds, self.user_id)
            output = mcp_call_tool(access_token, tool, arguments)
        except Exception as error:  # noqa: BLE001
            return ToolResult(ok=False, output=f"higgsfield_mcp_call failed: {error}")
        return ToolResult(ok=True, output=output[:MAX_OUTPUT_CHARS])


def _coerce_arguments(raw: object) -> dict | None:
    """Accepts a dict or a JSON/Python-dict-encoded string; LLMs often stringify nested objects."""
    if isinstance(raw, dict):
        return raw
    if isinstance(raw, str):
        text = raw.strip()
        if not text:
            return {}
        try:
            parsed = json.loads(text)
            return parsed if isinstance(parsed, dict) else None
        except json.JSONDecodeError:
            pass
        try:
            import ast

            parsed = ast.literal_eval(text)
            return parsed if isinstance(parsed, dict) else None
        except (ValueError, SyntaxError):
            return None
    return None


def test_token(blob: str) -> dict:
    creds = load_credentials(blob)
    access_token = _ensure_fresh_access_token(creds)
    tools = mcp_list_tools(access_token)
    return {"ok": True, "detail": f"Higgsfield MCP con {len(tools)} herramientas disponibles"}


def build_tools(blob: str, user_id: int | None = None) -> list[Tool]:
    creds = load_credentials(blob)
    if not str(creds.get("access_token", "")).strip():
        return [HiggsfieldMcpCallTool(creds, user_id)]
    discovered: list[dict] = []
    try:
        access_token = _ensure_fresh_access_token(creds, user_id)
        discovered = mcp_list_tools(access_token)[:MCP_MAX_TOOLS]
    except Exception:  # noqa: BLE001 - discovery is best-effort; the stable tool still works per-call
        pass
    from .bridge import _sanitize_tool_name

    tools: list[Tool] = []
    for mcp_tool in discovered:
        name = str(mcp_tool.get("name", "")).strip()
        if not name:
            continue
        description = str(mcp_tool.get("description", "") or f"Higgsfield tool {name}")[:200]
        schema = mcp_tool.get("inputSchema")
        parameters = json.dumps(schema)[:500] if isinstance(schema, dict) else "{}"
        spec = ToolSpec(
            name=f"higgsfield_{_sanitize_tool_name(name)}",
            description=description,
            parameters=parameters,
            permission="sensitive",
        )
        tools.append(HiggsfieldMcpTool(spec, name, dict(creds), user_id))
    discovered_names = [str(mcp_tool.get("name", "")).strip() for mcp_tool in discovered if mcp_tool.get("name")]
    ordered_names = [name for name in PRIORITY_TOOL_NAMES if name in discovered_names]
    ordered_names += [name for name in discovered_names if name not in ordered_names]
    tools.append(HiggsfieldMcpCallTool(creds, user_id, ordered_names, _video_model_ids(access_token)))
    return tools
