"""User-facing memory endpoints."""

from fastapi import APIRouter, HTTPException, Request
from pydantic import BaseModel, Field, field_validator

from ..auth.routes import require_user
from . import store


router = APIRouter(prefix="/api/memory", tags=["memory"])


class MemoryPayload(BaseModel):
    content: str = Field(min_length=1, max_length=4000)
    kind: str = "memory"
    project_id: int | None = None

    @field_validator("content")
    @classmethod
    def strip_content(cls, value: str) -> str:
        stripped = value.strip()
        if not stripped:
            raise ValueError("Memory content is required.")
        return stripped

    @field_validator("kind")
    @classmethod
    def validate_kind(cls, value: str) -> str:
        normalized = value.strip().lower()
        if normalized not in store.MEMORY_KINDS:
            raise ValueError("kind must be 'memory' or 'habit'.")
        return normalized


@router.get("")
def get_memories(kind: str | None = None, project_id: int | None = None, request: Request = None):  # noqa: RUF013
    user_id = require_user(request)
    normalized = kind.strip().lower() if kind else None
    if normalized and normalized not in store.MEMORY_KINDS:
        raise HTTPException(status_code=400, detail="kind must be 'memory' or 'habit'.")
    if project_id is not None:
        return {"memories": store.list_memories(user_id, project_id=project_id)}
    return {"memories": store.list_memories(user_id, kind=normalized)}


@router.post("")
def add_memory(payload: MemoryPayload, request: Request):
    user_id = require_user(request)
    try:
        memory = store.create_memory(user_id, payload.content, payload.kind, project_id=payload.project_id)
    except ValueError as error:
        raise HTTPException(status_code=409, detail=str(error)) from error
    return {"memory": memory}


@router.delete("/habits/all")
def reset_habits(request: Request):
    user_id = require_user(request)
    removed = store.delete_all_habits(user_id)
    return {"removed": removed}


@router.get("/habits/suggestions")
def list_suggestions(request: Request):
    user_id = require_user(request)
    return {"suggestions": store.list_habit_suggestions(user_id)}


@router.post("/habits/suggestions/{suggestion_id}/accept")
def accept_suggestion(suggestion_id: int, request: Request):
    user_id = require_user(request)
    try:
        result = store.decide_habit_suggestion(user_id, suggestion_id, "accept")
    except ValueError as error:
        raise HTTPException(status_code=400, detail=str(error)) from error
    if not result:
        raise HTTPException(status_code=404, detail="Suggestion not found or already decided.")
    return result


@router.post("/habits/suggestions/{suggestion_id}/dismiss")
def dismiss_suggestion(suggestion_id: int, request: Request):
    user_id = require_user(request)
    try:
        result = store.decide_habit_suggestion(user_id, suggestion_id, "dismiss")
    except ValueError as error:
        raise HTTPException(status_code=400, detail=str(error)) from error
    if not result:
        raise HTTPException(status_code=404, detail="Suggestion not found or already decided.")
    return result


@router.delete("/{memory_id}")
def remove_memory(memory_id: int, request: Request):
    user_id = require_user(request)
    if not store.delete_memory(user_id, memory_id):
        raise HTTPException(status_code=404, detail="Memory not found.")
    return {"removed": True, "memory_id": memory_id}
