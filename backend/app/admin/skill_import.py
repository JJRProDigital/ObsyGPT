"""Import Anthropic-format .skill archives (ZIP with SKILL.md plus resources)."""

import re
import zipfile
from io import BytesIO

from fastapi import HTTPException, Request

from .. import audit as audit_module
from . import queries, skill_files

MAX_SKILL_ARCHIVE_BYTES = 2 * 1024 * 1024
MAX_SKILL_UNCOMPRESSED_BYTES = 5 * 1024 * 1024
MAX_SKILL_ENTRIES = 60
MAX_SKILL_ENTRY_BYTES = 512 * 1024

FRONTMATTER_KEY_PATTERN = re.compile(r"^([A-Za-z0-9_-]+):\s*(.*)$")
FOLDED_SCALAR_MARKERS = {">", ">-", "|", "|-"}


def parse_frontmatter(text: str) -> tuple[dict[str, str], str]:
    """Extracts flat YAML frontmatter keys (plain, quoted, or folded values)."""
    lines = text.splitlines()
    if not lines or lines[0].strip() != "---":
        raise HTTPException(status_code=400, detail="SKILL.md must start with a '---' frontmatter block.")
    metadata: dict[str, str] = {}
    index = 1
    while index < len(lines):
        line = lines[index]
        if line.strip() == "---":
            return metadata, "\n".join(lines[index + 1:]).strip()
        match = FRONTMATTER_KEY_PATTERN.match(line)
        if not match:
            index += 1
            continue
        key, value = match.group(1), match.group(2).strip()
        if value in FOLDED_SCALAR_MARKERS:
            collected: list[str] = []
            index += 1
            while index < len(lines) and (lines[index].startswith(" ") or lines[index].startswith("\t")):
                collected.append(lines[index].strip())
                index += 1
            separator = " " if value.startswith(">") else "\n"
            metadata[key] = separator.join(collected).strip()
            continue
        if len(value) >= 2 and value[0] == value[-1] and value[0] in {"'", '"'}:
            value = value[1:-1]
        metadata[key] = value
        index += 1
    raise HTTPException(status_code=400, detail="SKILL.md frontmatter is not closed with a second '---' line.")


def _safe_archive_parts(filename: str) -> tuple[str, ...] | None:
    """Normalized path parts for an archive entry, or None when the path is unsafe."""
    if filename.startswith("/") or filename.startswith("\\"):
        return None
    parts = tuple(part for part in filename.replace("\\", "/").split("/") if part not in ("", "."))
    if not parts or ".." in parts:
        return None
    return parts


def parse_skill_zip(content: bytes) -> dict:
    if len(content) > MAX_SKILL_ARCHIVE_BYTES:
        raise HTTPException(status_code=413, detail=f".skill archive exceeds the {MAX_SKILL_ARCHIVE_BYTES // (1024 * 1024)} MB limit.")
    try:
        archive = zipfile.ZipFile(BytesIO(content))
    except zipfile.BadZipFile as error:
        raise HTTPException(status_code=400, detail="File is not a valid .skill ZIP archive.") from error

    entries = [entry for entry in archive.infolist() if not entry.is_dir()]
    if not entries:
        raise HTTPException(status_code=400, detail=".skill archive is empty.")
    if len(entries) > MAX_SKILL_ENTRIES:
        raise HTTPException(status_code=400, detail=f".skill archive has too many entries (max {MAX_SKILL_ENTRIES}).")
    if sum(entry.file_size for entry in entries) > MAX_SKILL_UNCOMPRESSED_BYTES:
        raise HTTPException(status_code=400, detail=f".skill archive exceeds the {MAX_SKILL_UNCOMPRESSED_BYTES // (1024 * 1024)} MB uncompressed limit.")

    files: dict[str, bytes] = {}
    skill_md_path: str | None = None
    for entry in entries:
        parts = _safe_archive_parts(entry.filename)
        if parts is None:
            raise HTTPException(status_code=400, detail=f"Unsafe path inside .skill archive: {entry.filename}")
        if entry.file_size > MAX_SKILL_ENTRY_BYTES:
            raise HTTPException(status_code=400, detail=f"File inside .skill archive is too large: {entry.filename}")
        path = "/".join(parts)
        if path.lower().endswith("/skill.md") or path.lower() == "skill.md":
            if skill_md_path is not None:
                raise HTTPException(status_code=400, detail=".skill archive contains more than one SKILL.md.")
            skill_md_path = path
        files[path] = archive.read(entry)

    if skill_md_path is None:
        raise HTTPException(status_code=400, detail=".skill archive does not contain a SKILL.md.")

    try:
        skill_md_text = files.pop(skill_md_path).decode("utf-8")
    except UnicodeDecodeError as error:
        raise HTTPException(status_code=400, detail="SKILL.md is not valid UTF-8 text.") from error

    metadata, body = parse_frontmatter(skill_md_text)
    if not body:
        raise HTTPException(status_code=400, detail="SKILL.md has no instructions below its frontmatter.")

    name = str(metadata.get("name", "")).strip()
    if not name and "/" in skill_md_path:
        name = skill_md_path.split("/")[0].strip()
    try:
        skill_files.ensure_safe_skill_name(name)
    except HTTPException as error:
        raise HTTPException(status_code=400, detail=f"Invalid skill name in SKILL.md frontmatter: {name!r}") from error

    prefix = skill_md_path[: -len("SKILL.md")]
    resource_files: dict[str, bytes] = {}
    for path, data in files.items():
        relative = path[len(prefix):] if prefix and path.startswith(prefix) else path
        resource_files[relative] = data

    return {
        "name": name,
        "description": str(metadata.get("description", "")).strip(),
        "argument_hint": "",
        "triggers": ["user"],
        "body": body,
        "resources": "\n".join(f"- {path}" for path in sorted(resource_files)),
        "resource_files": resource_files,
    }


def write_resource_files(name: str, resource_files: dict[str, bytes]) -> None:
    """Writes imported resource contents over the stubs created by write_skill_files."""
    skill_files.ensure_safe_skill_name(name)
    skill_dir = skill_files.SKILLS_ROOT / name
    skill_dir.mkdir(parents=True, exist_ok=True)
    for relative_path, data in resource_files.items():
        target = skill_dir / relative_path
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(data)


def import_skill_from_archive(content: bytes, filename: str, request: Request) -> dict:
    parsed = parse_skill_zip(content)
    existing = queries.fetch_one("SELECT id FROM skills WHERE name = %s;", (parsed["name"],))
    if existing:
        raise HTTPException(status_code=409, detail=f"A skill with this name already exists: {parsed['name']}")
    skill = queries.execute_returning(
        """
        INSERT INTO skills (name, description, argument_hint, triggers, body, resources, enabled)
        VALUES (%s, %s, %s, %s, %s, %s, true)
        RETURNING id, name, description, argument_hint, triggers, body, resources, enabled;
        """,
        (parsed["name"], parsed["description"], parsed["argument_hint"], parsed["triggers"], parsed["body"], parsed["resources"]),
    )
    skill_files.write_skill_files(skill)
    write_resource_files(skill["name"], parsed["resource_files"])
    audit_module.AuditStore().add_log(
        actor_user_id=int(request.session.get("user_id")),
        action="skill.imported",
        target_type="skill",
        target_id=skill["id"],
        metadata={"name": skill["name"], "resources": len(parsed["resource_files"]), "source_file": filename},
    )
    return {"skill": skill_files.with_skill_md(skill)}
