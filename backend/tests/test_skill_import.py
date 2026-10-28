import zipfile
from io import BytesIO

import pytest
from fastapi import HTTPException

from app.admin import skill_import

SKILL_MD = """---
name: demo-skill
description: Demo skill for tests.
---

# Demo Skill

Instrucciones de prueba.
"""


class FakeRequest:
    session = {"user_id": 1, "role": "admin"}


def build_archive(entries: dict[str, str]) -> bytes:
    buffer = BytesIO()
    with zipfile.ZipFile(buffer, "w") as archive:
        for name, content in entries.items():
            archive.writestr(name, content)
    return buffer.getvalue()


def test_parse_frontmatter_reads_plain_quoted_and_folded_values():
    text = (
        "---\n"
        'name: "quoted-skill"\n'
        "description: >-\n"
        "  first part\n"
        "  second part\n"
        "extra: plain\n"
        "---\n"
        "# Body\n"
    )

    metadata, body = skill_import.parse_frontmatter(text)

    assert metadata["name"] == "quoted-skill"
    assert metadata["description"] == "first part second part"
    assert metadata["extra"] == "plain"
    assert body == "# Body"


def test_parse_frontmatter_requires_closing_marker():
    with pytest.raises(HTTPException) as error:
        skill_import.parse_frontmatter("---\nname: x\n")

    assert error.value.status_code == 400


def test_parse_skill_zip_extracts_skill_and_resources():
    content = build_archive(
        {
            "demo-skill/SKILL.md": SKILL_MD,
            "demo-skill/references/pacing.md": "60s reel",
            "demo-skill/scripts/run.sh": "echo hi",
        }
    )

    parsed = skill_import.parse_skill_zip(content)

    assert parsed["name"] == "demo-skill"
    assert parsed["description"] == "Demo skill for tests."
    assert parsed["body"].startswith("# Demo Skill")
    assert parsed["triggers"] == ["user"]
    assert parsed["resources"] == "- references/pacing.md\n- scripts/run.sh"
    assert parsed["resource_files"] == {"references/pacing.md": b"60s reel", "scripts/run.sh": b"echo hi"}


def test_parse_skill_zip_falls_back_to_folder_name():
    skill_md = "---\ndescription: Sin name.\n---\n\nBody."

    parsed = skill_import.parse_skill_zip(build_archive({"folder-skill/SKILL.md": skill_md}))

    assert parsed["name"] == "folder-skill"


def test_parse_skill_zip_rejects_invalid_name():
    skill_md = "---\nname: 'bad name!'\n---\n\nBody."

    with pytest.raises(HTTPException) as error:
        skill_import.parse_skill_zip(build_archive({"x/SKILL.md": skill_md}))

    assert error.value.status_code == 400


def test_parse_skill_zip_rejects_missing_skill_md():
    with pytest.raises(HTTPException) as error:
        skill_import.parse_skill_zip(build_archive({"folder/notes.txt": "x"}))

    assert error.value.status_code == 400


def test_parse_skill_zip_rejects_multiple_skill_md():
    with pytest.raises(HTTPException) as error:
        skill_import.parse_skill_zip(build_archive({"a/SKILL.md": SKILL_MD, "b/SKILL.md": SKILL_MD}))

    assert error.value.status_code == 400


def test_parse_skill_zip_rejects_traversal_paths():
    with pytest.raises(HTTPException) as error:
        skill_import.parse_skill_zip(build_archive({"demo/SKILL.md": SKILL_MD, "../evil.txt": "x"}))

    assert error.value.status_code == 400


def test_parse_skill_zip_rejects_non_zip():
    with pytest.raises(HTTPException) as error:
        skill_import.parse_skill_zip(b"not a zip at all")

    assert error.value.status_code == 400


def test_parse_skill_zip_rejects_oversized_archive():
    with pytest.raises(HTTPException) as error:
        skill_import.parse_skill_zip(b"\0" * (skill_import.MAX_SKILL_ARCHIVE_BYTES + 1))

    assert error.value.status_code == 413


def test_write_resource_files_writes_real_content_over_stubs(monkeypatch, tmp_path):
    from app.admin import skill_files

    monkeypatch.setattr("app.admin.skill_files.SKILLS_ROOT", tmp_path)
    stub = tmp_path / "demo-skill" / "references" / "pacing.md"
    stub.parent.mkdir(parents=True)
    stub.write_text("# Pacing\n", encoding="utf-8")

    skill_import.write_resource_files("demo-skill", {"references/pacing.md": b"real content"})

    assert stub.read_bytes() == b"real content"


def test_import_skill_from_archive_creates_skill_and_audits(monkeypatch):
    captured = {}
    written = {}
    monkeypatch.setattr("app.admin.queries.fetch_one", lambda query, params: None)

    def fake_execute_returning(query, params):
        assert "INSERT INTO skills" in query
        assert params[0] == "demo-skill"
        return {"id": 61, "name": params[0], "description": params[1], "argument_hint": params[2], "triggers": params[3], "body": params[4], "resources": params[5], "enabled": True}

    monkeypatch.setattr("app.admin.queries.execute_returning", fake_execute_returning)
    monkeypatch.setattr("app.admin.skill_files.write_skill_files", lambda skill, previous_name=None: written.update({"skill_md": skill["name"]}))
    monkeypatch.setattr("app.admin.skill_import.write_resource_files", lambda name, resource_files: written.update({"resources": dict(resource_files)}))

    class FakeAuditStore:
        def add_log(self, actor_user_id, action, target_type, target_id, metadata):
            captured.update({"actor_user_id": actor_user_id, "action": action, "target_type": target_type, "target_id": target_id, "metadata": metadata})

    monkeypatch.setattr("app.audit.AuditStore", FakeAuditStore)

    content = build_archive({"demo-skill/SKILL.md": SKILL_MD, "demo-skill/references/pacing.md": "60s reel"})

    result = skill_import.import_skill_from_archive(content, "demo.skill", FakeRequest())

    assert result["skill"]["name"] == "demo-skill"
    assert "demo-skill" in result["skill"]["skill_md"]
    assert written == {"skill_md": "demo-skill", "resources": {"references/pacing.md": b"60s reel"}}
    assert captured["action"] == "skill.imported"
    assert captured["target_id"] == 61
    assert captured["metadata"]["resources"] == 1
    assert captured["metadata"]["source_file"] == "demo.skill"


def test_import_skill_from_archive_rejects_duplicate_name(monkeypatch):
    monkeypatch.setattr("app.admin.queries.fetch_one", lambda query, params: {"id": 5})

    with pytest.raises(HTTPException) as error:
        skill_import.import_skill_from_archive(build_archive({"demo-skill/SKILL.md": SKILL_MD}), "demo.skill", FakeRequest())

    assert error.value.status_code == 409
