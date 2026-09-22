"""Admin skill management endpoints."""

from typing import Literal

from fastapi import APIRouter, HTTPException, Request
from pydantic import BaseModel, Field, field_validator

from .. import audit as audit_module
from ..auth import routes as auth
from ..skills.runtime import SkillRegistry
from . import queries, skill_files
from .queries import ensure_positive_id


router = APIRouter()


class SkillPayload(BaseModel):
    name: str = Field(min_length=1, max_length=100)
    description: str = ""
    argument_hint: str = ""
    triggers: list[Literal["user", "model"]] = Field(default_factory=lambda: ["user"])
    body: str = "# Instrucciones principales\n1. Describe el flujo de trabajo de la skill.\n\n## Restricciones\n* No ejecutes acciones destructivas sin confirmacion explicita."
    resources: str = ""
    enabled: bool = True

    @field_validator("name")
    @classmethod
    def strip_name(cls, value: str) -> str:
        stripped = value.strip()
        if not stripped:
            raise ValueError("Skill name is required.")
        return stripped

    @field_validator("description", "argument_hint", "body", "resources")
    @classmethod
    def strip_skill_text(cls, value: str) -> str:
        return value.strip()

    @field_validator("triggers")
    @classmethod
    def validate_triggers(cls, value: list[str]) -> list[str]:
        triggers = list(dict.fromkeys(value))
        if not triggers:
            raise ValueError("At least one trigger is required.")
        return triggers


class SkillRunPayload(BaseModel):
    skill_name: Literal["read_url", "web_search"]
    payload: dict


class SkillGeneratePayload(BaseModel):
    prompt: str = Field(min_length=1, max_length=2000)

    @field_validator("prompt")
    @classmethod
    def strip_prompt(cls, value: str) -> str:
        stripped = value.strip()
        if not stripped:
            raise ValueError("Skill generator prompt is required.")
        return stripped


@router.get("/skills")
def list_skills(request: Request):
    auth.require_user(request)
    skills = queries.fetch_all("SELECT id, name, description, argument_hint, triggers, body, resources, enabled FROM skills ORDER BY name;")
    return {"skills": [skill_files.with_skill_md(skill) for skill in skills]}


@router.post("/skills")
def create_skill(payload: SkillPayload, request: Request):
    auth.require_admin(request)
    skill_files.ensure_safe_skill_name(payload.name)
    skill = queries.execute_returning(
        """
        INSERT INTO skills (name, description, argument_hint, triggers, body, resources, enabled)
        VALUES (%s, %s, %s, %s, %s, %s, %s)
        RETURNING id, name, description, argument_hint, triggers, body, resources, enabled;
        """,
        (payload.name, payload.description, payload.argument_hint, payload.triggers, payload.body, payload.resources, payload.enabled),
    )
    skill_files.write_skill_files(skill)
    audit_module.AuditStore().add_log(
        actor_user_id=int(request.session.get("user_id")),
        action="skill.created",
        target_type="skill",
        target_id=skill["id"],
        metadata={"name": skill["name"], "enabled": skill["enabled"]},
    )
    return {"skill": skill_files.with_skill_md(skill)}


@router.patch("/skills/{skill_id}")
def update_skill(skill_id: int, payload: SkillPayload, request: Request):
    auth.require_admin(request)
    skill_id = ensure_positive_id(skill_id, "skill_id")
    skill_files.ensure_safe_skill_name(payload.name)
    existing_skill = queries.fetch_one("SELECT name FROM skills WHERE id = %s;", (skill_id,))
    if not existing_skill:
        raise HTTPException(status_code=404, detail="Skill not found.")
    skill = queries.execute_returning(
        """
        UPDATE skills
        SET name = %s, description = %s, argument_hint = %s, triggers = %s, body = %s, resources = %s, enabled = %s
        WHERE id = %s
        RETURNING id, name, description, argument_hint, triggers, body, resources, enabled;
        """,
        (payload.name, payload.description, payload.argument_hint, payload.triggers, payload.body, payload.resources, payload.enabled, skill_id),
    )
    skill_files.write_skill_files(skill, previous_name=existing_skill["name"])
    audit_module.AuditStore().add_log(
        actor_user_id=int(request.session.get("user_id")),
        action="skill.updated",
        target_type="skill",
        target_id=skill["id"],
        metadata={"name": skill["name"], "enabled": skill["enabled"]},
    )
    return {"skill": skill_files.with_skill_md(skill)}


@router.delete("/skills/{skill_id}")
def delete_skill(skill_id: int, request: Request):
    auth.require_admin(request)
    skill_id = ensure_positive_id(skill_id, "skill_id")
    skill = queries.execute_returning(
        "DELETE FROM skills WHERE id = %s RETURNING id, name;",
        (skill_id,),
    )
    if not skill:
        raise HTTPException(status_code=404, detail="Skill not found.")
    skill_files.delete_skill_files(skill["name"])
    audit_module.AuditStore().add_log(
        actor_user_id=int(request.session.get("user_id")),
        action="skill.deleted",
        target_type="skill",
        target_id=skill["id"],
        metadata={"name": skill["name"]},
    )
    return {"id": skill["id"], "deleted": True}


@router.post("/skills/generate")
def generate_skill(payload: SkillGeneratePayload, request: Request):
    auth.require_admin(request)
    draft = skill_files.build_skill_draft(payload.prompt)
    audit_module.AuditStore().add_log(
        actor_user_id=int(request.session.get("user_id")),
        action="skill.generated",
        target_type="skill",
        target_id=None,
        metadata={"name": draft["name"]},
    )
    return {"draft": draft}


@router.post("/skills/run")
def run_skill(payload: SkillRunPayload, request: Request):
    auth.require_user(request)
    result = SkillRegistry().run(payload.skill_name, payload.payload)
    return {"skill_name": payload.skill_name, "result": result}
