from typing import Annotated, Literal
import json
import os
from pathlib import Path
import re
import shutil

from fastapi import APIRouter, HTTPException, Query, Request
from pydantic import BaseModel, Field, field_validator, model_validator

from ..agent.tools import default_tool_registry
from ..providers.registry import list_provider_models

from ..audit import AuditStore
from ..auth.routes import require_admin, require_user
from ..db import connect
from ..mcps.gateway import McpGateway, McpServerConfig
from ..providers import PROVIDER_DEFINITIONS
from ..skills.runtime import SkillRegistry
from ..traces.store import TraceStore


router = APIRouter(prefix="/api/admin", tags=["admin"])
SKILLS_ROOT = Path(__file__).resolve().parents[3] / "agents" / "skills"
SKILL_NAME_PATTERN = re.compile(r"^[a-zA-Z0-9_-]+$")

ProviderType = Literal[
    "openrouter",
    "openai",
    "anthropic",
    "gemini",
    "ollama",
    "llamacpp",
    "openai_compatible",
]


class ProviderPayload(BaseModel):
    name: str = Field(min_length=1, max_length=100)
    provider_type: ProviderType
    base_url: str | None = None
    api_key_env: str | None = None
    enabled: bool = True

    @field_validator("name")
    @classmethod
    def strip_name(cls, value: str) -> str:
        stripped = value.strip()
        if not stripped:
            raise ValueError("Provider name is required.")
        return stripped


class ModelPayload(BaseModel):
    provider_id: int
    model_name: str = Field(min_length=1, max_length=200)
    display_name: str = Field(min_length=1, max_length=200)
    supports_text: bool = True
    supports_streaming: bool = True
    supports_vision: bool = False
    supports_audio: bool = False
    supports_tools: bool = False
    supports_json: bool = False
    context_window: int | None = Field(default=None, ge=1)
    enabled: bool = True

    @field_validator("model_name", "display_name")
    @classmethod
    def strip_required_text(cls, value: str) -> str:
        stripped = value.strip()
        if not stripped:
            raise ValueError("Value is required.")
        return stripped

    @field_validator("provider_id")
    @classmethod
    def validate_provider_id(cls, value: int) -> int:
        return ensure_positive_id(value, "provider_id")


class AgentPayload(BaseModel):
    name: str = Field(min_length=1, max_length=100)
    description: str = ""
    system_prompt: str = Field(min_length=1)
    provider_id: int | None = None
    model_id: int | None = None
    temperature: float = Field(default=0.7, ge=0, le=2)
    internet_enabled: bool = False
    multimodal_enabled: bool = False
    agentic_mode: bool = False
    enabled: bool = True

    @field_validator("name", "system_prompt")
    @classmethod
    def strip_required_text(cls, value: str) -> str:
        stripped = value.strip()
        if not stripped:
            raise ValueError("Value is required.")
        return stripped


class SkillPayload(BaseModel):
    name: str = Field(min_length=1, max_length=100)
    description: str = ""
    argument_hint: str = ""
    triggers: list[Literal["user", "model"]] = Field(default_factory=lambda: ["user"])
    body: str = "# Instrucciones principales\n1. Describe el flujo de trabajo de la skill.\n\n## Restricciones\n* No ejecutes acciones destructivas sin confirmacion explicita."
    resources: str = ""
    enabled: bool = True

    @field_validator("name")
    @classmethod
    def strip_name(cls, value: str) -> str:
        stripped = value.strip()
        if not stripped:
            raise ValueError("Skill name is required.")
        return stripped

    @field_validator("description", "argument_hint", "body", "resources")
    @classmethod
    def strip_skill_text(cls, value: str) -> str:
        return value.strip()

    @field_validator("triggers")
    @classmethod
    def validate_triggers(cls, value: list[str]) -> list[str]:
        triggers = list(dict.fromkeys(value))
        if not triggers:
            raise ValueError("At least one trigger is required.")
        return triggers


class SkillRunPayload(BaseModel):
    skill_name: Literal["read_url", "web_search"]
    payload: dict


class SkillGeneratePayload(BaseModel):
    prompt: str = Field(min_length=1, max_length=2000)

    @field_validator("prompt")
    @classmethod
    def strip_prompt(cls, value: str) -> str:
        stripped = value.strip()
        if not stripped:
            raise ValueError("Skill generator prompt is required.")
        return stripped


class WorkflowPayload(BaseModel):
    name: str = Field(min_length=1, max_length=100)
    workflow_type: Literal["single_agent", "sequential", "supervisor", "reviewer", "parallel", "debate"]
    agent_ids: list[int] = Field(default_factory=list)
    enabled: bool = True

    @field_validator("name")
    @classmethod
    def strip_name(cls, value: str) -> str:
        stripped = value.strip()
        if not stripped:
            raise ValueError("Workflow name is required.")
        return stripped


class McpServerPayload(BaseModel):
    name: str = Field(min_length=1, max_length=100)
    description: str = ""
    connection_type: Literal["command", "url"]
    command: str | None = None
    url: str | None = None
    enabled: bool = False

    @field_validator("name")
    @classmethod
    def strip_name(cls, value: str) -> str:
        stripped = value.strip()
        if not stripped:
            raise ValueError("MCP server name is required.")
        return stripped

    @model_validator(mode="after")
    def validate_connection(self):
        if self.connection_type == "command" and not (self.command and self.command.strip()):
            raise ValueError("Command MCP servers require a command.")
        if self.connection_type == "url" and not (self.url and self.url.strip()):
            raise ValueError("URL MCP servers require a URL.")
        return self


class McpRunPayload(BaseModel):
    method: str = Field(min_length=1)
    params: dict = Field(default_factory=dict)
    agent_run_id: int | None = Field(default=None, ge=1)

    @field_validator("method")
    @classmethod
    def strip_method(cls, value: str) -> str:
        stripped = value.strip()
        if not stripped:
            raise ValueError("MCP method is required.")
        return stripped


class UserRolePayload(BaseModel):
    role: Literal["admin", "user"]


class PluginInstallPayload(BaseModel):
    source: Literal["local", "marketplace"]
    slug: str = Field(min_length=2, max_length=60)
    marketplace_name: str | None = Field(default=None, max_length=100)


class PluginMarketplacePayload(BaseModel):
    url: str = Field(min_length=8, max_length=500)


class AgentToolsPayload(BaseModel):
    tools: list[str] = Field(default_factory=list)

    @field_validator("tools")
    @classmethod
    def dedupe_tools(cls, value: list[str]) -> list[str]:
        return list(dict.fromkeys(item.strip() for item in value if item.strip()))


class GuardrailSettingsPayload(BaseModel):
    max_iterations: int | None = Field(default=None, ge=1, le=100)
    max_tool_calls: int | None = Field(default=None, ge=1, le=500)
    max_duration_seconds: int | None = Field(default=None, ge=1, le=7200)
    max_tool_output_chars: int | None = Field(default=None, ge=100, le=1_000_000)
    max_total_chars: int | None = Field(default=None, ge=1000, le=10_000_000)
    loop_repeat_limit: int | None = Field(default=None, ge=2, le=10)


def fetch_all(query: str, params: tuple = ()):  # noqa: ANN201
    with connect() as connection:
        with connection.cursor() as cursor:
            cursor.execute(query, params)
            columns = [column.name for column in cursor.description]
            return [dict(zip(columns, row)) for row in cursor.fetchall()]


def fetch_one(query: str, params: tuple):  # noqa: ANN201
    with connect() as connection:
        with connection.cursor() as cursor:
            cursor.execute(query, params)
            columns = [column.name for column in cursor.description]
            row = cursor.fetchone()
            return dict(zip(columns, row)) if row else None


