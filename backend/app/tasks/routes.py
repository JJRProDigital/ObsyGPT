"""Background task endpoints."""

from datetime import datetime

from fastapi import APIRouter, HTTPException, Request
from pydantic import BaseModel, Field, field_validator

from ..agent.store import decide_approval, list_pending_task_approvals
from ..auth.routes import require_user
from . import store as task_store


router = APIRouter(prefix="/api/tasks", tags=["tasks"])

_manager = None


def set_manager(manager) -> None:  # noqa: ANN001
    global _manager
    _manager = manager


def require_manager():
    if _manager is None:
        raise HTTPException(status_code=503, detail="Task manager is not running.")
    return _manager


class TaskCreatePayload(BaseModel):
    goal: str = Field(min_length=1, max_length=4000)
    mode: str = "act"
    scheduled_at: str | None = None
    agent_id: int | None = None
    project_id: int | None = None
    recurrence: str | None = None

    @field_validator("goal")
    @classmethod
    def strip_goal(cls, value: str) -> str:
        stripped = value.strip()
        if not stripped:
            raise ValueError("Task goal is required.")
        return stripped

    @field_validator("mode")
    @classmethod
    def validate_mode(cls, value: str) -> str:
        normalized = value.strip().lower()
        if normalized not in {"act", "plan", "think"}:
            raise ValueError("mode must be 'act', 'plan' or 'think'.")
        return normalized

    @field_validator("recurrence")
    @classmethod
    def validate_recurrence(cls, value: str | None) -> str | None:
        if value is None or not value.strip():
            return None
        normalized = value.strip().lower()
        if normalized not in {"daily", "weekly"}:
            raise ValueError("recurrence must be 'daily' or 'weekly'.")
        return normalized

    def parsed_scheduled_at(self):  # noqa: ANN201
        if not self.scheduled_at:
            return None
        try:
            parsed = datetime.fromisoformat(self.scheduled_at.replace("Z", "+00:00"))
        except ValueError as error:
            raise ValueError("Invalid scheduled_at datetime.") from error
        if parsed.tzinfo is None:
            # datetime-local inputs have no offset: interpret the user's wall
            # clock in the server's local timezone, NOT as UTC.
            parsed = parsed.replace(tzinfo=datetime.now().astimezone().tzinfo)
        return parsed


@router.get("")
def get_tasks(request: Request, project_id: int | None = None):
    user_id = require_user(request)
    tasks = task_store.list_tasks(user_id, project_id=project_id)
    return {"tasks": tasks}


@router.post("")
def create_task(payload: TaskCreatePayload, request: Request):
    user_id = require_user(request)
    manager = require_manager()
    try:
        scheduled_at = payload.parsed_scheduled_at()
    except ValueError as error:
        raise HTTPException(status_code=400, detail=str(error)) from error
    task = manager.enqueue(
        user_id,
        payload.goal,
        mode=payload.mode,
        scheduled_at=scheduled_at,
        agent_id=payload.agent_id,
        project_id=payload.project_id,
        recurrence=payload.recurrence,
    )
    return {"task": task}


def _owned_task(task_id: int, request: Request) -> dict:
    user_id = require_user(request)
    task = task_store.get_task(task_id, user_id=user_id)
    if not task:
        raise HTTPException(status_code=404, detail="Task not found.")
    return task


@router.post("/{task_id}/pause")
def pause_task(task_id: int, request: Request):
    _owned_task(task_id, request)
    if not require_manager().pause(task_id):
        raise HTTPException(status_code=409, detail="Task cannot be paused in its current state.")
    return {"task_id": task_id, "status": "paused"}


@router.post("/{task_id}/resume")
def resume_task(task_id: int, request: Request):
    _owned_task(task_id, request)
    if not require_manager().resume(task_id):
        raise HTTPException(status_code=409, detail="Task cannot be resumed in its current state.")
    return {"task_id": task_id, "status": "pending"}


@router.post("/{task_id}/cancel")
def cancel_task(task_id: int, request: Request):
    _owned_task(task_id, request)
    if not require_manager().cancel(task_id):
        raise HTTPException(status_code=409, detail="Task cannot be cancelled in its current state.")
    return {"task_id": task_id, "status": "cancelled"}


@router.delete("/{task_id}")
def remove_task(task_id: int, request: Request):
    _owned_task(task_id, request)
    require_manager().remove(task_id)
    return {"removed": True, "task_id": task_id}


@router.get("/{task_id}/events")
def get_task_events(task_id: int, request: Request):
    _owned_task(task_id, request)
    return {"events": task_store.list_events(task_id)}


@router.get("/approvals/pending")
def pending_task_approvals(task_id: int, request: Request):
    user_id = require_user(request)
    _owned_task(task_id, request)
    approvals = []
    for approval in list_pending_task_approvals(user_id, task_id):
        approvals.append(
            {
                "id": approval["id"],
                "task_id": approval.get("task_id"),
                "tool_name": approval["tool_name"],
                "args": approval["args"] if not isinstance(approval["args"], str) else _safe_json(approval["args"]),
                "created_at": approval["created_at"].isoformat() if isinstance(approval.get("created_at"), datetime) else approval.get("created_at"),
            }
        )
    return {"approvals": approvals}


def _safe_json(value: str) -> dict:
    import json

    try:
        parsed = json.loads(value)
        return parsed if isinstance(parsed, dict) else {}
    except json.JSONDecodeError:
        return {}


@router.post("/approvals/{approval_id}/approve")
def approve_task_tool(approval_id: int, request: Request):
    return _decide(approval_id, request, approved=True)


@router.post("/approvals/{approval_id}/deny")
def deny_task_tool(approval_id: int, request: Request):
    return _decide(approval_id, request, approved=False)


def _decide(approval_id: int, request: Request, approved: bool):
    user_id = require_user(request)
    manager = require_manager()
    approval = decide_approval(approval_id, user_id, "approved" if approved else "denied")
    if not approval:
        raise HTTPException(status_code=404, detail="Approval not found or already decided.")
    task_id = approval.get("task_id")
    if not task_id:
        raise HTTPException(status_code=400, detail="This approval does not belong to a task.")
    task = task_store.get_task(task_id, user_id=user_id)
    if not task:
        raise HTTPException(status_code=404, detail="Task not found.")
    manager.resume_after_approval(user_id, task_id, approval, approved)
    return {"task_id": task_id, "approved": approved, "status": "running"}
