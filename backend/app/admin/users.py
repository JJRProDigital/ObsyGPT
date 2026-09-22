"""Admin user management endpoints."""

from fastapi import APIRouter, HTTPException, Request
from pydantic import BaseModel
from typing import Literal

from .. import audit as audit_module
from ..auth import routes as auth
from . import queries
from .queries import ensure_positive_id


router = APIRouter()


class UserRolePayload(BaseModel):
    role: Literal["admin", "user"]


def ensure_admin_role_change_allowed(current_role: str, next_role: str, admin_count: int) -> None:
    if current_role == "admin" and next_role != "admin" and admin_count <= 1:
        raise ValueError("At least one admin user is required.")


@router.get("/users")
def list_users(request: Request):
    auth.require_admin(request)
    return {"users": queries.fetch_all("SELECT id, username, email, role, created_at FROM users ORDER BY created_at DESC, id DESC;")}


@router.patch("/users/{user_id}/role")
def update_user_role(user_id: int, payload: UserRolePayload, request: Request):
    auth.require_admin(request)
    try:
        user_id = ensure_positive_id(user_id, "user_id")
    except ValueError as error:
        raise HTTPException(status_code=400, detail=str(error)) from error

    user = queries.fetch_one("SELECT id, role FROM users WHERE id = %s;", (user_id,))
    if not user:
        raise HTTPException(status_code=404, detail="User not found.")

    admin_count_row = queries.fetch_one("SELECT COUNT(*) AS admin_count FROM users WHERE role = 'admin';", ())
    try:
        ensure_admin_role_change_allowed(user["role"], payload.role, admin_count_row["admin_count"])
    except ValueError as error:
        raise HTTPException(status_code=400, detail=str(error)) from error

    updated = queries.execute_returning(
        """
        UPDATE users
        SET role = %s
        WHERE id = %s
        RETURNING id, username, email, role, created_at;
        """,
        (payload.role, user_id),
    )
    audit_module.AuditStore().add_log(
        actor_user_id=int(request.session.get("user_id")),
        action="user.role_updated",
        target_type="user",
        target_id=user_id,
        metadata={"previous_role": user["role"], "next_role": payload.role},
    )
    return {"user": updated}