def execute_returning(query: str, params: tuple):  # noqa: ANN201
    with connect() as connection:
        with connection.cursor() as cursor:
            cursor.execute(query, params)
            columns = [column.name for column in cursor.description]
            row = cursor.fetchone()
            return dict(zip(columns, row))


def build_skill_draft(prompt: str) -> dict:
    words = re.findall(r"[a-zA-Z0-9]+", prompt.lower())[:6]
    name = "_".join(words) if words else "generated_skill"
    if not name.endswith("_skill"):
        name = f"{name}_skill"
    description = prompt if len(prompt) <= 180 else f"{prompt[:177]}..."
    return {
        "name": name[:100],
        "description": description,
        "argument_hint": "Describe entradas y objetivo esperado.",
        "triggers": ["user"],
        "body": (
            "# Instrucciones principales\n"
            "1. Identifica la tarea del usuario y confirma que encaja con esta skill.\n"
            "2. Reune entradas necesarias antes de actuar.\n"
            "3. Devuelve una respuesta estructurada con resultado, evidencias y siguientes pasos.\n\n"
            "## Restricciones\n"
            "* No ejecutes codigo, comandos destructivos ni llamadas externas sin autorizacion explicita.\n"
            "* No inventes datos; marca cualquier incertidumbre."
        ),
        "resources": "scripts/, templates/ y examples/ son opcionales; anade solo recursos revisados.",
        "instructions": (
            "Define the skill purpose, inputs, output shape, safety limits, and verification steps. "
            "Keep execution explicit; do not run arbitrary generated code."
        ),
        "checklist": [
            "Name is unique and action-oriented.",
            "Description explains when an agent should use it.",
            "Inputs and outputs are clear enough to test.",
            "No secrets, destructive shell commands, or unrestricted network access.",
        ],
    }


def render_skill_md(skill: dict) -> str:
    triggers = ", ".join(f'"{trigger}"' for trigger in skill.get("triggers", ["user"]))
    argument_hint = skill.get("argument_hint") or ""
    lines = [
        "---",
        f"name: {skill['name']}",
        f"description: {skill.get('description') or ''}",
    ]
    if argument_hint:
        lines.append(f"argument-hint: {argument_hint}")
    lines.extend([f"triggers: [{triggers}]", "---", "", skill.get("body") or ""])
    resources = skill.get("resources") or ""
    if resources:
        lines.extend(["", "## Recursos opcionales", resources])
    return "\n".join(lines).strip() + "\n"


def with_skill_md(skill: dict) -> dict:
    skill["skill_md"] = render_skill_md(skill)
    return skill


def ensure_safe_skill_name(name: str) -> None:
    if not SKILL_NAME_PATTERN.fullmatch(name):
        raise HTTPException(status_code=400, detail="Skill name may only contain letters, numbers, underscores, and hyphens.")


def resource_paths(resources: str) -> list[str]:
    paths: list[str] = []
    for line in resources.splitlines():
        resource = line.strip().lstrip("- ").strip()
        if not resource or resource.startswith("#"):
            continue
        normalized = resource.replace("\\", "/")
        if normalized.startswith("/") or ".." in Path(normalized).parts:
            raise HTTPException(status_code=400, detail=f"Unsafe skill resource path: {resource}")
        paths.append(normalized)
    return paths


def write_skill_files(skill: dict, previous_name: str | None = None) -> None:
    ensure_safe_skill_name(skill["name"])
    SKILLS_ROOT.mkdir(parents=True, exist_ok=True)
    skill_dir = SKILLS_ROOT / skill["name"]
    if previous_name and previous_name != skill["name"]:
        ensure_safe_skill_name(previous_name)
        previous_dir = SKILLS_ROOT / previous_name
        if previous_dir.exists() and not skill_dir.exists():
            previous_dir.rename(skill_dir)
    skill_dir.mkdir(parents=True, exist_ok=True)
    (skill_dir / "SKILL.md").write_text(render_skill_md(skill), encoding="utf-8")
    for resource in resource_paths(skill.get("resources") or ""):
        resource_path = skill_dir / resource
        resource_path.parent.mkdir(parents=True, exist_ok=True)
        if not resource_path.exists():
            resource_path.write_text(f"# {resource_path.stem.replace('-', ' ').replace('_', ' ').title()}\n", encoding="utf-8")


def delete_skill_files(name: str) -> None:
    ensure_safe_skill_name(name)
    skill_dir = SKILLS_ROOT / name
    if skill_dir.exists():
        shutil.rmtree(skill_dir)


def ensure_positive_id(value: int, label: str) -> int:
    if value <= 0:
        raise ValueError(f"{label} must be a positive integer")
    return value


def ensure_admin_role_change_allowed(current_role: str, next_role: str, admin_count: int) -> None:
    if current_role == "admin" and next_role != "admin" and admin_count <= 1:
        raise ValueError("At least one admin user is required.")


@router.get("/users")
def list_users(request: Request):
    require_admin(request)
    return {"users": fetch_all("SELECT id, username, email, role, created_at FROM users ORDER BY created_at DESC, id DESC;")}


@router.patch("/users/{user_id}/role")
def update_user_role(user_id: int, payload: UserRolePayload, request: Request):
    require_admin(request)
    try:
        user_id = ensure_positive_id(user_id, "user_id")
    except ValueError as error:
        raise HTTPException(status_code=400, detail=str(error)) from error

    user = fetch_one("SELECT id, role FROM users WHERE id = %s;", (user_id,))
    if not user:
        raise HTTPException(status_code=404, detail="User not found.")

    admin_count_row = fetch_one("SELECT COUNT(*) AS admin_count FROM users WHERE role = 'admin';", ())
    try:
        ensure_admin_role_change_allowed(user["role"], payload.role, admin_count_row["admin_count"])
    except ValueError as error:
        raise HTTPException(status_code=400, detail=str(error)) from error

    updated = execute_returning(
        """
        UPDATE users
        SET role = %s
        WHERE id = %s
        RETURNING id, username, email, role, created_at;
        """,
        (payload.role, user_id),
    )
    AuditStore().add_log(
        actor_user_id=int(request.session.get("user_id")),
        action="user.role_updated",
        target_type="user",
        target_id=user_id,
        metadata={"previous_role": user["role"], "next_role": payload.role},
    )
    return {"user": updated}


@router.get("/providers")
def list_providers(request: Request):
    require_user(request)
    return {"providers": fetch_all("SELECT id, name, provider_type, base_url, api_key_env, enabled FROM providers ORDER BY name;")}


@router.get("/provider-definitions")
def list_provider_definitions(request: Request):
    require_user(request)
    return {"provider_definitions": [definition.__dict__ for definition in PROVIDER_DEFINITIONS]}


@router.get("/diagnostics")
def diagnostics(request: Request):
    require_admin(request)
    counts = fetch_one(
        """
        SELECT
            (SELECT COUNT(*) AS users FROM users) AS users,
            (SELECT COUNT(*) AS agents FROM agents) AS agents,
            (SELECT COUNT(*) AS workflows FROM workflows) AS workflows,
            (SELECT COUNT(*) AS mcp_servers FROM mcp_servers) AS mcp_servers;
        """,
        (),
    )
    providers = fetch_all(
        """
        SELECT
            p.id,
            p.name,
            p.provider_type,
            p.enabled,
            p.api_key_env,
            COUNT(m.id) AS configured_models
        FROM providers p
        LEFT JOIN models m ON m.provider_id = p.id
        GROUP BY p.id, p.name, p.provider_type, p.enabled, p.api_key_env
        ORDER BY p.name;
        """
    )
    for provider in providers:
        provider["api_key_configured"] = bool(os.getenv(provider["api_key_env"])) if provider["api_key_env"] else True
        provider["ready"] = bool(provider["enabled"] and provider["configured_models"] > 0 and provider["api_key_configured"])
    return {"counts": counts, "providers": providers}


