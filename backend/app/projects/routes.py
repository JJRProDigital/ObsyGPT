"""Project endpoints: group conversations, files, and custom instructions."""

import re
import unicodedata
from pathlib import Path

from fastapi import APIRouter, File, HTTPException, Request, UploadFile
from pydantic import BaseModel, Field, field_validator

from ..auth.routes import require_user
from . import store


router = APIRouter(prefix="/api/projects", tags=["projects"])

MAX_FILE_ENTRIES = 200


def _slugify(name: str) -> str:
    normalized = unicodedata.normalize("NFKD", name).encode("ascii", "ignore").decode("ascii")
    slug = re.sub(r"[^a-z0-9]+", "-", normalized.lower()).strip("-")
    return slug[:40]


def _validate_folder_path(raw: str | None) -> str | None:
    if raw is None or not raw.strip():
        return None
    candidate = Path(raw.strip())
    if not candidate.is_absolute():
        raise HTTPException(status_code=400, detail="Project folder path must be absolute.")
    resolved = candidate.resolve()
    if not resolved.exists() or not resolved.is_dir():
        raise HTTPException(status_code=400, detail=f"Project folder does not exist or is not a directory: {resolved}")
    return str(resolved)


class ProjectPayload(BaseModel):
    name: str = Field(min_length=1, max_length=120)
    description: str = Field(default="", max_length=2000)
    instructions: str = Field(default="", max_length=20000)
    folder_path: str | None = None

    @field_validator("name")
    @classmethod
    def strip_name(cls, value: str) -> str:
        stripped = value.strip()
        if not stripped:
            raise ValueError("Project name is required.")
        return stripped

    @field_validator("description", "instructions")
    @classmethod
    def strip_fields(cls, value: str) -> str:
        return value.strip()


class ProjectUpdatePayload(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=120)
    description: str | None = Field(default=None, max_length=2000)
    instructions: str | None = Field(default=None, max_length=20000)
    folder_path: str | None = None
    archived: bool | None = None

    @field_validator("name", "description", "instructions")
    @classmethod
    def strip_fields(cls, value: str | None) -> str | None:
        return value.strip() if isinstance(value, str) else value


@router.get("")
def list_projects(request: Request, include_archived: bool = False):
    user_id = require_user(request)
    return {"projects": store.list_projects(user_id, include_archived=include_archived)}


@router.post("")
def create_project(payload: ProjectPayload, request: Request):
    user_id = require_user(request)
    folder = _validate_folder_path(payload.folder_path)
    return {"project": store.create_project(user_id, payload.name, payload.description, payload.instructions, folder_path=folder)}


@router.get("/for-conversation/{conversation_id}")
def project_for_conversation(conversation_id: int, request: Request):
    user_id = require_user(request)
    return {"project": store.get_project_for_conversation(conversation_id, user_id)}


@router.post("/{project_id}/chats")
def create_project_chat(project_id: int, request: Request):
    user_id = require_user(request)
    conversation = store.create_project_conversation(project_id, user_id)
    if not conversation:
        raise HTTPException(status_code=404, detail="Project not found.")
    return {"conversation": conversation}


@router.post("/{project_id}/knowledge")
async def upload_project_knowledge(project_id: int, request: Request, file: UploadFile = File(...)):
    user_id = require_user(request)
    if not store.get_project(project_id, user_id):
        raise HTTPException(status_code=404, detail="Project not found.")

    from ..files.routes import insert_attachment
    from ..files.service import AttachmentCandidate, AttachmentService, UnsupportedAttachmentError

    content = await file.read()
    try:
        prepared = AttachmentService().prepare(
            AttachmentCandidate(
                file_name=file.filename or "knowledge",
                mime_type=file.content_type or "application/octet-stream",
                content=content,
            )
        )
    except UnsupportedAttachmentError as error:
        raise HTTPException(status_code=415, detail=str(error)) from error
    except ValueError as error:
        raise HTTPException(status_code=400, detail=str(error)) from error

    attachment, _artifact = insert_attachment(user_id, prepared)
    if not store.link_attachment(project_id, user_id, attachment["id"]):
        raise HTTPException(status_code=500, detail="Could not link knowledge file to project.")
    return {"attachment": attachment}


