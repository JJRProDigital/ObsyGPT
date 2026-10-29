from pathlib import Path

import pytest

from app.agent.tools.base import ToolRegistry
from app.agent.tools.files import FilesTools, default_workspace_root


@pytest.fixture
def registry(tmp_path: Path) -> ToolRegistry:
    files = FilesTools(workspace_root=tmp_path)
    registry = ToolRegistry()
    registry.register_many(files.tools())
    return registry


def test_registry_exposes_specs_with_permissions(registry: ToolRegistry):
    specs = {spec.name: spec for spec in registry.list_specs()}

    assert specs["read_file"].permission == "safe"
    assert specs["list_dir"].permission == "safe"
    assert specs["write_file"].permission == "sensitive"
    assert specs["edit_file"].permission == "sensitive"


def test_read_file_returns_content(registry: ToolRegistry, tmp_path: Path):
    (tmp_path / "notes.txt").write_text("hola mundo", encoding="utf-8")

    result = registry.run("read_file", {"path": "notes.txt"})

    assert result.ok
    assert "hola mundo" in result.output


def test_read_file_blocks_sandbox_escape(registry: ToolRegistry, tmp_path: Path):
    secret = tmp_path.parent / "agent-sandbox-secret.txt"
    secret.write_text("secreto", encoding="utf-8")

    result = registry.run("read_file", {"path": "../agent-sandbox-secret.txt"})

    assert not result.ok
    assert "sandbox" in result.output.lower()


def test_read_file_blocks_absolute_path_outside_root(registry: ToolRegistry, tmp_path: Path):
    result = registry.run("read_file", {"path": str(tmp_path.parent / "cualquier.txt")})

    assert not result.ok


def test_read_file_missing_file_fails_cleanly(registry: ToolRegistry):
    result = registry.run("read_file", {"path": "no_existe.txt"})

    assert not result.ok
    assert "not found" in result.output.lower()


def test_list_dir_lists_entries(registry: ToolRegistry, tmp_path: Path):
    (tmp_path / "a.txt").write_text("a", encoding="utf-8")
    (tmp_path / "sub").mkdir()
    (tmp_path / "sub" / "b.txt").write_text("b", encoding="utf-8")

    result = registry.run("list_dir", {"path": "."})

    assert result.ok
    assert "a.txt" in result.output
    assert "sub/" in result.output


def test_write_file_creates_nested_path(registry: ToolRegistry, tmp_path: Path):
    result = registry.run("write_file", {"path": "reports/enero.md", "content": "# Enero"})

    assert result.ok
    assert (tmp_path / "reports" / "enero.md").read_text(encoding="utf-8") == "# Enero"


def test_write_file_blocks_escape(registry: ToolRegistry, tmp_path: Path):
    result = registry.run("write_file", {"path": "../evil.txt", "content": "x"})

    assert not result.ok
    assert not (tmp_path.parent / "evil.txt").exists()


def test_edit_file_replaces_first_occurrence(registry: ToolRegistry, tmp_path: Path):
    (tmp_path / "doc.md").write_text("alpha beta alpha", encoding="utf-8")

    result = registry.run("edit_file", {"path": "doc.md", "find": "beta", "replace": "gamma"})

    assert result.ok
    assert (tmp_path / "doc.md").read_text(encoding="utf-8") == "alpha gamma alpha"


def test_edit_file_missing_find_fails(registry: ToolRegistry, tmp_path: Path):
    (tmp_path / "doc.md").write_text("alpha", encoding="utf-8")

    result = registry.run("edit_file", {"path": "doc.md", "find": "zeta", "replace": "gamma"})

    assert not result.ok
    assert (tmp_path / "doc.md").read_text(encoding="utf-8") == "alpha"


def test_unknown_tool_raises(registry: ToolRegistry):
    with pytest.raises(Exception):
        registry.run("no_existe", {})


def test_default_workspace_root_points_to_repo_workspace():
    root = default_workspace_root()

    assert root.name == "workspace"
    assert root.parent.name == "backend"


@pytest.fixture
def skills_registry(tmp_path: Path) -> ToolRegistry:
    skills_root = tmp_path / "repo" / "agents" / "skills"
    skill_dir = skills_root / "demo-skill"
    (skill_dir / "references").mkdir(parents=True)
    (skill_dir / "references" / "pacing.md").write_text("60s reel", encoding="utf-8")
    (skill_dir / "SKILL.md").write_text("---\nname: demo-skill\n---\n", encoding="utf-8")
    workspace = tmp_path / "repo" / "workspace"
    workspace.mkdir(parents=True)
    registry = ToolRegistry()
    registry.register_many(FilesTools(workspace_root=workspace, read_only_roots=[skills_root]).tools())
    return registry


def test_read_file_reads_skill_resource_via_canonical_prefix(skills_registry: ToolRegistry):
    result = skills_registry.run("read_file", {"path": "agents/skills/demo-skill/references/pacing.md"})

    assert result.ok
    assert "60s reel" in result.output


def test_read_file_accepts_absolute_path_inside_read_only_root(skills_registry: ToolRegistry, tmp_path: Path):
    target = tmp_path / "repo" / "agents" / "skills" / "demo-skill" / "SKILL.md"

    result = skills_registry.run("read_file", {"path": str(target)})

    assert result.ok
    assert "name: demo-skill" in result.output


def test_list_dir_lists_skill_folder(skills_registry: ToolRegistry):
    result = skills_registry.run("list_dir", {"path": "agents/skills/demo-skill"})

    assert result.ok
    assert "references/" in result.output
    assert "SKILL.md" in result.output


def test_write_file_still_blocked_for_skill_paths(skills_registry: ToolRegistry, tmp_path: Path):
    result = skills_registry.run("write_file", {"path": "agents/skills/demo-skill/evil.md", "content": "x"})

    assert not result.ok
    assert not (tmp_path / "repo" / "agents" / "skills" / "demo-skill" / "evil.md").exists()


def test_read_file_blocks_traversal_through_skill_prefix(skills_registry: ToolRegistry):
    result = skills_registry.run("read_file", {"path": "agents/skills/../../../../secrets.txt"})

    assert not result.ok


def test_read_file_skill_prefix_always_maps_to_skills_root(skills_registry: ToolRegistry, tmp_path: Path):
    workspace = tmp_path / "repo" / "workspace"
    (workspace / "agents" / "skills" / "mine").mkdir(parents=True)
    (workspace / "agents" / "skills" / "mine" / "SKILL.md").write_text("in workspace", encoding="utf-8")

    result = skills_registry.run("read_file", {"path": "agents/skills/mine/SKILL.md"})

    assert not result.ok
    assert "not found" in result.output.lower()


def test_skills_root_keeps_canonical_agents_skills_layout():
    from app.admin.skill_files import SKILLS_ROOT

    assert SKILLS_ROOT.parts[-2:] == ("agents", "skills")
