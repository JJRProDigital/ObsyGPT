from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
SKILLS_ROOT = ROOT / "agents" / "skills"


def test_builtin_agent_skill_files_and_resources_exist():
    skill_files = sorted(SKILLS_ROOT.glob("*/SKILL.md"))

    builtin = {
        "analyze_image",
        "critic_review",
        "extract_pdf",
        "final_answer",
        "read_url",
        "summarize_document",
        "web_search",
    }
    assert builtin <= {path.parent.name for path in skill_files}

    for skill_file in skill_files:
        content = skill_file.read_text(encoding="utf-8")
        assert content.startswith("---\nname: ")
        if "## Recursos opcionales" not in content:
            continue
        resources_block = content.split("## Recursos opcionales", 1)[1]
        for line in resources_block.splitlines():
            resource = line.strip()
            if not resource or resource.startswith("#") or resource.startswith("-"):
                continue
            assert (skill_file.parent / resource).exists(), f"Missing resource {resource} for {skill_file.parent.name}"