@router.get("/metrics")
def metrics(request: Request, days: Annotated[int, Query(ge=1, le=90)] = 14):
    require_admin(request)
    interval_where = "WHERE created_at >= NOW() - (%s * INTERVAL '1 day')"
    interval_params = (days,)
    summary = fetch_one(
        f"""
        SELECT
            COUNT(*) AS runs,
            COUNT(*) FILTER (WHERE status = 'completed') AS completed,
            COUNT(*) FILTER (WHERE status = 'failed') AS failed,
            COUNT(*) FILTER (WHERE status NOT IN ('completed', 'failed')) AS other,
            COUNT(DISTINCT user_id) AS active_users,
            COALESCE(AVG(EXTRACT(EPOCH FROM (completed_at - created_at))) FILTER (WHERE status = 'completed' AND completed_at IS NOT NULL), 0) AS avg_duration_seconds
        FROM agent_runs {interval_where};
        """,
        interval_params,
    )
    runs_per_day = fetch_all(
        f"""
        SELECT
            DATE_TRUNC('day', created_at)::date::text AS day,
            COUNT(*) FILTER (WHERE status = 'completed') AS completed,
            COUNT(*) FILTER (WHERE status = 'failed') AS failed,
            COUNT(*) FILTER (WHERE status NOT IN ('completed', 'failed')) AS other
        FROM agent_runs {interval_where}
        GROUP BY 1
        ORDER BY 1;
        """,
        interval_params,
    )
    tool_calls_per_day = fetch_all(
        f"""
        SELECT
            DATE_TRUNC('day', created_at)::date::text AS day,
            COUNT(*) AS total,
            COUNT(*) FILTER (WHERE status = 'failed') AS failed
        FROM tool_calls {interval_where}
        GROUP BY 1
        ORDER BY 1;
        """,
        interval_params,
    )
    top_tools = fetch_all(
        f"""
        SELECT
            skill_name AS name,
            COUNT(*) AS calls,
            COUNT(*) FILTER (WHERE status = 'failed') AS failed
        FROM tool_calls {interval_where}
        GROUP BY 1
        ORDER BY calls DESC
        LIMIT 15;
        """,
        interval_params,
    )
    mcp_calls = fetch_all(
        f"""
        SELECT
            tool_name AS name,
            COUNT(*) AS calls,
            COUNT(*) FILTER (WHERE status = 'failed') AS failed
        FROM mcp_calls {interval_where}
        GROUP BY 1
        ORDER BY calls DESC
        LIMIT 15;
        """,
        interval_params,
    )
    provider_fallbacks = fetch_one(
        f"""
        SELECT COUNT(*) AS fallbacks
        FROM agent_events {interval_where} AND event_type = 'provider_fallback';
        """,
        interval_params,
    )
    agent_activity = fetch_all(
        f"""
        SELECT
            COALESCE(a.name, 'n/a') AS agent,
            COUNT(*) AS runs,
            COUNT(*) FILTER (WHERE r.status = 'failed') AS failed
        FROM agent_runs r
        LEFT JOIN agents a ON a.id = r.agent_id
        {interval_where.replace('created_at', 'r.created_at')}
        GROUP BY 1
        ORDER BY runs DESC
        LIMIT 10;
        """,
        interval_params,
    )
    tool_categories = {"connectors": 0, "mcp": 0, "builtin": 0}
    for tool in top_tools:
        name = tool["name"]
        if name.startswith(("github_", "drive_")):
            tool_categories["connectors"] += tool["calls"]
        elif name.startswith("mcp_") or name.startswith("mcp:"):
            tool_categories["mcp"] += tool["calls"]
        else:
            tool_categories["builtin"] += tool["calls"]
    return {
        "days": days,
        "summary": summary,
        "runs_per_day": runs_per_day,
        "tool_calls_per_day": tool_calls_per_day,
        "top_tools": top_tools,
        "tool_categories": tool_categories,
        "mcp_calls": mcp_calls,
        "provider_fallbacks": provider_fallbacks["fallbacks"] if provider_fallbacks else 0,
        "agent_activity": agent_activity,
    }


@router.get("/plugins")
def list_plugins(request: Request):
    require_admin(request)
    from ..plugins import service

    installed = service.list_installed()
    catalog = []
    for entry in service.scan_catalog():
        manifest = entry["manifest"]
        plugin = installed.get(manifest["slug"])
        catalog.append(
            {
                "slug": manifest["slug"],
                "name": manifest["name"],
                "version": manifest["version"],
                "description": manifest["description"],
                "source": entry["source"],
                "marketplace_name": entry.get("marketplace_name"),
                "installed": plugin is not None,
                "connectors": manifest["connectors"],
                "components": {"skills": len(manifest["skills"]), "mcps": len(manifest["mcps"]), "agents": len(manifest["agents"])},
            }
        )
    return {"plugins": catalog, "marketplaces": service.list_marketplaces()}


@router.post("/plugins/install")
def install_plugin(payload: PluginInstallPayload, request: Request):
    require_admin(request)
    from ..plugins import service

    try:
        entry = service.find_catalog_entry(payload.source, payload.slug, payload.marketplace_name)
        result = service.install_plugin(entry)
    except (ValueError, RuntimeError) as error:
        raise HTTPException(status_code=400, detail=str(error)) from error
    AuditStore().add_log(
        actor_user_id=int(request.session.get("user_id")),
        action="plugin.installed",
        target_type="plugin",
        target_id=None,
        metadata={"slug": payload.slug, "source": payload.source},
    )
    return {"installed": result}


@router.delete("/plugins/{slug}")
def uninstall_plugin(slug: str, request: Request):
    require_admin(request)
    from ..plugins import service

    try:
        result = service.uninstall_plugin(slug)
    except ValueError as error:
        raise HTTPException(status_code=404, detail=str(error)) from error
    AuditStore().add_log(
        actor_user_id=int(request.session.get("user_id")),
        action="plugin.uninstalled",
        target_type="plugin",
        target_id=None,
        metadata={"slug": slug},
    )
    return {"uninstalled": result}


@router.post("/plugin-marketplaces")
def add_plugin_marketplace(payload: PluginMarketplacePayload, request: Request):
    require_admin(request)
    from ..plugins import service

    try:
        marketplace = service.add_marketplace(payload.url)
    except (ValueError, RuntimeError) as error:
        raise HTTPException(status_code=400, detail=str(error)) from error
    AuditStore().add_log(
        actor_user_id=int(request.session.get("user_id")),
        action="plugin_marketplace.added",
        target_type="plugin",
        target_id=None,
        metadata={"name": marketplace["name"], "url": marketplace["url"]},
    )
    return {"marketplace": marketplace}


@router.post("/plugin-marketplaces/{name}/refresh")
def refresh_plugin_marketplace(name: str, request: Request):
    require_admin(request)
    from ..plugins import service

    try:
        result = service.refresh_marketplace(name)
    except (ValueError, RuntimeError) as error:
        raise HTTPException(status_code=400, detail=str(error)) from error
    return {"refreshed": result}


@router.delete("/plugin-marketplaces/{name}")
def remove_plugin_marketplace(name: str, request: Request):
    require_admin(request)
    from ..plugins import service

    if not service.remove_marketplace(name):
        raise HTTPException(status_code=404, detail="Marketplace not found.")
    AuditStore().add_log(
        actor_user_id=int(request.session.get("user_id")),
        action="plugin_marketplace.removed",
        target_type="plugin",
        target_id=None,
        metadata={"name": name},
    )
    return {"name": name, "deleted": True}


