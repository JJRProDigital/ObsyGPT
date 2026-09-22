"""Admin audit log endpoints."""

from typing import Annotated

from fastapi import APIRouter, Query, Request

from ..auth import routes as auth
from . import queries


router = APIRouter()


@router.get("/audit-logs")
def list_audit_logs(
    request: Request,
    limit: Annotated[int, Query(ge=1, le=500)] = 100,
    action: Annotated[str | None, Query(max_length=120)] = None,
    target_type: Annotated[str | None, Query(max_length=80)] = None,
):
    auth.require_admin(request)
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
    logs = queries.fetch_all(
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
