"""Plugin catalog scanning, git marketplaces, and install/uninstall."""

import json
import re
import subprocess
from pathlib import Path

from ..db import connect
from .manifest import load_manifest

REPO_ROOT = Path(__file__).resolve().parents[3]
PLUGINS_ROOT = REPO_ROOT / "plugins"
MARKETPLACES_ROOT = PLUGINS_ROOT / "marketplaces"
MAX_MARKETPLACES = 25
GIT_TIMEOUT_SECONDS = 90


def namespaced_skill_name(plugin_slug: str, skill_name: str) -> str:
    return f"{plugin_slug}-{skill_name}"


def _installed_plugin_dir(plugin: dict) -> Path | None:
    """Folder that holds plugin.json for an installed plugin, or None when unavailable."""
    slug = plugin.get("slug", "")
    source = plugin.get("source")
    if source == "local":
        return PLUGINS_ROOT / slug
    if source == "marketplace" and plugin.get("marketplace_name"):
        return MARKETPLACES_ROOT / plugin["marketplace_name"] / slug
    return None


def _current_manifest(plugin: dict, base: Path) -> dict:
    """On-disk manifest (so plugin updates apply) with the installed manifest as fallback."""
    try:
        return load_manifest(base / "plugin.json")
    except (ValueError, OSError):
        return plugin.get("manifest") or {}


def list_project_templates() -> list[dict]:
    """Project templates shipped by installed plugins whose folder is still available."""
    results = []
    for plugin in list_installed().values():
        base = _installed_plugin_dir(plugin)
        if base is None or not base.is_dir():
            continue
        manifest = _current_manifest(plugin, base)
        for template in manifest.get("templates", []) or []:
            source = (base / template["path"]).resolve()
            if base.resolve() not in source.parents or not source.is_dir():
                continue
            results.append(
                {
                    "slug": plugin["slug"],
                    "plugin_name": plugin["name"],
                    "name": template["name"],
                    "title": template["title"],
                    "description": template["description"],
                }
            )
    return results


def get_project_template(slug: str, name: str) -> dict:
    """Resolves one installed template, its source folder, and its instructions file."""
    plugin = list_installed().get(slug)
    if not plugin:
        raise ValueError(f"Plugin is not installed: {slug}")
    base = _installed_plugin_dir(plugin)
    if base is None or not base.is_dir():
        raise ValueError(f"Plugin files are not available: {slug}")

    manifest = _current_manifest(plugin, base)
    template = next(
        (item for item in manifest.get("templates", []) or [] if item.get("name") == name),
        None,
    )
    if not template:
        raise ValueError(f"Template not found: {slug}/{name}")

    base_resolved = base.resolve()
    source = (base / template["path"]).resolve()
    if base_resolved not in source.parents or not source.is_dir():
        raise ValueError(f"Template folder is missing: {source}")

    instructions = ""
    if template.get("instructions"):
        instructions_path = (source / template["instructions"]).resolve()
        if source in instructions_path.parents and instructions_path.is_file():
            instructions = instructions_path.read_text(encoding="utf-8")[:20000]

    return {
        "slug": slug,
        "name": name,
        "title": template["title"],
        "description": template["description"],
        "source_dir": source,
        "instructions": instructions,
    }


def _local_plugin_dirs() -> list[Path]:
    if not PLUGINS_ROOT.is_dir():
        return []
    return sorted(entry for entry in PLUGINS_ROOT.iterdir() if entry.is_dir() and (entry / "plugin.json").is_file())


def _marketplace_plugin_dirs(marketplace_name: str) -> list[Path]:
    base = MARKETPLACES_ROOT / marketplace_name
    if not base.is_dir():
        return []
    return sorted(entry for entry in base.iterdir() if entry.is_dir() and (entry / "plugin.json").is_file())


def scan_catalog() -> list[dict]:
    entries: dict[str, dict] = {}
    for plugin_dir in _local_plugin_dirs():
        try:
            manifest = load_manifest(plugin_dir / "plugin.json")
        except ValueError:
            continue
        entries[manifest["slug"]] = {"manifest": manifest, "source": "local", "marketplace_name": None}
    for marketplace in list_marketplaces():
        for plugin_dir in _marketplace_plugin_dirs(marketplace["name"]):
            try:
                manifest = load_manifest(plugin_dir / "plugin.json")
            except ValueError:
                continue
            entries.setdefault(manifest["slug"], {"manifest": manifest, "source": "marketplace", "marketplace_name": marketplace["name"]})
    return [dict(entry, manifest_path=_manifest_path(entry)) for entry in entries.values()]


