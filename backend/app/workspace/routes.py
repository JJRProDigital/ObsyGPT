"""Per-user workspace settings."""

from pathlib import Path

from fastapi import APIRouter, HTTPException, Request
from pydantic import BaseModel

from ..agent.tools.files import default_workspace_root
from ..auth.routes import require_user
from ..db import connect


router = APIRouter(prefix="/api/workspace", tags=["workspace"])

WORKSPACE_KEY = "workspace_root"
RECENT_KEY = "recent_workspaces"
MAX_RECENT = 5


def get_user_setting(user_id: int, key: str):
    with connect() as connection:
        with connection.cursor() as cursor:
            cursor.execute("SELECT value FROM user_settings WHERE user_id = %s AND key = %s;", (user_id, key))
            row = cursor.fetchone()
            return row[0] if row else None


def set_user_setting(user_id: int, key: str, value) -> None:
    import json

    payload = json.dumps(value)
    with connect() as connection:
        with connection.cursor() as cursor:
            cursor.execute(
                """
                INSERT INTO user_settings (user_id, key, value, updated_at)
                VALUES (%s, %s, %s::json, CURRENT_TIMESTAMP)
                ON CONFLICT (user_id, key) DO UPDATE SET value = EXCLUDED.value, updated_at = CURRENT_TIMESTAMP;
                """,
                (user_id, key, payload),
            )


def get_user_workspace(user_id: int) -> Path:
    value = get_user_setting(user_id, WORKSPACE_KEY)
    if isinstance(value, str) and value.strip():
        return Path(value.strip()).resolve()
    return default_workspace_root()


def validate_workspace_path(raw_path: str) -> Path:
    if not raw_path or not raw_path.strip():
        raise HTTPException(status_code=400, detail="Workspace path is required.")
    candidate = Path(raw_path.strip())
    if not candidate.is_absolute():
        raise HTTPException(status_code=400, detail="Workspace path must be absolute.")
    resolved = candidate.resolve()
    if not resolved.exists():
        raise HTTPException(status_code=400, detail=f"Path does not exist: {resolved}")
    if not resolved.is_dir():
        raise HTTPException(status_code=400, detail=f"Path is not a directory: {resolved}")
    return resolved


class WorkspacePayload(BaseModel):
    path: str


PREFERENCE_DEFAULTS = {
    "display_name": "",
    "accent": "gold",
    "memory_max": 30,
    "tool_policies": {},
    "instructions": "",
}

MAX_INSTRUCTIONS_CHARS = 4000


def get_user_preferences(user_id: int) -> dict:
    stored = get_user_setting(user_id, "preferences")
    prefs = dict(PREFERENCE_DEFAULTS)
    if isinstance(stored, dict):
        prefs.update(stored)
    return prefs


def set_user_preferences(user_id: int, prefs: dict) -> dict:
    current = get_user_preferences(user_id)
    current.update(prefs)
    set_user_setting(user_id, "preferences", current)
    return current


class PreferencesPayload(BaseModel):
    display_name: str | None = None
    accent: str | None = None
    memory_max: int | None = None
    tool_policies: dict | None = None
    instructions: str | None = None


@router.get("/preferences")
def read_preferences(request: Request):
    user_id = require_user(request)
    return {"preferences": get_user_preferences(user_id)}


@router.put("/preferences")
def write_preferences(payload: PreferencesPayload, request: Request):
    user_id = require_user(request)
    updates = payload.model_dump(exclude_none=True)
    if "memory_max" in updates:
        memory_max = updates["memory_max"]
        if not isinstance(memory_max, int) or memory_max < 1 or memory_max > 100:
            raise HTTPException(status_code=400, detail="memory_max must be between 1 and 100.")
    if "accent" in updates and updates["accent"] not in {"gold", "teal", "violet", "magenta", "ice"}:
        raise HTTPException(status_code=400, detail="accent must be one of: gold, teal, violet, magenta, ice.")
    if "tool_policies" in updates and not isinstance(updates["tool_policies"], dict):
        raise HTTPException(status_code=400, detail="tool_policies must be an object.")
    if "instructions" in updates:
        if not isinstance(updates["instructions"], str):
            raise HTTPException(status_code=400, detail="instructions must be a string.")
        if len(updates["instructions"]) > MAX_INSTRUCTIONS_CHARS:
            raise HTTPException(status_code=400, detail=f"instructions must be at most {MAX_INSTRUCTIONS_CHARS} characters.")
        updates["instructions"] = updates["instructions"].strip()
    return {"preferences": set_user_preferences(user_id, updates)}


@router.get("")
def get_workspace(request: Request):
    user_id = require_user(request)
    workspace = get_user_workspace(user_id)
    recent = get_user_setting(user_id, RECENT_KEY)
    return {
        "workspace": str(workspace),
        "recent": recent if isinstance(recent, list) else [],
        "default": str(default_workspace_root()),
    }


@router.put("")
def set_workspace(payload: WorkspacePayload, request: Request):
    user_id = require_user(request)
    resolved = validate_workspace_path(payload.path)
    previous = get_user_workspace(user_id)
    set_user_setting(user_id, WORKSPACE_KEY, str(resolved))

    recent = get_user_setting(user_id, RECENT_KEY)
    recent = recent if isinstance(recent, list) else []
    updated_recent = [str(resolved), *[item for item in recent if item != str(resolved)]][:MAX_RECENT]
    set_user_setting(user_id, RECENT_KEY, updated_recent)

    return {"workspace": str(resolved), "previous": str(previous), "recent": updated_recent}