@router.get("/{project_id}")
def get_project(project_id: int, request: Request):
    user_id = require_user(request)
    detail = store.get_project_detail(project_id, user_id)
    if not detail:
        raise HTTPException(status_code=404, detail="Project not found.")
    return {"project": detail}


@router.patch("/{project_id}")
def update_project(project_id: int, payload: ProjectUpdatePayload, request: Request):
    user_id = require_user(request)
    folder = _validate_folder_path(payload.folder_path) if payload.folder_path is not None else None
    project = store.update_project(
        project_id,
        user_id,
        name=payload.name,
        description=payload.description,
        instructions=payload.instructions,
        folder_path=folder,
        archived=payload.archived,
    )
    if not project:
        raise HTTPException(status_code=404, detail="Project not found.")
    return {"project": project}


@router.delete("/{project_id}")
def delete_project(project_id: int, request: Request):
    user_id = require_user(request)
    project = store.get_project(project_id, user_id)
    if not project:
        raise HTTPException(status_code=404, detail="Project not found.")

    removed = store.delete_project(project_id, user_id)

    folder_removed = False
    folder = project.get("folder_path")
    if folder and _is_managed_project_folder(user_id, Path(folder)):
        import shutil

        shutil.rmtree(folder, ignore_errors=True)
        folder_removed = True

    return {"removed": removed, "project_id": project_id, "workspace_removed": folder_removed}


def _managed_projects_root(user_id: int) -> Path:
    from ..workspace.routes import get_user_workspace

    return (Path(get_user_workspace(user_id)) / "projects").resolve()


def _is_managed_project_folder(user_id: int, folder: Path) -> bool:
    """True only for folders auto-created by ObsyGPT under <workspace>/projects/."""
    try:
        resolved = folder.resolve()
        root = _managed_projects_root(user_id)
        return resolved != root and root in resolved.parents
    except OSError:
        return False


@router.post("/{project_id}/workspace")
def enable_project_workspace(project_id: int, request: Request):
    """Creates (if needed) and assigns an isolated working folder under the user workspace."""
    user_id = require_user(request)
    project = store.get_project(project_id, user_id)
    if not project:
        raise HTTPException(status_code=404, detail="Project not found.")

    from ..workspace.routes import get_user_workspace

    base = Path(get_user_workspace(user_id)) / "projects"
    slug = _slugify(project["name"]) or f"proyecto-{project_id}"
    target = (base / f"{slug}-{project_id}").resolve()
    target.mkdir(parents=True, exist_ok=True)

    updated = store.set_project_folder(project_id, user_id, str(target))
    return {"project": store.get_project_detail(project_id, user_id), "workspace": str(target)}


@router.delete("/{project_id}/workspace")
def unlink_project_workspace(project_id: int, request: Request):
    """Detaches the project folder: files stay on disk, tools fall back to the global workspace."""
    user_id = require_user(request)
    project = store.get_project(project_id, user_id)
    if not project:
        raise HTTPException(status_code=404, detail="Project not found.")
    if not project.get("folder_path"):
        raise HTTPException(status_code=400, detail="Project has no linked folder.")
    store.set_project_folder(project_id, user_id, None)
    return {"project": store.get_project_detail(project_id, user_id), "removed": True}