def _manifest_path(entry: dict) -> str:
    if entry["source"] == "local":
        return str(PLUGINS_ROOT / entry["manifest"]["slug"] / "plugin.json")
    return str(MARKETPLACES_ROOT / entry["marketplace_name"] / entry["manifest"]["slug"] / "plugin.json")


def find_catalog_entry(source: str, slug: str, marketplace_name: str | None = None) -> dict:
    for entry in scan_catalog():
        if entry["manifest"]["slug"] != slug:
            continue
        if entry["source"] != source:
            continue
        if source == "marketplace" and entry["marketplace_name"] != marketplace_name:
            continue
        return entry
    raise ValueError(f"Plugin not found in catalog: {source}/{slug}")


def list_installed() -> dict[str, dict]:
    with connect() as connection:
        with connection.cursor() as cursor:
            cursor.execute("SELECT slug, name, version, description, source, marketplace_name, manifest, installed_refs FROM plugins;")
            columns = [column.name for column in cursor.description]
            return {row[columns.index("slug")]: dict(zip(columns, row)) for row in cursor.fetchall()}


def list_marketplaces() -> list[dict]:
    with connect() as connection:
        with connection.cursor() as cursor:
            cursor.execute("SELECT name, url FROM plugin_marketplaces ORDER BY name;")
            columns = [column.name for column in cursor.description]
            return [dict(zip(columns, row)) for row in cursor.fetchall()]


def _marketplace_slug(url: str) -> str:
    path = url.rstrip("/").split("/")
    tail = "-".join(part for part in path[-2:] if part) or "marketplace"
    return re.sub(r"[^a-z0-9-]+", "-", tail.lower()).strip("-")[:100]


def add_marketplace(url: str) -> dict:
    from ..mcps.gateway import validate_url

    cleaned = validate_url(url)
    existing = list_marketplaces()
    if any(marketplace["url"] == cleaned for marketplace in existing):
        raise ValueError("Marketplace URL is already registered.")
    if len(existing) >= MAX_MARKETPLACES:
        raise ValueError(f"Marketplace limit reached ({MAX_MARKETPLACES}).")
    name = _marketplace_slug(cleaned)
    if any(marketplace["name"] == name for marketplace in existing):
        name = f"{name}-{len(existing) + 1}"
    target = MARKETPLACES_ROOT / name
    MARKETPLACES_ROOT.mkdir(parents=True, exist_ok=True)
    result = subprocess.run(
        ["git", "clone", "--depth", "1", cleaned, str(target)],
        capture_output=True,
        text=True,
        timeout=GIT_TIMEOUT_SECONDS,
        shell=False,
    )
    if result.returncode != 0:
        raise RuntimeError(f"git clone failed: {result.stderr.strip()[:300]}")
    with connect() as connection:
        with connection.cursor() as cursor:
            cursor.execute(
                "INSERT INTO plugin_marketplaces (name, url) VALUES (%s, %s) ON CONFLICT (name) DO NOTHING;",
                (name, cleaned),
            )
    return {"name": name, "url": cleaned}


def refresh_marketplace(name: str) -> dict:
    target = MARKETPLACES_ROOT / name
    if not target.is_dir():
        raise ValueError(f"Marketplace directory not found: {name}")
    result = subprocess.run(
        ["git", "-C", str(target), "pull", "--ff-only"],
        capture_output=True,
        text=True,
        timeout=GIT_TIMEOUT_SECONDS,
        shell=False,
    )
    if result.returncode != 0:
        raise RuntimeError(f"git pull failed: {result.stderr.strip()[:300]}")
    return {"name": name, "updated": True}


def remove_marketplace(name: str) -> bool:
    import shutil

    with connect() as connection:
        with connection.cursor() as cursor:
            cursor.execute("DELETE FROM plugin_marketplaces WHERE name = %s;", (name,))
            removed = cursor.rowcount > 0
    target = MARKETPLACES_ROOT / name
    if target.is_dir():
        shutil.rmtree(target, ignore_errors=True)
    return removed


