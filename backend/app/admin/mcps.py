"""Admin MCP server endpoints: CRUD, inspect, validate, run, agent bindings."""

from typing import Literal

from fastapi import APIRouter, HTTPException, Request
from pydantic import BaseModel, Field, field_validator, model_validator

from .. import audit as audit_module
from ..auth import routes as auth
from ..mcps import gateway as mcp_gateway
from ..traces import store as trace_store_mod
from . import queries
from .queries import ensure_positive_id


router = APIRouter()


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


@router.get("/mcp-servers")
def list_mcp_servers(request: Request):
    auth.require_user(request)
    return {"mcp_servers": queries.fetch_all("SELECT id, name, description, connection_type, command, url, enabled FROM mcp_servers ORDER BY name;")}


@router.get("/agent-mcps")
def list_agent_mcps(request: Request):
    auth.require_user(request)
    return {"agent_mcps": queries.fetch_all("SELECT agent_id, mcp_server_id FROM agent_mcps ORDER BY agent_id, mcp_server_id;")}


@router.post("/agents/{agent_id}/mcps/{mcp_server_id}")
def assign_agent_mcp(agent_id: int, mcp_server_id: int, request: Request):
    auth.require_admin(request)
    try:
        agent_id = ensure_positive_id(agent_id, "agent_id")
        mcp_server_id = ensure_positive_id(mcp_server_id, "mcp_server_id")
    except ValueError as error:
        raise HTTPException(status_code=400, detail=str(error)) from error

    queries.execute_returning(
        """
        INSERT INTO agent_mcps (agent_id, mcp_server_id)
        VALUES (%s, %s)
        ON CONFLICT (agent_id, mcp_server_id) DO UPDATE SET agent_id = EXCLUDED.agent_id
        RETURNING agent_id, mcp_server_id;
        """,
        (agent_id, mcp_server_id),
    )
    audit_module.AuditStore().add_log(
        actor_user_id=int(request.session.get("user_id")),
        action="agent_mcp.assigned",
        target_type="agent",
        target_id=agent_id,
        metadata={"mcp_server_id": mcp_server_id},
    )
    return {"agent_id": agent_id, "mcp_server_id": mcp_server_id}


@router.delete("/agents/{agent_id}/mcps/{mcp_server_id}")
def remove_agent_mcp(agent_id: int, mcp_server_id: int, request: Request):
    auth.require_admin(request)
    try:
        agent_id = ensure_positive_id(agent_id, "agent_id")
        mcp_server_id = ensure_positive_id(mcp_server_id, "mcp_server_id")
    except ValueError as error:
        raise HTTPException(status_code=400, detail=str(error)) from error

    from .. import db as app_db

    with app_db.connect() as connection:
        with connection.cursor() as cursor:
            cursor.execute("DELETE FROM agent_mcps WHERE agent_id = %s AND mcp_server_id = %s;", (agent_id, mcp_server_id))
    audit_module.AuditStore().add_log(
        actor_user_id=int(request.session.get("user_id")),
        action="agent_mcp.removed",
        target_type="agent",
        target_id=agent_id,
        metadata={"mcp_server_id": mcp_server_id},
    )
    return {"agent_id": agent_id, "mcp_server_id": mcp_server_id, "removed": True}


@router.post("/mcp-servers")
def create_mcp_server(payload: McpServerPayload, request: Request):
    auth.require_admin(request)
    try:
        mcp_gateway.McpGateway().validate(mcp_gateway.McpServerConfig(payload.name, payload.description, payload.connection_type, payload.command, payload.url, payload.enabled))
    except ValueError as error:
        raise HTTPException(status_code=400, detail=str(error)) from error
    server = queries.execute_returning(
        """
        INSERT INTO mcp_servers (name, description, connection_type, command, url, enabled)
        VALUES (%s, %s, %s, %s, %s, %s)
        RETURNING id, name, description, connection_type, command, url, enabled;
        """,
        (payload.name, payload.description, payload.connection_type, payload.command, payload.url, payload.enabled),
    )
    audit_module.AuditStore().add_log(
        actor_user_id=int(request.session.get("user_id")),
        action="mcp_server.created",
        target_type="mcp_server",
        target_id=server["id"],
        metadata={"name": server["name"], "connection_type": server["connection_type"], "enabled": server["enabled"]},
    )
    return {"mcp_server": server}


