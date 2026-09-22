"""Admin workflow management endpoints."""

from typing import Literal

from fastapi import APIRouter, HTTPException, Request
from pydantic import BaseModel, Field, field_validator

from .. import audit as audit_module
from .. import db as app_db
from ..auth import routes as auth
from . import queries
from .queries import ensure_positive_id


router = APIRouter()


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


@router.get("/workflows")
def list_workflows(request: Request):
    auth.require_user(request)
    workflows = queries.fetch_all("SELECT id, name, workflow_type, enabled FROM workflows ORDER BY name;")
    steps = queries.fetch_all("SELECT workflow_id, agent_id, step_order, step_name FROM workflow_steps ORDER BY workflow_id, step_order;")
    return {"workflows": workflows, "workflow_steps": steps}


@router.post("/workflows")
def create_workflow(payload: WorkflowPayload, request: Request):
    auth.require_admin(request)
    with app_db.connect() as connection:
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

    audit_module.AuditStore().add_log(
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
    auth.require_admin(request)
    try:
        workflow_id = ensure_positive_id(workflow_id, "workflow_id")
    except ValueError as error:
        raise HTTPException(status_code=400, detail=str(error)) from error

    with app_db.connect() as connection:
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

    audit_module.AuditStore().add_log(
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
