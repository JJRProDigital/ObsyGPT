from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def test_alembic_configuration_files_exist():
    assert (ROOT / "alembic.ini").exists()
    assert (ROOT / "migrations" / "env.py").exists()
    assert (ROOT / "migrations" / "script.py.mako").exists()


def test_initial_migration_contains_core_tables():
    migration = ROOT / "migrations" / "versions" / "0001_initial_obsygpt.py"

    assert migration.exists()
    content = migration.read_text(encoding="utf-8")

    for table_name in [
        "users",
        "conversations",
        "messages",
        "providers",
        "models",
        "agents",
        "skills",
        "mcp_servers",
        "workflows",
        "agent_runs",
        "agent_events",
        "attachments",
        "artifacts",
        "sources",
        "tool_calls",
    ]:
        assert f'op.create_table("{table_name}"' in content


def test_initial_migration_seeds_default_workflows_and_providers():
    migration = ROOT / "migrations" / "versions" / "0001_initial_obsygpt.py"
    content = migration.read_text(encoding="utf-8")

    for expected in [
        "OpenRouter",
        "OpenAI",
        "Anthropic",
        "Gemini",
        "Default Single Agent",
        "Research Then Write",
        "Debate Then Judge",
    ]:
        assert expected in content
