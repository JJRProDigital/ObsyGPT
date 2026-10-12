"""Admin model management endpoints."""

import os

from fastapi import APIRouter, HTTPException, Request
from pydantic import BaseModel, Field, field_validator

from .. import audit as audit_module
from ..auth import routes as auth
from . import queries
from .queries import ensure_positive_id


router = APIRouter()


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


@router.get("/models")
def list_models(request: Request):
    auth.require_user(request)
    return {"models": queries.fetch_all("SELECT id, provider_id, model_name, display_name, supports_text, supports_streaming, supports_vision, supports_audio, supports_tools, supports_json, context_window, enabled FROM models ORDER BY display_name;")}


@router.post("/models")
def create_model(payload: ModelPayload, request: Request):
    auth.require_admin(request)
    model = queries.execute_returning(
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
    audit_module.AuditStore().add_log(
        actor_user_id=int(request.session.get("user_id")),
        action="model.created",
        target_type="model",
        target_id=model["id"],
        metadata={"model_name": model["model_name"], "provider_id": model["provider_id"], "enabled": model["enabled"]},
    )
    return {"model": model}


@router.delete("/models/{model_id}")
def delete_model(model_id: int, request: Request):
    auth.require_admin(request)
    try:
        model_id = ensure_positive_id(model_id, "model_id")
    except ValueError as error:
        raise HTTPException(status_code=400, detail=str(error)) from error
    model = queries.execute_returning(
        "DELETE FROM models WHERE id = %s RETURNING id, model_name, display_name;",
        (model_id,),
    )
    if not model:
        raise HTTPException(status_code=404, detail="Model not found.")
    audit_module.AuditStore().add_log(
        actor_user_id=int(request.session.get("user_id")),
        action="model.deleted",
        target_type="model",
        target_id=model["id"],
        metadata={"model_name": model["model_name"], "display_name": model["display_name"]},
    )
    return {"id": model["id"], "deleted": True}


@router.patch("/models/{model_id}")
def update_model(model_id: int, payload: ModelPayload, request: Request):
    auth.require_admin(request)
    try:
        model_id = ensure_positive_id(model_id, "model_id")
    except ValueError as error:
        raise HTTPException(status_code=400, detail=str(error)) from error

    model = queries.execute_returning(
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
    audit_module.AuditStore().add_log(
        actor_user_id=int(request.session.get("user_id")),
        action="model.updated",
        target_type="model",
        target_id=model["id"],
        metadata={"model_name": model["model_name"], "provider_id": model["provider_id"], "enabled": model["enabled"]},
    )
    return {"model": model}


@router.post("/models/{model_id}/check")
def check_model_config(model_id: int, request: Request):
    auth.require_admin(request)
    try:
        model_id = ensure_positive_id(model_id, "model_id")
    except ValueError as error:
        raise HTTPException(status_code=400, detail=str(error)) from error

    model = queries.fetch_one(
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
