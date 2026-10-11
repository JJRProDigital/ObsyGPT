"""Plugin manifest loading and validation."""

import json
import re
from pathlib import Path

SLUG_PATTERN = re.compile(r"^[a-z0-9][a-z0-9-]{1,59}$")
SKILL_NAME_PATTERN = re.compile(r"^[a-zA-Z0-9_-]+$")
MAX_MANIFEST_BYTES = 512 * 1024


def load_manifest(path: Path) -> dict:
    if not path.is_file():
        raise ValueError(f"Plugin manifest not found: {path}")
    if path.stat().st_size > MAX_MANIFEST_BYTES:
        raise ValueError("Plugin manifest is too large.")
    try:
        manifest = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as error:
        raise ValueError(f"Invalid plugin manifest JSON: {error}") from error
    return validate_manifest(manifest)


def validate_manifest(manifest: dict) -> dict:
    if not isinstance(manifest, dict):
        raise ValueError("Plugin manifest must be a JSON object.")
    slug = str(manifest.get("slug", "")).strip()
    if not SLUG_PATTERN.fullmatch(slug):
        raise ValueError("Plugin slug must be lowercase letters, numbers, and hyphens (2-60 chars).")
    name = str(manifest.get("name", "")).strip()
    if not name:
        raise ValueError("Plugin name is required.")
    version = str(manifest.get("version", "1.0.0")).strip() or "1.0.0"

    skills = []
    for index, skill in enumerate(manifest.get("skills", []) or []):
        if not isinstance(skill, dict):
            raise ValueError(f"skills[{index}] must be an object.")
        skill_name = str(skill.get("name", "")).strip()
        if not SKILL_NAME_PATTERN.fullmatch(skill_name):
            raise ValueError(f"skills[{index}].name may only contain letters, numbers, underscores, and hyphens.")
        body = str(skill.get("body", "")).strip()
        if not body:
            raise ValueError(f"skills[{index}].body is required.")
        triggers = [trigger for trigger in (skill.get("triggers") or ["user"]) if trigger in {"user", "model"}] or ["user"]
        skills.append(
            {
                "name": skill_name,
                "description": str(skill.get("description", "")).strip(),
                "argument_hint": str(skill.get("argument_hint", "")).strip(),
                "triggers": triggers,
                "body": body,
                "resources": str(skill.get("resources", "")).strip(),
            }
        )

    mcps = []
    for index, mcp in enumerate(manifest.get("mcps", []) or []):
        if not isinstance(mcp, dict):
            raise ValueError(f"mcps[{index}] must be an object.")
        connection_type = mcp.get("connection_type")
        if connection_type not in {"command", "url"}:
            raise ValueError(f"mcps[{index}].connection_type must be 'command' or 'url'.")
        mcps.append(
            {
                "name": str(mcp.get("name", "")).strip(),
                "description": str(mcp.get("description", "")).strip(),
                "connection_type": connection_type,
                "command": mcp.get("command"),
                "url": mcp.get("url"),
                "enabled": bool(mcp.get("enabled", False)),
            }
        )

    agents = []
    for index, agent in enumerate(manifest.get("agents", []) or []):
        if not isinstance(agent, dict):
            raise ValueError(f"agents[{index}] must be an object.")
        system_prompt = str(agent.get("system_prompt", "")).strip()
        if not system_prompt:
            raise ValueError(f"agents[{index}].system_prompt is required.")
        agents.append(
            {
                "name": str(agent.get("name", "")).strip(),
                "description": str(agent.get("description", "")).strip(),
                "system_prompt": system_prompt,
                "enabled": bool(agent.get("enabled", True)),
            }
        )

    connectors = [str(connector).strip() for connector in (manifest.get("connectors") or []) if str(connector).strip()]

    return {
        "slug": slug,
        "name": name,
        "version": version,
        "description": str(manifest.get("description", "")).strip(),
        "skills": skills,
        "mcps": mcps,
        "agents": agents,
        "connectors": connectors,
    }