@router.get("/{project_id}/files")
def list_project_files(project_id: int, request: Request, subpath: str = ""):
    """Lists the contents of the project working folder (jail-checked)."""
    user_id = require_user(request)
    project = store.get_project(project_id, user_id)
    if not project:
        raise HTTPException(status_code=404, detail="Project not found.")
    if not project.get("folder_path"):
        return {"folder": None, "subpath": "", "parent": None, "entries": []}

    root, target = _resolve_project_path(project, subpath)

    entries = []
    for child in sorted(target.iterdir(), key=lambda item: (not item.is_dir(), item.name.lower())):
        try:
            stat = child.stat()
        except OSError:
            continue
        entries.append({
            "name": child.name,
            "is_dir": child.is_dir(),
            "size": 0 if child.is_dir() else stat.st_size,
            "modified": _iso_timestamp(stat.st_mtime),
        })
        if len(entries) >= MAX_FILE_ENTRIES:
            break

    normalized_subpath = "" if target == root else str(target.relative_to(root)).replace("\\", "/")
    parent = str(Path(normalized_subpath).parent).replace("\\", "/") if normalized_subpath and str(Path(normalized_subpath).parent) != "." else None
    return {"folder": str(root), "subpath": normalized_subpath, "parent": parent, "entries": entries}


def _iso_timestamp(mtime: float) -> str:
    from datetime import datetime, timezone

    return datetime.fromtimestamp(mtime, tz=timezone.utc).isoformat()


def _resolve_project_path(project: dict, subpath: str) -> tuple[Path, Path]:
    """Resolves a relative subpath inside the project folder, refusing escapes and missing folders."""
    root = Path(project["folder_path"]).resolve()
    target = (root / subpath).resolve() if subpath.strip() else root
    if target != root and root not in target.parents:
        raise HTTPException(status_code=400, detail="Path escapes the project folder.")
    if not target.exists() or not target.is_dir():
        raise HTTPException(status_code=400, detail="Folder does not exist.")
    return root, target


@router.delete("/{project_id}/files")
def delete_project_file(project_id: int, request: Request, path: str = ""):
    """Deletes a file (or an empty folder) inside the project working folder."""
    user_id = require_user(request)
    project = store.get_project(project_id, user_id)
    if not project:
        raise HTTPException(status_code=404, detail="Project not found.")
    if not project.get("folder_path"):
        raise HTTPException(status_code=400, detail="Project has no linked folder.")

    root, folder = _resolve_project_path(project, "")
    target = (root / path).resolve() if path.strip() else root
    if target == root or root not in target.parents:
        raise HTTPException(status_code=400, detail="Path escapes the project folder.")
    if not target.exists():
        raise HTTPException(status_code=404, detail="File not found.")

    if target.is_dir():
        try:
            target.rmdir()
        except OSError as error:
            raise HTTPException(status_code=400, detail=f"Folder is not empty: {target.name}") from error
        return {"removed": True, "name": target.name, "kind": "folder"}

    target.unlink()
    return {"removed": True, "name": target.name, "kind": "file"}


@router.post("/{project_id}/conversations/{conversation_id}")
def add_conversation(project_id: int, conversation_id: int, request: Request):
    user_id = require_user(request)
    if not store.link_conversation(project_id, user_id, conversation_id):
        raise HTTPException(status_code=404, detail="Project or conversation not found.")
    return {"project_id": project_id, "conversation_id": conversation_id}


@router.delete("/{project_id}/conversations/{conversation_id}")
def remove_conversation(project_id: int, conversation_id: int, request: Request):
    user_id = require_user(request)
    if not store.unlink_conversation(project_id, user_id, conversation_id):
        raise HTTPException(status_code=404, detail="Project not found.")
    return {"project_id": project_id, "conversation_id": conversation_id, "removed": True}


@router.post("/{project_id}/attachments/{attachment_id}")
def add_attachment(project_id: int, attachment_id: int, request: Request):
    user_id = require_user(request)
    if not store.link_attachment(project_id, user_id, attachment_id):
        raise HTTPException(status_code=404, detail="Project or attachment not found.")
    return {"project_id": project_id, "attachment_id": attachment_id}


@router.delete("/{project_id}/attachments/{attachment_id}")
def remove_attachment(project_id: int, attachment_id: int, request: Request):
    user_id = require_user(request)
    if not store.unlink_attachment(project_id, user_id, attachment_id):
        raise HTTPException(status_code=404, detail="Project not found.")
    return {"project_id": project_id, "attachment_id": attachment_id, "removed": True}
