"""Agent Skills filesystem bridge: SKILL.md rendering and skill folders.

Domain modules call these through the module (``skill_files.write_skill_files(...)``)
so tests can monkeypatch ``app.admin.skill_files.*`` once for every consumer.
"""

from pathlib import Path
import re
import shutil

from fastapi import HTTPException


SKILLS_ROOT = Path(__file__).resolve().parents[3] / "agents" / "skills"
SKILL_NAME_PATTERN = re.compile(r"^[a-zA-Z0-9_-]+$")


def build_skill_draft(prompt: str) -> dict:
    words = re.findall(r"[a-zA-Z0-9]+", prompt.lower())[:6]
    name = "_".join(words) if words else "generated_skill"
    if not name.endswith("_skill"):
        name = f"{name}_skill"
    description = prompt if len(prompt) <= 180 else f"{prompt[:177]}..."
    return {
        "name": name[:100],
        "description": description,
        "argument_hint": "Describe entradas y objetivo esperado.",
        "triggers": ["user"],
        "body": (
            "# Instrucciones principales\n"
            "1. Identifica la tarea del usuario y confirma que encaja con esta skill.\n"
            "2. Reune entradas necesarias antes de actuar.\n"
            "3. Devuelve una respuesta estructurada con resultado, evidencias y siguientes pasos.\n\n"
            "## Restricciones\n"
            "* No ejecutes codigo, comandos destructivos ni llamadas externas sin autorizacion explicita.\n"
            "* No inventes datos; marca cualquier incertidumbre."
        ),
        "resources": "scripts/, templates/ y examples/ son opcionales; anade solo recursos revisados.",
        "instructions": (
            "Define the skill purpose, inputs, output shape, safety limits, and verification steps. "
            "Keep execution explicit; do not run arbitrary generated code."
        ),
        "checklist": [
            "Name is unique and action-oriented.",
            "Description explains when an agent should use it.",
            "Inputs and outputs are clear enough to test.",
            "No secrets, destructive shell commands, or unrestricted network access.",
        ],
    }


def render_skill_md(skill: dict) -> str:
    triggers = ", ".join(f'"{trigger}"' for trigger in skill.get("triggers", ["user"]))
    argument_hint = skill.get("argument_hint") or ""
    lines = [
        "---",
        f"name: {skill['name']}",
        f"description: {skill.get('description') or ''}",
    ]
    if argument_hint:
        lines.append(f"argument-hint: {argument_hint}")
    lines.extend([f"triggers: [{triggers}]", "---", "", skill.get("body") or ""])
    resources = skill.get("resources") or ""
    if resources:
        lines.extend(["", "## Recursos opcionales", resources])
    return "\n".join(lines).strip() + "\n"


def with_skill_md(skill: dict) -> dict:
    skill["skill_md"] = render_skill_md(skill)
    return skill


def ensure_safe_skill_name(name: str) -> None:
    if not SKILL_NAME_PATTERN.fullmatch(name):
        raise HTTPException(status_code=400, detail="Skill name may only contain letters, numbers, underscores, and hyphens.")


def resource_paths(resources: str) -> list[str]:
    paths: list[str] = []
    for line in resources.splitlines():
        resource = line.strip().lstrip("- ").strip()
        if not resource or resource.startswith("#"):
            continue
        normalized = resource.replace("\\", "/")
        if normalized.startswith("/") or ".." in Path(normalized).parts:
            raise HTTPException(status_code=400, detail=f"Unsafe skill resource path: {resource}")
        paths.append(normalized)
    return paths


def write_skill_files(skill: dict, previous_name: str | None = None) -> None:
    ensure_safe_skill_name(skill["name"])
    SKILLS_ROOT.mkdir(parents=True, exist_ok=True)
    skill_dir = SKILLS_ROOT / skill["name"]
    if previous_name and previous_name != skill["name"]:
        ensure_safe_skill_name(previous_name)
        previous_dir = SKILLS_ROOT / previous_name
        if previous_dir.exists() and not skill_dir.exists():
            previous_dir.rename(skill_dir)
    skill_dir.mkdir(parents=True, exist_ok=True)
    (skill_dir / "SKILL.md").write_text(render_skill_md(skill), encoding="utf-8")
    for resource in resource_paths(skill.get("resources") or ""):
        resource_path = skill_dir / resource
        resource_path.parent.mkdir(parents=True, exist_ok=True)
        if not resource_path.exists():
            resource_path.write_text(f"# {resource_path.stem.replace('-', ' ').replace('_', ' ').title()}\n", encoding="utf-8")


def delete_skill_files(name: str) -> None:
    ensure_safe_skill_name(name)
    skill_dir = SKILLS_ROOT / name
    if skill_dir.exists():
        shutil.rmtree(skill_dir)
