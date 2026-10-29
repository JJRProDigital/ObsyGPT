"""Admin endpoints for personal API key management.

Keys belong to the authenticated user (require_user, not require_admin):
every ObsyGPT user can mint and revoke their own keys for the /v1 endpoint.
The plaintext key is returned exactly once by the create endpoint and is
never stored or logged; audit metadata only carries prefix and name.
"""

from fastapi import APIRouter, HTTPException, Request
from pydantic import BaseModel, Field, field_validator

from .. import audit as audit_module
from ..auth import routes as auth
from ..v1 import keys as v1_keys


router = APIRouter()


class ApiKeyCreatePayload(BaseModel):
    name: str = Field(min_length=1, max_length=100)

    @field_validator("name")
    @classmethod
    def strip_name(cls, value: str) -> str:
        stripped = value.strip()
        if not stripped:
            raise ValueError("API key name is required.")
        return stripped


@router.get("/api-keys")
def list_api_keys(request: Request):
    user_id = auth.require_user(request)
    return {"api_keys": v1_keys.list_api_keys(user_id)}


@router.post("/api-keys", status_code=201)
def create_api_key(payload: ApiKeyCreatePayload, request: Request):
    user_id = auth.require_user(request)
    created = v1_keys.create_api_key(user_id, payload.name)
    audit_module.AuditStore().add_log(
        actor_user_id=user_id,
        action="api_key.created",
        target_type="api_key",
        target_id=created["id"],
        metadata={"prefix": created["prefix"], "name": created["name"]},
    )
    return {"api_key": created}


@router.post("/api-keys/{key_id}/revoke")
def revoke_api_key(key_id: int, request: Request):
    user_id = auth.require_user(request)
    if not v1_keys.revoke_api_key(user_id, key_id):
        raise HTTPException(status_code=404, detail="API key not found.")
    audit_module.AuditStore().add_log(
        actor_user_id=user_id,
        action="api_key.revoked",
        target_type="api_key",
        target_id=key_id,
        metadata={},
    )
    return {"revoked": True}