@router.get("/audit-logs")
def list_audit_logs(
    request: Request,
    limit: Annotated[int, Query(ge=1, le=500)] = 100,
    action: Annotated[str | None, Query(max_length=120)] = None,
    target_type: Annotated[str | None, Query(max_length=80)] = None,
):
    require_admin(request)
    filters = []
    params: list[object] = []
    if action:
        filters.append("a.action = %s")
        params.append(action)
    if target_type:
        filters.append("a.target_type = %s")
        params.append(target_type)
    where_clause = f"WHERE {' AND '.join(filters)}" if filters else ""
    params.append(limit)
    logs = fetch_all(
        f"""
        SELECT
            a.id,
            a.actor_user_id,
            u.username AS actor_username,
            a.action,
            a.target_type,
            a.target_id,
            a.metadata,
            a.created_at
        FROM audit_logs a
        LEFT JOIN users u ON u.id = a.actor_user_id
        {where_clause}
        ORDER BY a.created_at DESC, a.id DESC
        LIMIT %s;
        """,
        tuple(params),
    )
    return {"audit_logs": logs}


@router.post("/providers")
def create_provider(payload: ProviderPayload, request: Request):
    require_admin(request)
    provider = execute_returning(
        """
        INSERT INTO providers (name, provider_type, base_url, api_key_env, enabled)
        VALUES (%s, %s, %s, %s, %s)
        RETURNING id, name, provider_type, base_url, api_key_env, enabled;
        """,
        (payload.name, payload.provider_type, payload.base_url, payload.api_key_env, payload.enabled),
    )
    AuditStore().add_log(
        actor_user_id=int(request.session.get("user_id")),
        action="provider.created",
        target_type="provider",
        target_id=provider["id"],
        metadata={"name": provider["name"], "provider_type": provider["provider_type"], "enabled": provider["enabled"]},
    )
    return {"provider": provider}


@router.patch("/providers/{provider_id}")
def update_provider(provider_id: int, payload: ProviderPayload, request: Request):
    require_admin(request)
    provider = execute_returning(
        """
        UPDATE providers
        SET name = %s, provider_type = %s, base_url = %s, api_key_env = %s, enabled = %s
        WHERE id = %s
        RETURNING id, name, provider_type, base_url, api_key_env, enabled;
        """,
        (payload.name, payload.provider_type, payload.base_url, payload.api_key_env, payload.enabled, provider_id),
    )
    if not provider:
        raise HTTPException(status_code=404, detail="Provider not found.")
    AuditStore().add_log(
        actor_user_id=int(request.session.get("user_id")),
        action="provider.updated",
        target_type="provider",
        target_id=provider["id"],
        metadata={"name": provider["name"], "provider_type": provider["provider_type"], "enabled": provider["enabled"]},
    )
    return {"provider": provider}


@router.get("/models")
def list_models(request: Request):
    require_user(request)
    return {"models": fetch_all("SELECT id, provider_id, model_name, display_name, supports_text, supports_streaming, supports_vision, supports_audio, supports_tools, supports_json, context_window, enabled FROM models ORDER BY display_name;")}


@router.post("/models")
def create_model(payload: ModelPayload, request: Request):
    require_admin(request)
    model = execute_returning(
        """
        INSERT INTO models (
            provider_id, model_name, display_name, supports_text, supports_streaming,
            supports_vision, supports_audio, supports_tools, supports_json, context_window, enabled
        )
        VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
        RETURNING id, provider_id, model_name, display_name, supports_text, supports_streaming,
            supports_vision, supports_audio, supports_tools, supports_json, context_window, enabled;
        """,
        (
            payload.provider_id,
            payload.model_name,
            payload.display_name,
            payload.supports_text,
            payload.supports_streaming,
            payload.supports_vision,
            payload.supports_audio,
            payload.supports_tools,
            payload.supports_json,
            payload.context_window,
            payload.enabled,
        ),
    )
    AuditStore().add_log(
        actor_user_id=int(request.session.get("user_id")),
        action="model.created",
        target_type="model",
        target_id=model["id"],
        metadata={"model_name": model["model_name"], "provider_id": model["provider_id"], "enabled": model["enabled"]},
    )
    return {"model": model}


@router.delete("/models/{model_id}")
def delete_model(model_id: int, request: Request):
    require_admin(request)
    try:
        model_id = ensure_positive_id(model_id, "model_id")
    except ValueError as error:
        raise HTTPException(status_code=400, detail=str(error)) from error
    model = execute_returning(
        "DELETE FROM models WHERE id = %s RETURNING id, model_name, display_name;",
        (model_id,),
    )
    AuditStore().add_log(
        actor_user_id=int(request.session.get("user_id")),
        action="model.deleted",
        target_type="model",
        target_id=model["id"],
        metadata={"model_name": model["model_name"], "display_name": model["display_name"]},
    )
    return {"id": model["id"], "deleted": True}


@router.patch("/models/{model_id}")
def update_model(model_id: int, payload: ModelPayload, request: Request):
    require_admin(request)
    try:
        model_id = ensure_positive_id(model_id, "model_id")
    except ValueError as error:
        raise HTTPException(status_code=400, detail=str(error)) from error

    model = execute_returning(
        """
        UPDATE models
        SET provider_id = %s, model_name = %s, display_name = %s, supports_text = %s,
            supports_streaming = %s, supports_vision = %s, supports_audio = %s,
            supports_tools = %s, supports_json = %s, context_window = %s, enabled = %s
        WHERE id = %s
        RETURNING id, provider_id, model_name, display_name, supports_text, supports_streaming,
            supports_vision, supports_audio, supports_tools, supports_json, context_window, enabled;
        """,
        (
            payload.provider_id,
            payload.model_name,
            payload.display_name,
            payload.supports_text,
            payload.supports_streaming,
            payload.supports_vision,
            payload.supports_audio,
            payload.supports_tools,
            payload.supports_json,
            payload.context_window,
            payload.enabled,
            model_id,
        ),
    )
    if not model:
        raise HTTPException(status_code=404, detail="Model not found.")
    AuditStore().add_log(
        actor_user_id=int(request.session.get("user_id")),
        action="model.updated",
        target_type="model",
        target_id=model["id"],
        metadata={"model_name": model["model_name"], "provider_id": model["provider_id"], "enabled": model["enabled"]},
    )
    return {"model": model}


@router.post("/models/{model_id}/check")
def check_model_config(model_id: int, request: Request):
    require_admin(request)
    try:
        model_id = ensure_positive_id(model_id, "model_id")
    except ValueError as error:
        raise HTTPException(status_code=400, detail=str(error)) from error

    model = fetch_one(
        """
        SELECT
            m.id,
            m.model_name,
            m.display_name,
            m.enabled,
            p.id AS provider_id,
            p.name AS provider_name,
            p.provider_type,
            p.api_key_env,
            p.enabled AS provider_enabled
        FROM models m
        JOIN providers p ON p.id = m.provider_id
        WHERE m.id = %s;
        """,
        (model_id,),
    )
    if not model:
        raise HTTPException(status_code=404, detail="Model not found.")

    api_key_env = model["api_key_env"]
    api_key_configured = bool(os.getenv(api_key_env)) if api_key_env else True
    return {
        "model_id": model["id"],
        "model_name": model["model_name"],
        "provider": model["provider_name"],
        "provider_type": model["provider_type"],
        "enabled": model["enabled"],
        "provider_enabled": model["provider_enabled"],
        "api_key_env": api_key_env,
        "api_key_configured": api_key_configured,
        "ready": bool(model["enabled"] and model["provider_enabled"] and api_key_configured),
    }


@router.get("/agents")
def list_agents(request: Request):
    require_user(request)
    return {"agents": fetch_all("SELECT id, name, description, system_prompt, provider_id, model_id, temperature, internet_enabled, multimodal_enabled, agentic_mode, enabled FROM agents ORDER BY name;")}


@router.get("/agent-skills")
def list_agent_skills(request: Request):
    require_user(request)
    return {"agent_skills": fetch_all("SELECT agent_id, skill_id FROM agent_skills ORDER BY agent_id, skill_id;")}


