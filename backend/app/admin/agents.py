"""Admin agent management endpoints: CRUD, skills, tools, fallbacks."""

from fastapi import APIRouter, HTTPException, Request
from pydantic import BaseModel, Field, field_validator

from .. import audit as audit_module
from .. import db as app_db
from ..auth import routes as auth
from . import queries
from .queries import ensure_positive_id


router = APIRouter()


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


class AgentToolsPayload(BaseModel):
    tools: list[str] = Field(default_factory=list)

    @field_validator("tools")
    @classmethod
    def dedupe_tools(cls, value: list[str]) -> list[str]:
        return list(dict.fromkeys(item.strip() for item in value if item.strip()))


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


@router.get("/agents")
def list_agents(request: Request):
    auth.require_user(request)
    return {"agents": queries.fetch_all("SELECT id, name, description, system_prompt, provider_id, model_id, temperature, internet_enabled, multimodal_enabled, agentic_mode, enabled, telegram_enabled, telegram_allowlist, telegram_bot_token IS NOT NULL AS telegram_bot_token_set FROM agents ORDER BY name;")}


@router.get("/agent-skills")
def list_agent_skills(request: Request):
    auth.require_user(request)
    return {"agent_skills": queries.fetch_all("SELECT agent_id, skill_id FROM agent_skills ORDER BY agent_id, skill_id;")}


@router.post("/agents/{agent_id}/skills/{skill_id}")
def assign_agent_skill(agent_id: int, skill_id: int, request: Request):
    auth.require_admin(request)
    try:
        agent_id = ensure_positive_id(agent_id, "agent_id")
        skill_id = ensure_positive_id(skill_id, "skill_id")
    except ValueError as error:
        raise HTTPException(status_code=400, detail=str(error)) from error

    queries.execute_returning(
        """
        INSERT INTO agent_skills (agent_id, skill_id)
        VALUES (%s, %s)
        ON CONFLICT (agent_id, skill_id) DO UPDATE SET agent_id = EXCLUDED.agent_id
        RETURNING agent_id, skill_id;
        """,
        (agent_id, skill_id),
    )
    audit_module.AuditStore().add_log(
        actor_user_id=int(request.session.get("user_id")),
        action="agent_skill.assigned",
        target_type="agent",
        target_id=agent_id,
        metadata={"skill_id": skill_id},
    )
    return {"agent_id": agent_id, "skill_id": skill_id}


@router.delete("/agents/{agent_id}/skills/{skill_id}")
def remove_agent_skill(agent_id: int, skill_id: int, request: Request):
    auth.require_admin(request)
    try:
        agent_id = ensure_positive_id(agent_id, "agent_id")
        skill_id = ensure_positive_id(skill_id, "skill_id")
    except ValueError as error:
        raise HTTPException(status_code=400, detail=str(error)) from error

    with app_db.connect() as connection:
        with connection.cursor() as cursor:
            cursor.execute("DELETE FROM agent_skills WHERE agent_id = %s AND skill_id = %s;", (agent_id, skill_id))
    audit_module.AuditStore().add_log(
        actor_user_id=int(request.session.get("user_id")),
        action="agent_skill.removed",
        target_type="agent",
        target_id=agent_id,
        metadata={"skill_id": skill_id},
    )
    return {"agent_id": agent_id, "skill_id": skill_id, "removed": True}


