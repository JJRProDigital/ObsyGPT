"""Admin provider management endpoints."""

from typing import Literal

from fastapi import APIRouter, HTTPException, Request
from pydantic import BaseModel, Field, field_validator

from .. import audit as audit_module
from ..auth import routes as auth
from ..connectors.crypto import encrypt_credential
from ..providers import PROVIDER_DEFINITIONS
from ..providers import registry as provider_registry
from ..providers.keys import resolve_provider_api_key
from . import queries
from .queries import ensure_positive_id


router = APIRouter()

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
    # Write-only: stored encrypted, never returned. None = keep current;
    # empty string = clear the stored key.
    api_key: str | None = Field(default=None, max_length=2000)
    enabled: bool = True

    @field_validator("name")
    @classmethod
    def strip_name(cls, value: str) -> str:
        stripped = value.strip()
        if not stripped:
            raise ValueError("Provider name is required.")
        return stripped


PROVIDER_LIST_COLUMNS = "id, name, provider_type, base_url, api_key_env, enabled, api_key_encrypted IS NOT NULL AS api_key_set"


def _stored_key_value(payload: ProviderPayload) -> str | None:
    key = (payload.api_key or "").strip()
    if payload.api_key is None:
        return None  # keep existing
    return encrypt_credential(key) if key else None  # value or cleared


@router.get("/providers")
def list_providers(request: Request):
    auth.require_user(request)
    return {"providers": queries.fetch_all(f"SELECT {PROVIDER_LIST_COLUMNS} FROM providers ORDER BY name;")}


@router.get("/provider-definitions")
def list_provider_definitions(request: Request):
    auth.require_user(request)
    return {"provider_definitions": [definition.__dict__ for definition in PROVIDER_DEFINITIONS]}


@router.post("/providers")
def create_provider(payload: ProviderPayload, request: Request):
    auth.require_admin(request)
    provider = queries.execute_returning(
        """
        INSERT INTO providers (name, provider_type, base_url, api_key_env, api_key_encrypted, enabled)
        VALUES (%s, %s, %s, %s, %s, %s)
        RETURNING id, name, provider_type, base_url, api_key_env, enabled, api_key_encrypted IS NOT NULL AS api_key_set;
        """,
        (
            payload.name,
            payload.provider_type,
            payload.base_url,
            payload.api_key_env,
            _stored_key_value(payload),
            payload.enabled,
        ),
    )
    audit_module.AuditStore().add_log(
        actor_user_id=int(request.session.get("user_id")),
        action="provider.created",
        target_type="provider",
        target_id=provider["id"],
        metadata={"name": provider["name"], "provider_type": provider["provider_type"], "enabled": provider["enabled"], "api_key_set": provider["api_key_set"]},
    )
    return {"provider": provider}


@router.patch("/providers/{provider_id}")
def update_provider(provider_id: int, payload: ProviderPayload, request: Request):
    auth.require_admin(request)
    stored_key = _stored_key_value(payload)
    if payload.api_key is None:
        existing = queries.fetch_one("SELECT api_key_encrypted FROM providers WHERE id = %s;", (provider_id,))
        if not existing:
            raise HTTPException(status_code=404, detail="Provider not found.")
        stored_key = existing["api_key_encrypted"]
    provider = queries.execute_returning(
        """
        UPDATE providers
        SET name = %s, provider_type = %s, base_url = %s, api_key_env = %s, api_key_encrypted = %s, enabled = %s
        WHERE id = %s
        RETURNING id, name, provider_type, base_url, api_key_env, enabled, api_key_encrypted IS NOT NULL AS api_key_set;
        """,
        (payload.name, payload.provider_type, payload.base_url, payload.api_key_env, stored_key, payload.enabled, provider_id),
    )
    if not provider:
        raise HTTPException(status_code=404, detail="Provider not found.")
    audit_module.AuditStore().add_log(
        actor_user_id=int(request.session.get("user_id")),
        action="provider.updated",
        target_type="provider",
        target_id=provider["id"],
        metadata={"name": provider["name"], "provider_type": provider["provider_type"], "enabled": provider["enabled"], "api_key_set": provider["api_key_set"]},
    )
    return {"provider": provider}


@router.post("/providers/{provider_id}/detect-models")
def detect_provider_models(provider_id: int, request: Request):
    auth.require_admin(request)
    provider_id = ensure_positive_id(provider_id, "provider_id")
    provider = queries.fetch_one(
        "SELECT id, name, provider_type, base_url, api_key_env, api_key_encrypted, enabled FROM providers WHERE id = %s;",
        (provider_id,),
    )
    if not provider:
        raise HTTPException(status_code=404, detail="Provider not found.")

    api_key = resolve_provider_api_key(provider["api_key_encrypted"], provider["api_key_env"])
    try:
        detected = provider_registry.list_provider_models(provider["provider_type"], api_key, provider["base_url"])
    except Exception as error:  # noqa: BLE001
        raise HTTPException(status_code=502, detail=f"Model detection failed: {error}") from error

    registered = {
        row["model_name"]
        for row in queries.fetch_all("SELECT model_name FROM models WHERE provider_id = %s;", (provider_id,))
    }
    for item in detected:
        item["already_registered"] = item["model_name"] in registered
    return {"provider_id": provider_id, "provider_name": provider["name"], "models": detected}