@router.post("/agents/{agent_id}/skills/{skill_id}")
def assign_agent_skill(agent_id: int, skill_id: int, request: Request):
    require_admin(request)
    try:
        agent_id = ensure_positive_id(agent_id, "agent_id")
        skill_id = ensure_positive_id(skill_id, "skill_id")
    except ValueError as error:
        raise HTTPException(status_code=400, detail=str(error)) from error

    execute_returning(
        """
        INSERT INTO agent_skills (agent_id, skill_id)
        VALUES (%s, %s)
        ON CONFLICT (agent_id, skill_id) DO UPDATE SET agent_id = EXCLUDED.agent_id
        RETURNING agent_id, skill_id;
        """,
        (agent_id, skill_id),
    )
    AuditStore().add_log(
        actor_user_id=int(request.session.get("user_id")),
        action="agent_skill.assigned",
        target_type="agent",
        target_id=agent_id,
        metadata={"skill_id": skill_id},
    )
    return {"agent_id": agent_id, "skill_id": skill_id}


@router.delete("/agents/{agent_id}/skills/{skill_id}")
def remove_agent_skill(agent_id: int, skill_id: int, request: Request):
    require_admin(request)
    try:
        agent_id = ensure_positive_id(agent_id, "agent_id")
        skill_id = ensure_positive_id(skill_id, "skill_id")
    except ValueError as error:
        raise HTTPException(status_code=400, detail=str(error)) from error

    with connect() as connection:
        with connection.cursor() as cursor:
            cursor.execute("DELETE FROM agent_skills WHERE agent_id = %s AND skill_id = %s;", (agent_id, skill_id))
    AuditStore().add_log(
        actor_user_id=int(request.session.get("user_id")),
        action="agent_skill.removed",
        target_type="agent",
        target_id=agent_id,
        metadata={"skill_id": skill_id},
    )
    return {"agent_id": agent_id, "skill_id": skill_id, "removed": True}


@router.post("/agents")
def create_agent(payload: AgentPayload, request: Request):
    require_admin(request)
    agent = execute_returning(
        """
        INSERT INTO agents (name, description, system_prompt, provider_id, model_id, temperature, internet_enabled, multimodal_enabled, agentic_mode, enabled)
        VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
        RETURNING id, name, description, provider_id, model_id, temperature, internet_enabled, multimodal_enabled, agentic_mode, enabled;
        """,
        (
            payload.name,
            payload.description,
            payload.system_prompt,
            payload.provider_id,
            payload.model_id,
            payload.temperature,
            payload.internet_enabled,
            payload.multimodal_enabled,
            payload.agentic_mode,
            payload.enabled,
        ),
    )
    AuditStore().add_log(
        actor_user_id=int(request.session.get("user_id")),
        action="agent.created",
        target_type="agent",
        target_id=agent["id"],
        metadata={
            "name": agent["name"],
            "internet_enabled": agent["internet_enabled"],
            "multimodal_enabled": agent["multimodal_enabled"],
            "enabled": agent["enabled"],
        },
    )
    return {"agent": agent}


@router.patch("/agents/{agent_id}")
def update_agent(agent_id: int, payload: AgentPayload, request: Request):
    require_admin(request)
    agent = execute_returning(
        """
        UPDATE agents
        SET name = %s, description = %s, system_prompt = %s, provider_id = %s, model_id = %s,
            temperature = %s, internet_enabled = %s, multimodal_enabled = %s, agentic_mode = %s, enabled = %s
        WHERE id = %s
        RETURNING id, name, description, provider_id, model_id, temperature, internet_enabled, multimodal_enabled, agentic_mode, enabled;
        """,
        (
            payload.name,
            payload.description,
            payload.system_prompt,
            payload.provider_id,
            payload.model_id,
            payload.temperature,
            payload.internet_enabled,
            payload.multimodal_enabled,
            payload.agentic_mode,
            payload.enabled,
            agent_id,
        ),
    )
    if not agent:
        raise HTTPException(status_code=404, detail="Agent not found.")
    AuditStore().add_log(
        actor_user_id=int(request.session.get("user_id")),
        action="agent.updated",
        target_type="agent",
        target_id=agent["id"],
        metadata={
            "name": agent["name"],
            "internet_enabled": agent["internet_enabled"],
            "multimodal_enabled": agent["multimodal_enabled"],
            "enabled": agent["enabled"],
        },
    )
    return {"agent": agent}


@router.post("/providers/{provider_id}/detect-models")
def detect_provider_models(provider_id: int, request: Request):
    require_admin(request)
    provider_id = ensure_positive_id(provider_id, "provider_id")
    provider = fetch_one(
        "SELECT id, name, provider_type, base_url, api_key_env, enabled FROM providers WHERE id = %s;",
        (provider_id,),
    )
    if not provider:
        raise HTTPException(status_code=404, detail="Provider not found.")

    api_key = os.getenv(provider["api_key_env"]) if provider["api_key_env"] else None
    try:
        detected = list_provider_models(provider["provider_type"], api_key, provider["base_url"])
    except Exception as error:  # noqa: BLE001
        raise HTTPException(status_code=502, detail=f"Model detection failed: {error}") from error

    registered = {
        row["model_name"]
        for row in fetch_all("SELECT model_name FROM models WHERE provider_id = %s;", (provider_id,))
    }
    for item in detected:
        item["already_registered"] = item["model_name"] in registered
    return {"provider_id": provider_id, "provider_name": provider["name"], "models": detected}


@router.get("/agent-tools")
def list_agent_tools(request: Request):
    require_user(request)
    return {"agent_tools": fetch_all("SELECT agent_id, tool_name, allowed FROM agent_tool_permissions ORDER BY agent_id, tool_name;")}


@router.get("/agent-fallbacks")
def list_agent_fallbacks(request: Request):
    require_user(request)
    return {
        "agent_fallbacks": fetch_all(
            """
            SELECT af.agent_id, af.provider_id, af.model_id, af.priority, p.name AS provider_name, m.display_name AS model_display_name
            FROM agent_fallbacks af
            JOIN providers p ON p.id = af.provider_id
            JOIN models m ON m.id = af.model_id
            ORDER BY af.agent_id, af.priority;
            """
        )
    }


class AgentFallbackPayload(BaseModel):
    fallbacks: list[dict] = Field(default_factory=list)

    @field_validator("fallbacks")
    @classmethod
    def validate_fallbacks(cls, value: list[dict]) -> list[dict]:
        normalized = []
        for index, item in enumerate(value):
            provider_id = item.get("provider_id")
            model_id = item.get("model_id")
            if not isinstance(provider_id, int) or not isinstance(model_id, int):
                raise ValueError(f"fallbacks[{index}] must include provider_id and model_id as integers.")
            normalized.append({"provider_id": provider_id, "model_id": model_id})
        return normalized


@router.put("/agents/{agent_id}/fallbacks")
def set_agent_fallbacks(agent_id: int, payload: AgentFallbackPayload, request: Request):
    require_admin(request)
    agent_id = ensure_positive_id(agent_id, "agent_id")
    agent = fetch_one("SELECT id, name FROM agents WHERE id = %s;", (agent_id,))
    if not agent:
        raise HTTPException(status_code=404, detail="Agent not found.")
    for item in payload.fallbacks:
        model = fetch_one(
            """
            SELECT m.id FROM models m
            JOIN providers p ON p.id = m.provider_id
            WHERE m.id = %s AND p.id = %s AND m.enabled = true AND p.enabled = true;
            """,
            (item["model_id"], item["provider_id"]),
        )
        if not model:
            raise HTTPException(status_code=400, detail=f"Model {item['model_id']} is not an enabled model of provider {item['provider_id']}.")

    with connect() as connection:
        with connection.cursor() as cursor:
            cursor.execute("DELETE FROM agent_fallbacks WHERE agent_id = %s;", (agent_id,))
            for priority, item in enumerate(payload.fallbacks, start=1):
                cursor.execute(
                    "INSERT INTO agent_fallbacks (agent_id, provider_id, model_id, priority) VALUES (%s, %s, %s, %s);",
                    (agent_id, item["provider_id"], item["model_id"], priority),
                )

    AuditStore().add_log(
        actor_user_id=int(request.session.get("user_id")),
        action="agent_fallbacks.updated",
        target_type="agent",
        target_id=agent_id,
        metadata={"fallbacks": payload.fallbacks},
    )
    return {"agent_id": agent_id, "fallbacks": payload.fallbacks}


