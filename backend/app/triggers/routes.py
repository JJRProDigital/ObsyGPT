"""HTTP API for event triggers: CRUD (session-authenticated) + webhook fire (secret-authenticated)."""

from fastapi import APIRouter, Header, HTTPException, Request
from pydantic import BaseModel, Field, field_validator

from ..auth.routes import require_user
from . import store as trigger_store
from .engine import TriggerEngine, is_due, render_goal
from datetime import datetime, timezone

router = APIRouter(prefix="/api", tags=["triggers"])

VALID_TYPES = ("interval", "change_detection", "webhook")


class TriggerPayload(BaseModel):
    agent_id: int = Field(ge=1)
    name: str = Field(min_length=1, max_length=120)
    trigger_type: str
    config: dict = Field(default_factory=dict)
    goal_template: str = Field(min_length=1, max_length=8000)
    notify_channel: str = ""
    notify_chat_id: int | None = None
    cooldown_seconds: int = Field(default=0, ge=0, le=30 * 24 * 3600)
    readonly: bool = True

    @field_validator("trigger_type")
    @classmethod
    def validate_type(cls, value: str) -> str:
        if value not in VALID_TYPES:
            raise ValueError(f"trigger_type must be one of: {', '.join(VALID_TYPES)}.")
        return value

    @field_validator("notify_channel")
    @classmethod
    def validate_channel(cls, value: str) -> str:
        if value not in {"", "telegram"}:
            raise ValueError("notify_channel must be '' or 'telegram'.")
        return value


def _validate_payload(payload: TriggerPayload) -> None:
    from .engine import validate_config

    if payload.notify_channel == "telegram" and not payload.notify_chat_id:
        raise ValueError("notify_channel 'telegram' requires notify_chat_id.")
    validate_config(payload.trigger_type, payload.config)


@router.get("/triggers")
def list_triggers(request: Request):
    user_id = require_user(request)
    return {"triggers": trigger_store.list_triggers(user_id)}


@router.post("/triggers")
def create_trigger(payload: TriggerPayload, request: Request):
    user_id = require_user(request)
    try:
        _validate_payload(payload)
    except ValueError as error:
        raise HTTPException(status_code=400, detail=str(error)) from error
    trigger = trigger_store.create_trigger(
        user_id,
        payload.agent_id,
        payload.name,
        payload.trigger_type,
        payload.config,
        payload.goal_template,
        notify_channel=payload.notify_channel,
        notify_chat_id=payload.notify_chat_id,
        cooldown_seconds=payload.cooldown_seconds,
        readonly=payload.readonly,
    )
    return {"trigger": trigger}


@router.patch("/triggers/{trigger_id}")
def update_trigger(trigger_id: int, payload: dict, request: Request):
    user_id = require_user(request)
    if "enabled" not in payload or not isinstance(payload["enabled"], bool):
        raise HTTPException(status_code=400, detail="Only the 'enabled' boolean field can be updated.")
    trigger = trigger_store.set_trigger_enabled(trigger_id, user_id, payload["enabled"])
    if not trigger:
        raise HTTPException(status_code=404, detail="Trigger not found.")
    return {"trigger": trigger}


@router.delete("/triggers/{trigger_id}")
def delete_trigger(trigger_id: int, request: Request):
    user_id = require_user(request)
    if not trigger_store.delete_trigger(trigger_id, user_id):
        raise HTTPException(status_code=404, detail="Trigger not found.")
    return {"ok": True}


@router.post("/triggers/{trigger_id}/fire")
def fire_trigger(trigger_id: int, request: Request, x_trigger_secret: str = Header(default="")):
    """Webhook entry point: authenticated by the per-trigger secret, not by session."""
    trigger = trigger_store.get_trigger(trigger_id)
    if not trigger or not trigger.get("enabled"):
        raise HTTPException(status_code=404, detail="Trigger not found or disabled.")
    if not trigger.get("webhook_secret") or trigger["webhook_secret"] != x_trigger_secret:
        raise HTTPException(status_code=403, detail="Invalid trigger secret.")
    if trigger["trigger_type"] != "webhook":
        raise HTTPException(status_code=400, detail="Only webhook triggers can be fired via endpoint.")
    if not is_due(trigger, datetime.now(timezone.utc)):
        return {"fired": False, "reason": "cooldown active"}
    try:
        summary = None
        payload_body = trigger.get("config") or {}
        if isinstance(payload_body, dict) and payload_body.get("summary"):
            summary = str(payload_body["summary"])[:500]
        engine = TriggerEngine()
        outcome = engine.fire_now(trigger, summary=summary, snapshot=datetime.now(timezone.utc).isoformat())
    except Exception as error:  # noqa: BLE001
        raise HTTPException(status_code=503, detail=f"Task engine unavailable: {error}") from error
    return {"fired": outcome.fired, "task_id": outcome.task_id}


@router.post("/triggers/{trigger_id}/preview")
def preview_trigger(trigger_id: int, request: Request):
    user_id = require_user(request)
    trigger = trigger_store.get_trigger(trigger_id, user_id)
    if not trigger:
        raise HTTPException(status_code=404, detail="Trigger not found.")
    goal = render_goal(trigger["goal_template"], trigger["name"], "(vista previa del contexto del disparo)")
    return {"goal": goal}