def install_plugin(entry: dict) -> dict:
    from ..admin import skill_files
    from ..mcps.gateway import McpGateway, McpServerConfig

    manifest = entry["manifest"]
    slug = manifest["slug"]
    installed_refs = {"skill_ids": [], "mcp_ids": [], "agent_ids": [], "skipped": []}

    with connect() as connection:
        with connection.cursor() as cursor:
            cursor.execute("SELECT slug FROM plugins WHERE slug = %s;", (slug,))
            if cursor.fetchone():
                raise ValueError(f"Plugin is already installed: {slug}")

            for skill in manifest["skills"]:
                full_name = namespaced_skill_name(slug, skill["name"])
                cursor.execute("SELECT id FROM skills WHERE name = %s;", (full_name,))
                existing = cursor.fetchone()
                if existing:
                    installed_refs["skipped"].append(f"skill:{full_name}")
                    continue
                cursor.execute(
                    """
                    INSERT INTO skills (name, description, argument_hint, triggers, body, resources, enabled)
                    VALUES (%s, %s, %s, %s, %s, %s, true)
                    RETURNING id;
                    """,
                    (full_name, skill["description"], skill["argument_hint"], skill["triggers"], skill["body"], skill["resources"]),
                )
                skill_id = cursor.fetchone()[0]
                installed_refs["skill_ids"].append(skill_id)
                skill_files.write_skill_files({"name": full_name, "description": skill["description"], "argument_hint": skill["argument_hint"], "triggers": skill["triggers"], "body": skill["body"], "resources": skill["resources"]})

            for mcp in manifest["mcps"]:
                McpGateway().validate(
                    McpServerConfig(mcp["name"], mcp["description"], mcp["connection_type"], mcp.get("command"), mcp.get("url"), mcp["enabled"])
                )
                cursor.execute(
                    """
                    INSERT INTO mcp_servers (name, description, connection_type, command, url, enabled)
                    VALUES (%s, %s, %s, %s, %s, %s)
                    ON CONFLICT (name) DO NOTHING
                    RETURNING id;
                    """,
                    (mcp["name"], mcp["description"], mcp["connection_type"], mcp.get("command"), mcp.get("url"), mcp["enabled"]),
                )
                row = cursor.fetchone()
                if row:
                    installed_refs["mcp_ids"].append(row[0])
                else:
                    installed_refs["skipped"].append(f"mcp:{mcp['name']}")

            for agent in manifest["agents"]:
                cursor.execute(
                    """
                    INSERT INTO agents (name, description, system_prompt, internet_enabled, multimodal_enabled, agentic_mode, enabled)
                    VALUES (%s, %s, %s, false, false, true, %s)
                    ON CONFLICT (name) DO NOTHING
                    RETURNING id;
                    """,
                    (agent["name"], agent["description"], agent["system_prompt"], agent["enabled"]),
                )
                row = cursor.fetchone()
                if row:
                    agent_id = row[0]
                    installed_refs["agent_ids"].append(agent_id)
                    for skill_id in installed_refs["skill_ids"]:
                        cursor.execute(
                            "INSERT INTO agent_skills (agent_id, skill_id) VALUES (%s, %s) ON CONFLICT DO NOTHING;",
                            (agent_id, skill_id),
                        )
                else:
                    installed_refs["skipped"].append(f"agent:{agent['name']}")

            cursor.execute(
                """
                INSERT INTO plugins (slug, name, version, description, source, marketplace_name, manifest, installed_refs)
                VALUES (%s, %s, %s, %s, %s, %s, %s::json, %s::json);
                """,
                (
                    slug,
                    manifest["name"],
                    manifest["version"],
                    manifest["description"],
                    entry["source"],
                    entry.get("marketplace_name"),
                    json.dumps(manifest),
                    json.dumps(installed_refs),
                ),
            )

    return {"slug": slug, "refs": installed_refs}


def uninstall_plugin(slug: str) -> dict:
    from ..admin import skill_files

    with connect() as connection:
        with connection.cursor() as cursor:
            cursor.execute("SELECT installed_refs FROM plugins WHERE slug = %s;", (slug,))
            row = cursor.fetchone()
            if not row:
                raise ValueError(f"Plugin is not installed: {slug}")
            refs = row[0] or {}
            removed = {"skills": 0, "mcps": 0, "agents": 0}
            for skill_id in refs.get("skill_ids", []):
                cursor.execute("DELETE FROM skills WHERE id = %s RETURNING name;", (skill_id,))
                deleted = cursor.fetchone()
                if deleted:
                    skill_files.delete_skill_files(deleted[0])
                    removed["skills"] += 1
            for mcp_id in refs.get("mcp_ids", []):
                cursor.execute("DELETE FROM mcp_servers WHERE id = %s;", (mcp_id,))
                removed["mcps"] += 1
            for agent_id in refs.get("agent_ids", []):
                cursor.execute("DELETE FROM agents WHERE id = %s;", (agent_id,))
                removed["agents"] += 1
            cursor.execute("DELETE FROM plugins WHERE slug = %s;", (slug,))
    return {"slug": slug, "removed": removed}