@router.put("/agents/{agent_id}/tools")
def set_agent_tools(agent_id: int, payload: AgentToolsPayload, request: Request):
    require_admin(request)
    agent_id = ensure_positive_id(agent_id, "agent_id")
    from ..agent.routes import catalog_tool_specs

    known_tools = {spec.name for spec in catalog_tool_specs()}
    unknown = [tool for tool in payload.tools if tool not in known_tools]
    if unknown:
        raise HTTPException(status_code=400, detail=f"Unknown tools: {', '.join(unknown)}")

    agent = fetch_one("SELECT id, name FROM agents WHERE id = %s;", (agent_id,))
    if not agent:
        raise HTTPException(status_code=404, detail="Agent not found.")

    with connect() as connection:
        with connection.cursor() as cursor:
            cursor.execute("DELETE FROM agent_tool_permissions WHERE agent_id = %s;", (agent_id,))
            for tool_name in payload.tools:
                cursor.execute(
                    "INSERT INTO agent_tool_permissions (agent_id, tool_name, allowed) VALUES (%s, %s, true);",
                    (agent_id, tool_name),
                )

    AuditStore().add_log(
        actor_user_id=int(request.session.get("user_id")),
        action="agent_tools.updated",
        target_type="agent",
        target_id=agent_id,
        metadata={"tools": payload.tools},
    )
    return {"agent_id": agent_id, "tools": payload.tools}


@router.get("/settings/guardrails")
def list_guardrail_settings(request: Request):
    require_admin(request)
    row = fetch_one("SELECT value FROM app_settings WHERE key = 'guardrails';", ())
    return {"guardrails": (row or {}).get("value", {})}


class TasksSettingsPayload(BaseModel):
    max_concurrent_tasks: int | None = Field(default=None, ge=1, le=4)
    auto_resume_tasks: bool | None = None


@router.get("/settings/tasks")
def list_tasks_settings(request: Request):
    require_admin(request)
    row = fetch_one("SELECT value FROM app_settings WHERE key = 'tasks';", ())
    return {"tasks": (row or {}).get("value", {"max_concurrent_tasks": 1, "auto_resume_tasks": True})}


@router.put("/settings/tasks")
def update_tasks_settings(settings: TasksSettingsPayload, request: Request):
    require_admin(request)
    current_row = fetch_one("SELECT value FROM app_settings WHERE key = 'tasks';", ())
    current = current_row.get("value", {}) if current_row else {}
    payload = {**current, **{key: value for key, value in settings.model_dump().items() if value is not None}}
    row = execute_returning(
        """
        INSERT INTO app_settings (key, value)
        VALUES ('tasks', %s::json)
        ON CONFLICT (key) DO UPDATE SET value = EXCLUDED.value
        RETURNING value;
        """,
        (json.dumps(payload),),
    )
    AuditStore().add_log(
        actor_user_id=int(request.session.get("user_id")),
        action="tasks_settings.updated",
        target_type="settings",
        target_id=None,
        metadata=payload,
    )
    return {"tasks": row["value"]}


@router.put("/settings/guardrails")
def update_guardrail_settings(settings: GuardrailSettingsPayload, request: Request):
    require_admin(request)
    payload = {key: value for key, value in settings.model_dump().items() if value is not None}
    row = execute_returning(
        """
        INSERT INTO app_settings (key, value)
        VALUES ('guardrails', %s::json)
        ON CONFLICT (key) DO UPDATE SET value = EXCLUDED.value
        RETURNING value;
        """,
        (json.dumps(payload),),
    )
    AuditStore().add_log(
        actor_user_id=int(request.session.get("user_id")),
        action="guardrails.updated",
        target_type="settings",
        target_id=None,
        metadata=payload,
    )
    return {"guardrails": row["value"]}


@router.get("/skills")
def list_skills(request: Request):
    require_user(request)
    skills = fetch_all("SELECT id, name, description, argument_hint, triggers, body, resources, enabled FROM skills ORDER BY name;")
    return {"skills": [with_skill_md(skill) for skill in skills]}


@router.post("/skills")
def create_skill(payload: SkillPayload, request: Request):
    require_admin(request)
    ensure_safe_skill_name(payload.name)
    skill = execute_returning(
        """
        INSERT INTO skills (name, description, argument_hint, triggers, body, resources, enabled)
        VALUES (%s, %s, %s, %s, %s, %s, %s)
        RETURNING id, name, description, argument_hint, triggers, body, resources, enabled;
        """,
        (payload.name, payload.description, payload.argument_hint, payload.triggers, payload.body, payload.resources, payload.enabled),
    )
    write_skill_files(skill)
    AuditStore().add_log(
        actor_user_id=int(request.session.get("user_id")),
        action="skill.created",
        target_type="skill",
        target_id=skill["id"],
        metadata={"name": skill["name"], "enabled": skill["enabled"]},
    )
    return {"skill": with_skill_md(skill)}


@router.patch("/skills/{skill_id}")
def update_skill(skill_id: int, payload: SkillPayload, request: Request):
    require_admin(request)
    skill_id = ensure_positive_id(skill_id, "skill_id")
    ensure_safe_skill_name(payload.name)
    existing_skill = fetch_one("SELECT name FROM skills WHERE id = %s;", (skill_id,))
    if not existing_skill:
        raise HTTPException(status_code=404, detail="Skill not found.")
    skill = execute_returning(
        """
        UPDATE skills
        SET name = %s, description = %s, argument_hint = %s, triggers = %s, body = %s, resources = %s, enabled = %s
        WHERE id = %s
        RETURNING id, name, description, argument_hint, triggers, body, resources, enabled;
        """,
        (payload.name, payload.description, payload.argument_hint, payload.triggers, payload.body, payload.resources, payload.enabled, skill_id),
    )
    write_skill_files(skill, previous_name=existing_skill["name"])
    AuditStore().add_log(
        actor_user_id=int(request.session.get("user_id")),
        action="skill.updated",
        target_type="skill",
        target_id=skill["id"],
        metadata={"name": skill["name"], "enabled": skill["enabled"]},
    )
    return {"skill": with_skill_md(skill)}


@router.delete("/skills/{skill_id}")
def delete_skill(skill_id: int, request: Request):
    require_admin(request)
    skill_id = ensure_positive_id(skill_id, "skill_id")
    skill = execute_returning(
        "DELETE FROM skills WHERE id = %s RETURNING id, name;",
        (skill_id,),
    )
    delete_skill_files(skill["name"])
    AuditStore().add_log(
        actor_user_id=int(request.session.get("user_id")),
        action="skill.deleted",
        target_type="skill",
        target_id=skill["id"],
        metadata={"name": skill["name"]},
    )
    return {"id": skill["id"], "deleted": True}


@router.post("/skills/generate")
def generate_skill(payload: SkillGeneratePayload, request: Request):
    require_admin(request)
    draft = build_skill_draft(payload.prompt)
    AuditStore().add_log(
        actor_user_id=int(request.session.get("user_id")),
        action="skill.generated",
        target_type="skill",
        target_id=None,
        metadata={"name": draft["name"]},
    )
    return {"draft": draft}


