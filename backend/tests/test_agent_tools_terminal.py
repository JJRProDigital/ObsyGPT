from pathlib import Path

import pytest

from app.agent.tools.terminal import TerminalTool, default_allowlist, default_timeout_seconds


@pytest.fixture
def tool(tmp_path: Path) -> TerminalTool:
    return TerminalTool(workspace_root=tmp_path, timeout_seconds=15, max_output_chars=2000)


def test_runs_allowlisted_command_and_returns_output(tool: TerminalTool):
    result = tool.run({"command": 'python -c "print(\'agent-ok\')"'})

    assert result.ok
    assert "agent-ok" in result.output


def test_runs_in_workspace_directory(tmp_path: Path):
    tool = TerminalTool(workspace_root=tmp_path, timeout_seconds=15, max_output_chars=2000)

    result = tool.run({"command": 'python -c "import os; print(os.getcwd())"'})

    assert result.ok
    assert str(tmp_path) in result.output


def test_rejects_command_not_in_allowlist(tool: TerminalTool):
    result = tool.run({"command": "curl http://example.com"})

    assert not result.ok
    assert "not allowed" in result.output.lower()


def test_rejects_destructive_pattern_even_if_prefix_allowed(tool: TerminalTool):
    result = tool.run({"command": 'python -c "print(\'rm -rf /\')"'})

    assert not result.ok
    assert "blocked" in result.output.lower()


def test_timeout_produces_clean_failure(tmp_path: Path):
    tool = TerminalTool(workspace_root=tmp_path, timeout_seconds=1, max_output_chars=2000)

    result = tool.run({"command": 'python -c "import time; time.sleep(4)"'})

    assert not result.ok
    assert "timed out" in result.output.lower()


def test_output_is_truncated(tmp_path: Path):
    tool = TerminalTool(workspace_root=tmp_path, timeout_seconds=15, max_output_chars=50)

    result = tool.run({"command": 'python -c "print(\'x\' * 500)"'})

    assert result.ok
    assert len(result.output) <= 120
    assert "truncated" in result.output.lower()


def test_nonzero_exit_code_marks_failure(tool: TerminalTool):
    result = tool.run({"command": 'python -c "import sys; sys.exit(3)"'})

    assert not result.ok
    assert "exit code 3" in result.output.lower()


def test_default_allowlist_and_timeout_from_env(monkeypatch):
    monkeypatch.setenv("AGENT_COMMAND_ALLOWLIST", "git, node")
    monkeypatch.setenv("AGENT_COMMAND_TIMEOUT_SECONDS", "42")

    assert default_allowlist() == ["git", "node"]
    assert default_timeout_seconds() == 42


def test_spec_is_sensitive(tool: TerminalTool):
    assert tool.spec.permission == "sensitive"
    assert tool.spec.name == "run_command"