@router.patch("/mcp-servers/{mcp_server_id}")
def update_mcp_server(mcp_server_id: int, payload: McpServerPayload, request: Request):
    auth.require_admin(request)
    try:
        mcp_gateway.McpGateway().validate(mcp_gateway.McpServerConfig(payload.name, payload.description, payload.connection_type, payload.command, payload.url, payload.enabled))
    except ValueError as error:
        raise HTTPException(status_code=400, detail=str(error)) from error
    try:
        mcp_server_id = ensure_positive_id(mcp_server_id, "mcp_server_id")
    except ValueError as error:
        raise HTTPException(status_code=400, detail=str(error)) from error

    server = queries.execute_returning(
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
    audit_module.AuditStore().add_log(
        actor_user_id=int(request.session.get("user_id")),
        action="mcp_server.updated",
        target_type="mcp_server",
        target_id=server["id"],
        metadata={"name": server["name"], "connection_type": server["connection_type"], "enabled": server["enabled"]},
    )
    return {"mcp_server": server}


@router.delete("/mcp-servers/{mcp_server_id}")
def delete_mcp_server(mcp_server_id: int, request: Request):
    auth.require_admin(request)
    try:
        mcp_server_id = ensure_positive_id(mcp_server_id, "mcp_server_id")
    except ValueError as error:
        raise HTTPException(status_code=400, detail=str(error)) from error
    server = queries.execute_returning(
        "DELETE FROM mcp_servers WHERE id = %s RETURNING id, name;",
        (mcp_server_id,),
    )
    if not server:
        raise HTTPException(status_code=404, detail="MCP server not found.")
    audit_module.AuditStore().add_log(
        actor_user_id=int(request.session.get("user_id")),
        action="mcp_server.deleted",
        target_type="mcp_server",
        target_id=server["id"],
        metadata={"name": server["name"]},
    )
    return {"id": server["id"], "deleted": True}


@router.post("/mcp-servers/{mcp_server_id}/inspect")
def inspect_mcp_server(mcp_server_id: int, request: Request):
    auth.require_admin(request)
    try:
        mcp_server_id = ensure_positive_id(mcp_server_id, "mcp_server_id")
    except ValueError as error:
        raise HTTPException(status_code=400, detail=str(error)) from error

    server = queries.fetch_one(
        "SELECT id, name, connection_type, command, url FROM mcp_servers WHERE id = %s;",
        (mcp_server_id,),
    )
    if not server:
        raise HTTPException(status_code=404, detail="MCP server not found.")
    gateway = mcp_gateway.McpGateway()
    try:
        if server["connection_type"] == "command":
            inspection = gateway.inspect_command(server["command"])
        else:
            inspection = gateway.inspect_url(server["url"])
    except (RuntimeError, ValueError) as error:
        raise HTTPException(status_code=502, detail=str(error)) from error
    audit_module.AuditStore().add_log(
        actor_user_id=int(request.session.get("user_id")),
        action="mcp_server.inspected",
        target_type="mcp_server",
        target_id=mcp_server_id,
        metadata={"name": server["name"], "tool_count": len(inspection["tools"]), "connection_type": server["connection_type"]},
    )
    return {"mcp_server_id": mcp_server_id, "server_info": inspection["server_info"], "tools": inspection["tools"]}


@router.post("/mcp-servers/validate")
def validate_mcp_server(payload: McpServerPayload, request: Request):
    auth.require_admin(request)
    validation = mcp_gateway.McpGateway().validate(
        mcp_gateway.McpServerConfig(
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
    auth.require_admin(request)
    try:
        mcp_server_id = ensure_positive_id(mcp_server_id, "mcp_server_id")
    except ValueError as error:
        raise HTTPException(status_code=400, detail=str(error)) from error

    server = queries.fetch_one(
        "SELECT id, name, description, connection_type, command, url, enabled FROM mcp_servers WHERE id = %s;",
        (mcp_server_id,),
    )
    if not server:
        raise HTTPException(status_code=404, detail="MCP server not found.")
    if not server["enabled"]:
        raise HTTPException(status_code=400, detail="MCP server is disabled.")
    gateway = mcp_gateway.McpGateway()
    try:
        if server["connection_type"] == "command":
            response = gateway.call_command(server["command"], payload.method, payload.params)
        else:
            response = gateway.call_url(server["url"], payload.method, payload.params)
    except RuntimeError as error:
        audit_module.AuditStore().add_log(
            actor_user_id=int(request.session.get("user_id")),
            action="mcp_server.run.failed",
            target_type="mcp_server",
            target_id=mcp_server_id,
            metadata={"name": server["name"], "method": payload.method, "connection_type": server["connection_type"]},
        )
        trace_store_mod.TraceStore().add_mcp_call(
            payload.agent_run_id,
            mcp_server_id,
            payload.method,
            str(payload.params)[:1000],
            str(error)[:1000],
            "failed",
        )
        if payload.agent_run_id is not None:
            trace_store_mod.TraceStore().add_tool_call(
                payload.agent_run_id,
                f"mcp:{server['name']}",
                payload.method,
                str(error),
                "failed",
            )
        raise HTTPException(status_code=502, detail=str(error)) from error
    audit_module.AuditStore().add_log(
        actor_user_id=int(request.session.get("user_id")),
        action="mcp_server.run.completed",
        target_type="mcp_server",
        target_id=mcp_server_id,
        metadata={"name": server["name"], "method": payload.method, "connection_type": server["connection_type"]},
    )
    trace_store_mod.TraceStore().add_mcp_call(
        payload.agent_run_id,
        mcp_server_id,
        payload.method,
        str(payload.params)[:1000],
        str(response)[:1000],
        "completed",
    )
    if payload.agent_run_id is not None:
        trace_store_mod.TraceStore().add_tool_call(
            payload.agent_run_id,
            f"mcp:{server['name']}",
            payload.method,
            str(response),
            "completed",
        )
    return {"mcp_server_id": mcp_server_id, "response": response}