@router.post("/skills/run")
def run_skill(payload: SkillRunPayload, request: Request):
    require_user(request)
    result = SkillRegistry().run(payload.skill_name, payload.payload)
    return {"skill_name": payload.skill_name, "result": result}


@router.get("/mcp-servers")
def list_mcp_servers(request: Request):
    require_user(request)
    return {"mcp_servers": fetch_all("SELECT id, name, description, connection_type, command, url, enabled FROM mcp_servers ORDER BY name;")}


@router.get("/agent-mcps")
def list_agent_mcps(request: Request):
    require_user(request)
    return {"agent_mcps": fetch_all("SELECT agent_id, mcp_server_id FROM agent_mcps ORDER BY agent_id, mcp_server_id;")}


@router.post("/agents/{agent_id}/mcps/{mcp_server_id}")
def assign_agent_mcp(agent_id: int, mcp_server_id: int, request: Request):
    require_admin(request)
    try:
        agent_id = ensure_positive_id(agent_id, "agent_id")
        mcp_server_id = ensure_positive_id(mcp_server_id, "mcp_server_id")
    except ValueError as error:
        raise HTTPException(status_code=400, detail=str(error)) from error

    execute_returning(
        """
        INSERT INTO agent_mcps (agent_id, mcp_server_id)
        VALUES (%s, %s)
        ON CONFLICT (agent_id, mcp_server_id) DO UPDATE SET agent_id = EXCLUDED.agent_id
        RETURNING agent_id, mcp_server_id;
        """,
        (agent_id, mcp_server_id),
    )
    AuditStore().add_log(
        actor_user_id=int(request.session.get("user_id")),
        action="agent_mcp.assigned",
        target_type="agent",
        target_id=agent_id,
        metadata={"mcp_server_id": mcp_server_id},
    )
    return {"agent_id": agent_id, "mcp_server_id": mcp_server_id}


@router.delete("/agents/{agent_id}/mcps/{mcp_server_id}")
def remove_agent_mcp(agent_id: int, mcp_server_id: int, request: Request):
    require_admin(request)
    try:
        agent_id = ensure_positive_id(agent_id, "agent_id")
        mcp_server_id = ensure_positive_id(mcp_server_id, "mcp_server_id")
    except ValueError as error:
        raise HTTPException(status_code=400, detail=str(error)) from error

    with connect() as connection:
        with connection.cursor() as cursor:
            cursor.execute("DELETE FROM agent_mcps WHERE agent_id = %s AND mcp_server_id = %s;", (agent_id, mcp_server_id))
    AuditStore().add_log(
        actor_user_id=int(request.session.get("user_id")),
        action="agent_mcp.removed",
        target_type="agent",
        target_id=agent_id,
        metadata={"mcp_server_id": mcp_server_id},
    )
    return {"agent_id": agent_id, "mcp_server_id": mcp_server_id, "removed": True}


@router.get("/workflows")
def list_workflows(request: Request):
    require_user(request)
    workflows = fetch_all("SELECT id, name, workflow_type, enabled FROM workflows ORDER BY name;")
    steps = fetch_all("SELECT workflow_id, agent_id, step_order, step_name FROM workflow_steps ORDER BY workflow_id, step_order;")
    return {"workflows": workflows, "workflow_steps": steps}


@router.post("/workflows")
def create_workflow(payload: WorkflowPayload, request: Request):
    require_admin(request)
    with connect() as connection:
        with connection.cursor() as cursor:
            cursor.execute(
                """
                INSERT INTO workflows (name, workflow_type, enabled)
                VALUES (%s, %s, %s)
                RETURNING id, name, workflow_type, enabled;
                """,
                (payload.name, payload.workflow_type, payload.enabled),
            )
            columns = [column.name for column in cursor.description]
            workflow = dict(zip(columns, cursor.fetchone()))

            for index, agent_id in enumerate(payload.agent_ids, start=1):
                cursor.execute(
                    """
                    INSERT INTO workflow_steps (workflow_id, agent_id, step_order, step_name)
                    VALUES (%s, %s, %s, %s);
                    """,
                    (workflow["id"], agent_id, index, f"Step {index}"),
                )

    AuditStore().add_log(
        actor_user_id=int(request.session.get("user_id")),
        action="workflow.created",
        target_type="workflow",
        target_id=workflow["id"],
        metadata={
            "name": workflow["name"],
            "workflow_type": workflow["workflow_type"],
            "step_count": len(payload.agent_ids),
            "enabled": workflow["enabled"],
        },
    )
    return {"workflow": workflow}


@router.patch("/workflows/{workflow_id}")
def update_workflow(workflow_id: int, payload: WorkflowPayload, request: Request):
    require_admin(request)
    try:
        workflow_id = ensure_positive_id(workflow_id, "workflow_id")
    except ValueError as error:
        raise HTTPException(status_code=400, detail=str(error)) from error

    with connect() as connection:
        with connection.cursor() as cursor:
            cursor.execute(
                """
                UPDATE workflows
                SET name = %s, workflow_type = %s, enabled = %s
                WHERE id = %s
                RETURNING id, name, workflow_type, enabled;
                """,
                (payload.name, payload.workflow_type, payload.enabled, workflow_id),
            )
            row = cursor.fetchone()
            if not row:
                raise HTTPException(status_code=404, detail="Workflow not found.")

            columns = [column.name for column in cursor.description]
            workflow = dict(zip(columns, row))

            cursor.execute("DELETE FROM workflow_steps WHERE workflow_id = %s;", (workflow_id,))
            for index, agent_id in enumerate(payload.agent_ids, start=1):
                cursor.execute(
                    """
                    INSERT INTO workflow_steps (workflow_id, agent_id, step_order, step_name)
                    VALUES (%s, %s, %s, %s);
                    """,
                    (workflow_id, agent_id, index, f"Step {index}"),
                )

    AuditStore().add_log(
        actor_user_id=int(request.session.get("user_id")),
        action="workflow.updated",
        target_type="workflow",
        target_id=workflow["id"],
        metadata={
            "name": workflow["name"],
            "workflow_type": workflow["workflow_type"],
            "step_count": len(payload.agent_ids),
            "enabled": workflow["enabled"],
        },
    )
    return {"workflow": workflow}


@router.post("/mcp-servers")
def create_mcp_server(payload: McpServerPayload, request: Request):
    require_admin(request)
    try:
        McpGateway().validate(McpServerConfig(payload.name, payload.description, payload.connection_type, payload.command, payload.url, payload.enabled))
    except ValueError as error:
        raise HTTPException(status_code=400, detail=str(error)) from error
    server = execute_returning(
        """
        INSERT INTO mcp_servers (name, description, connection_type, command, url, enabled)
        VALUES (%s, %s, %s, %s, %s, %s)
        RETURNING id, name, description, connection_type, command, url, enabled;
        """,
        (payload.name, payload.description, payload.connection_type, payload.command, payload.url, payload.enabled),
    )
    AuditStore().add_log(
        actor_user_id=int(request.session.get("user_id")),
        action="mcp_server.created",
        target_type="mcp_server",
        target_id=server["id"],
        metadata={"name": server["name"], "connection_type": server["connection_type"], "enabled": server["enabled"]},
    )
    return {"mcp_server": server}