@router.post("/agents")
def create_agent(payload: AgentPayload, request: Request):
    auth.require_admin(request)
    agent = queries.execute_returning(
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
    audit_module.AuditStore().add_log(
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
    auth.require_admin(request)
    agent = queries.execute_returning(
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
    audit_module.AuditStore().add_log(
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


class AgentTelegramPayload(BaseModel):
    enabled: bool
    bot_token: str | None = Field(default=None, max_length=200)
    allowlist: str = Field(default="", max_length=4000)

    @field_validator("bot_token")
    @classmethod
    def strip_token(cls, value: str | None) -> str | None:
        if value is None:
            return None
        return value.strip()

    @field_validator("allowlist")
    @classmethod
    def validate_allowlist(cls, value: str) -> str:
        from ..telegram.gateway import parse_allowlist

        normalized = ",".join(f"{tg_id}:{username}" for tg_id, username in parse_allowlist(value).items())
        return normalized


@router.put("/agents/{agent_id}/telegram")
def set_agent_telegram(agent_id: int, payload: AgentTelegramPayload, request: Request):
    auth.require_admin(request)
    agent_id = ensure_positive_id(agent_id, "agent_id")
    from ..telegram import store as tg_store

    agent = queries.fetch_one("SELECT id, name FROM agents WHERE id = %s;", (agent_id,))
    if not agent:
        raise HTTPException(status_code=404, detail="Agent not found.")
    config = tg_store.get_agent_telegram_config(agent_id)
    # Semantics: bot_token None keeps the stored token, "" clears it, a value replaces it.
    token_cleared = payload.bot_token == ""
    encrypted_token = payload.bot_token if payload.bot_token else None
    if payload.enabled and not token_cleared and not (encrypted_token or (config and config.get("telegram_bot_token"))):
        raise HTTPException(status_code=400, detail="A bot token is required to enable Telegram.")
    updated = tg_store.set_agent_telegram_config(
        agent_id,
        enabled=payload.enabled,
        encrypted_token=encrypted_token,
        token_cleared=token_cleared,
        allowlist=payload.allowlist,
    )
    audit_module.AuditStore().add_log(
        actor_user_id=int(request.session.get("user_id")),
        action="agent_telegram.updated",
        target_type="agent",
        target_id=agent_id,
        metadata={"telegram_enabled": payload.enabled, "allowlist_entries": len(payload.allowlist.split(",")) if payload.allowlist else 0},
    )
    return {
        "telegram": {
            "agent_id": agent_id,
            "telegram_enabled": updated["telegram_enabled"],
            "telegram_allowlist": updated["telegram_allowlist"],
            "telegram_bot_token_set": bool(updated["telegram_bot_token"]),
        }
    }


@router.post("/agents/{agent_id}/telegram/verify")
def verify_agent_telegram(agent_id: int, request: Request):
    auth.require_admin(request)
    agent_id = ensure_positive_id(agent_id, "agent_id")
    from ..telegram import store as tg_store
    from ..telegram.gateway import TelegramGatewayError, verify_token_sync

    token = tg_store.get_agent_bot_token(agent_id)
    if not token:
        raise HTTPException(status_code=400, detail="This agent has no Telegram bot token configured.")
    try:
        me = verify_token_sync(token)
    except TelegramGatewayError as error:
        raise HTTPException(status_code=400, detail=f"Telegram rejected the token: {error}") from error
    return {"bot_username": me.get("username"), "bot_name": me.get("first_name")}


@router.get("/agent-tools")
def list_agent_tools(request: Request):
    auth.require_user(request)
    return {"agent_tools": queries.fetch_all("SELECT agent_id, tool_name, allowed FROM agent_tool_permissions ORDER BY agent_id, tool_name;")}


@router.get("/agent-fallbacks")
def list_agent_fallbacks(request: Request):
    auth.require_user(request)
    return {
        "agent_fallbacks": queries.fetch_all(
            """
            SELECT af.agent_id, af.provider_id, af.model_id, af.priority, p.name AS provider_name, m.display_name AS model_display_name
            FROM agent_fallbacks af
            JOIN providers p ON p.id = af.provider_id
            JOIN models m ON m.id = af.model_id
            ORDER BY af.agent_id, af.priority;
            """
        )
    }


@router.put("/agents/{agent_id}/fallbacks")
def set_agent_fallbacks(agent_id: int, payload: AgentFallbackPayload, request: Request):
    auth.require_admin(request)
    agent_id = ensure_positive_id(agent_id, "agent_id")
    agent = queries.fetch_one("SELECT id, name FROM agents WHERE id = %s;", (agent_id,))
    if not agent:
        raise HTTPException(status_code=404, detail="Agent not found.")
    for item in payload.fallbacks:
        model = queries.fetch_one(
            """
            SELECT m.id FROM models m
            JOIN providers p ON p.id = m.provider_id
            WHERE m.id = %s AND p.id = %s AND m.enabled = true AND p.enabled = true;
            """,
            (item["model_id"], item["provider_id"]),
        )
        if not model:
            raise HTTPException(status_code=400, detail=f"Model {item['model_id']} is not an enabled model of provider {item['provider_id']}.")

    with app_db.connect() as connection:
        with connection.cursor() as cursor:
            cursor.execute("DELETE FROM agent_fallbacks WHERE agent_id = %s;", (agent_id,))
            for priority, item in enumerate(payload.fallbacks, start=1):
                cursor.execute(
                    "INSERT INTO agent_fallbacks (agent_id, provider_id, model_id, priority) VALUES (%s, %s, %s, %s);",
                    (agent_id, item["provider_id"], item["model_id"], priority),
                )

    audit_module.AuditStore().add_log(
        actor_user_id=int(request.session.get("user_id")),
        action="agent_fallbacks.updated",
        target_type="agent",
        target_id=agent_id,
        metadata={"fallbacks": payload.fallbacks},
    )
    return {"agent_id": agent_id, "fallbacks": payload.fallbacks}


@router.put("/agents/{agent_id}/tools")
def set_agent_tools(agent_id: int, payload: AgentToolsPayload, request: Request):
    auth.require_admin(request)
    agent_id = ensure_positive_id(agent_id, "agent_id")
    from ..agent.routes import catalog_tool_specs

    known_tools = {spec.name for spec in catalog_tool_specs()}
    unknown = [tool for tool in payload.tools if tool not in known_tools]
    if unknown:
        raise HTTPException(status_code=400, detail=f"Unknown tools: {', '.join(unknown)}")

    agent = queries.fetch_one("SELECT id, name FROM agents WHERE id = %s;", (agent_id,))
    if not agent:
        raise HTTPException(status_code=404, detail="Agent not found.")

    with app_db.connect() as connection:
        with connection.cursor() as cursor:
            cursor.execute("DELETE FROM agent_tool_permissions WHERE agent_id = %s;", (agent_id,))
            for tool_name in payload.tools:
                cursor.execute(
                    "INSERT INTO agent_tool_permissions (agent_id, tool_name, allowed) VALUES (%s, %s, true);",
                    (agent_id, tool_name),
                )

    audit_module.AuditStore().add_log(
        actor_user_id=int(request.session.get("user_id")),
        action="agent_tools.updated",
        target_type="agent",
        target_id=agent_id,
        metadata={"tools": payload.tools},
    )
    return {"agent_id": agent_id, "tools": payload.tools}
