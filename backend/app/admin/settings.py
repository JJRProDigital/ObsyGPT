"""Admin runtime settings endpoints: guardrails and task engine."""

import json

from fastapi import APIRouter, Request
from pydantic import BaseModel, Field

from .. import audit as audit_module
from ..auth import routes as auth
from . import queries


router = APIRouter()


class GuardrailSettingsPayload(BaseModel):
    max_iterations: int | None = Field(default=None, ge=1, le=100)
    max_tool_calls: int | None = Field(default=None, ge=1, le=500)
    max_duration_seconds: int | None = Field(default=None, ge=1, le=7200)
    max_tool_output_chars: int | None = Field(default=None, ge=100, le=1_000_000)
    max_total_chars: int | None = Field(default=None, ge=1000, le=10_000_000)
    loop_repeat_limit: int | None = Field(default=None, ge=2, le=10)


class TasksSettingsPayload(BaseModel):
    max_concurrent_tasks: int | None = Field(default=None, ge=1, le=4)
    auto_resume_tasks: bool | None = None


@router.get("/settings/guardrails")
def list_guardrail_settings(request: Request):
    auth.require_admin(request)
    row = queries.fetch_one("SELECT value FROM app_settings WHERE key = 'guardrails';", ())
    return {"guardrails": (row or {}).get("value", {})}


@router.get("/settings/tasks")
def list_tasks_settings(request: Request):
    auth.require_admin(request)
    row = queries.fetch_one("SELECT value FROM app_settings WHERE key = 'tasks';", ())
    return {"tasks": (row or {}).get("value", {"max_concurrent_tasks": 1, "auto_resume_tasks": True})}


@router.put("/settings/tasks")
def update_tasks_settings(settings: TasksSettingsPayload, request: Request):
    auth.require_admin(request)
    current_row = queries.fetch_one("SELECT value FROM app_settings WHERE key = 'tasks';", ())
    current = current_row.get("value", {}) if current_row else {}
    payload = {**current, **{key: value for key, value in settings.model_dump().items() if value is not None}}
    row = queries.execute_returning(
        """
        INSERT INTO app_settings (key, value)
        VALUES ('tasks', %s::json)
        ON CONFLICT (key) DO UPDATE SET value = EXCLUDED.value
        RETURNING value;
        """,
        (json.dumps(payload),),
    )
    audit_module.AuditStore().add_log(
        actor_user_id=int(request.session.get("user_id")),
        action="tasks_settings.updated",
        target_type="settings",
        target_id=None,
        metadata=payload,
    )
    return {"tasks": row["value"]}


@router.put("/settings/guardrails")
def update_guardrail_settings(settings: GuardrailSettingsPayload, request: Request):
    auth.require_admin(request)
    payload = {key: value for key, value in settings.model_dump().items() if value is not None}
    row = queries.execute_returning(
        """
        INSERT INTO app_settings (key, value)
        VALUES ('guardrails', %s::json)
        ON CONFLICT (key) DO UPDATE SET value = EXCLUDED.value
        RETURNING value;
        """,
        (json.dumps(payload),),
    )
    audit_module.AuditStore().add_log(
        actor_user_id=int(request.session.get("user_id")),
        action="guardrails.updated",
        target_type="settings",
        target_id=None,
        metadata=payload,
    )
    return {"guardrails": row["value"]}