@router.patch("/mcp-servers/{mcp_server_id}")
def update_mcp_server(mcp_server_id: int, payload: McpServerPayload, request: Request):
    require_admin(request)
    try:
        McpGateway().validate(McpServerConfig(payload.name, payload.description, payload.connection_type, payload.command, payload.url, payload.enabled))
    except ValueError as error:
        raise HTTPException(status_code=400, detail=str(error)) from error
    try:
        mcp_server_id = ensure_positive_id(mcp_server_id, "mcp_server_id")
    except ValueError as error:
        raise HTTPException(status_code=400, detail=str(error)) from error

    server = execute_returning(
        """
        UPDATE mcp_servers
        SET name = %s, description = %s, connection_type = %s, command = %s, url = %s, enabled = %s
        WHERE id = %s
        RETURNING id, name, description, connection_type, command, url, enabled;
        """,
        (payload.name, payload.description, payload.connection_type, payload.command, payload.url, payload.enabled, mcp_server_id),
    )
    if not server:
        raise HTTPException(status_code=404, detail="MCP server not found.")
    AuditStore().add_log(
        actor_user_id=int(request.session.get("user_id")),
        action="mcp_server.updated",
        target_type="mcp_server",
        target_id=server["id"],
        metadata={"name": server["name"], "connection_type": server["connection_type"], "enabled": server["enabled"]},
    )
    return {"mcp_server": server}


@router.delete("/mcp-servers/{mcp_server_id}")
def delete_mcp_server(mcp_server_id: int, request: Request):
    require_admin(request)
    try:
        mcp_server_id = ensure_positive_id(mcp_server_id, "mcp_server_id")
    except ValueError as error:
        raise HTTPException(status_code=400, detail=str(error)) from error
    server = execute_returning(
        "DELETE FROM mcp_servers WHERE id = %s RETURNING id, name;",
        (mcp_server_id,),
    )
    AuditStore().add_log(
        actor_user_id=int(request.session.get("user_id")),
        action="mcp_server.deleted",
        target_type="mcp_server",
        target_id=server["id"],
        metadata={"name": server["name"]},
    )
    return {"id": server["id"], "deleted": True}


@router.post("/mcp-servers/{mcp_server_id}/inspect")
def inspect_mcp_server(mcp_server_id: int, request: Request):
    require_admin(request)
    try:
        mcp_server_id = ensure_positive_id(mcp_server_id, "mcp_server_id")
    except ValueError as error:
        raise HTTPException(status_code=400, detail=str(error)) from error

    server = fetch_one(
        "SELECT id, name, connection_type, command, url FROM mcp_servers WHERE id = %s;",
        (mcp_server_id,),
    )
    if not server:
        raise HTTPException(status_code=404, detail="MCP server not found.")
    gateway = McpGateway()
    try:
        if server["connection_type"] == "command":
            inspection = gateway.inspect_command(server["command"])
        else:
            inspection = gateway.inspect_url(server["url"])
    except (RuntimeError, ValueError) as error:
        raise HTTPException(status_code=502, detail=str(error)) from error
    AuditStore().add_log(
        actor_user_id=int(request.session.get("user_id")),
        action="mcp_server.inspected",
        target_type="mcp_server",
        target_id=mcp_server_id,
        metadata={"name": server["name"], "tool_count": len(inspection["tools"]), "connection_type": server["connection_type"]},
    )
    return {"mcp_server_id": mcp_server_id, "server_info": inspection["server_info"], "tools": inspection["tools"]}


@router.post("/mcp-servers/validate")
def validate_mcp_server(payload: McpServerPayload, request: Request):
    require_admin(request)
    validation = McpGateway().validate(
        McpServerConfig(
            name=payload.name,
            description=payload.description,
            connection_type=payload.connection_type,
            command=payload.command,
            url=payload.url,
            enabled=payload.enabled,
        )
    )
    return {"validation": validation}


@router.post("/mcp-servers/{mcp_server_id}/run")
def run_mcp_server(mcp_server_id: int, payload: McpRunPayload, request: Request):
    require_admin(request)
    try:
        mcp_server_id = ensure_positive_id(mcp_server_id, "mcp_server_id")
    except ValueError as error:
        raise HTTPException(status_code=400, detail=str(error)) from error

    server = fetch_one(
        "SELECT id, name, description, connection_type, command, url, enabled FROM mcp_servers WHERE id = %s;",
        (mcp_server_id,),
    )
    if not server:
        raise HTTPException(status_code=404, detail="MCP server not found.")
    if not server["enabled"]:
        raise HTTPException(status_code=400, detail="MCP server is disabled.")
    gateway = McpGateway()
    try:
        if server["connection_type"] == "command":
            response = gateway.call_command(server["command"], payload.method, payload.params)
        else:
            response = gateway.call_url(server["url"], payload.method, payload.params)
    except RuntimeError as error:
        AuditStore().add_log(
            actor_user_id=int(request.session.get("user_id")),
            action="mcp_server.run.failed",
            target_type="mcp_server",
            target_id=mcp_server_id,
            metadata={"name": server["name"], "method": payload.method, "connection_type": server["connection_type"]},
        )
        TraceStore().add_mcp_call(
            payload.agent_run_id,
            mcp_server_id,
            payload.method,
            str(payload.params)[:1000],
            str(error)[:1000],
            "failed",
        )
        if payload.agent_run_id is not None:
            TraceStore().add_tool_call(
                payload.agent_run_id,
                f"mcp:{server['name']}",
                payload.method,
                str(error),
                "failed",
            )
        raise HTTPException(status_code=502, detail=str(error)) from error
    AuditStore().add_log(
        actor_user_id=int(request.session.get("user_id")),
        action="mcp_server.run.completed",
        target_type="mcp_server",
        target_id=mcp_server_id,
        metadata={"name": server["name"], "method": payload.method, "connection_type": server["connection_type"]},
    )
    TraceStore().add_mcp_call(
        payload.agent_run_id,
        mcp_server_id,
        payload.method,
        str(payload.params)[:1000],
        str(response)[:1000],
        "completed",
    )
    if payload.agent_run_id is not None:
        TraceStore().add_tool_call(
            payload.agent_run_id,
            f"mcp:{server['name']}",
            payload.method,
            str(response),
            "completed",
        )
    return {"mcp_server_id": mcp_server_id, "response": response}


@router.get("/agent-runs/{conversation_id}")
def list_agent_runs(conversation_id: int, request: Request):
    user_id = require_user(request)
    return {"agent_runs": fetch_all("SELECT id, conversation_id, agent_id, workflow_id, parent_run_id, status, final_response, created_at, completed_at FROM agent_runs WHERE user_id = %s AND conversation_id = %s ORDER BY created_at DESC;", (user_id, conversation_id))}


@router.get("/agent-events/{agent_run_id}")
def list_agent_events(agent_run_id: int, request: Request):
    user_id = require_user(request)
    query = """
        SELECT e.id, e.agent_run_id, e.event_type, e.title, e.content, e.created_at
        FROM agent_events e
        JOIN agent_runs r ON r.id = e.agent_run_id
        WHERE r.user_id = %s AND e.agent_run_id = %s
        ORDER BY e.created_at, e.id;
    """
    return {"agent_events": fetch_all(query, (user_id, agent_run_id))}


@router.get("/sources/{agent_run_id}")
def list_sources(agent_run_id: int, request: Request):
    user_id = require_user(request)
    query = """
        SELECT s.id, s.agent_run_id, s.url, s.title, s.snippet, s.created_at
        FROM sources s
        JOIN agent_runs r ON r.id = s.agent_run_id
        WHERE r.user_id = %s AND s.agent_run_id = %s
        ORDER BY s.created_at, s.id;
    """
    return {"sources": fetch_all(query, (user_id, agent_run_id))}


@router.get("/tool-calls/{agent_run_id}")
def list_tool_calls(agent_run_id: int, request: Request):
    user_id = require_user(request)
    query = """
        SELECT t.id, t.agent_run_id, t.skill_name, t.input_summary, t.output_summary, t.status, t.created_at
        FROM tool_calls t
        JOIN agent_runs r ON r.id = t.agent_run_id
        WHERE r.user_id = %s AND t.agent_run_id = %s
        ORDER BY t.created_at, t.id;
    """
    return {"tool_calls": fetch_all(query, (user_id, agent_run_id))}
