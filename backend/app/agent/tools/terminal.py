"""Real terminal tool with allowlist, blocklist, timeout, and output truncation."""

import os
import re
import subprocess
from pathlib import Path

from .base import ToolResult, ToolSpec


DEFAULT_ALLOWLIST = ["git", "python", "node", "npm", "pip", "pytest", "docker", "dir", "type", "rg", "findstr"]
DEFAULT_TIMEOUT_SECONDS = 60
MAX_OUTPUT_CHARS = 10_000

BLOCKED_PATTERNS = [
    r"rm\s+-rf",
    r"\bdel\s+/[fqs]",
    r"\brd\s+/s",
    r"\brmdir\s+/s",
    r"\bformat\b",
    r"\bshutdown\b",
    r"\breg\s+(add|delete|import)",
    r"\btaskkill\b",
    r"\bmkfs\b",
    r"invoke-expression",
    r"iex\s+",
    r"remove-item\s+-recurse",
    r"--force-push|push\s+--force",
    r"drop\s+database",
]

_BLOCKED_RE = re.compile("|".join(BLOCKED_PATTERNS), re.IGNORECASE)


def default_allowlist() -> list[str]:
    configured = os.getenv("AGENT_COMMAND_ALLOWLIST")
    if not configured:
        return list(DEFAULT_ALLOWLIST)
    return [item.strip().lower() for item in configured.split(",") if item.strip()]


def default_timeout_seconds() -> int:
    try:
        return int(os.getenv("AGENT_COMMAND_TIMEOUT_SECONDS", str(DEFAULT_TIMEOUT_SECONDS)))
    except ValueError:
        return DEFAULT_TIMEOUT_SECONDS


class TerminalTool:
    spec = ToolSpec(
        name="run_command",
        description=(
            "Runs a real shell command in the workspace directory. "
            "Only allowlisted command prefixes run; destructive patterns are blocked. Requires user approval."
        ),
        parameters='{"command": "<command to execute>"}',
        permission="sensitive",
    )

    def __init__(
        self,
        workspace_root: Path,
        allowlist: list[str] | None = None,
        timeout_seconds: int | None = None,
        max_output_chars: int = MAX_OUTPUT_CHARS,
    ):
        self.workspace_root = workspace_root.resolve()
        self.allowlist = [item.lower() for item in (allowlist if allowlist is not None else default_allowlist())]
        self.timeout_seconds = timeout_seconds if timeout_seconds is not None else default_timeout_seconds()
        self.max_output_chars = max_output_chars

    def _validate(self, command: str) -> str | None:
        stripped = command.strip()
        if not stripped:
            return "Empty command."
        first_token = stripped.split()[0].lower()
        if first_token not in self.allowlist:
            return f"Command not allowed: '{first_token}' is not in the allowlist ({', '.join(self.allowlist)})."
        if _BLOCKED_RE.search(stripped):
            return "Command blocked: it matches a destructive pattern."
        return None

    def run(self, args: dict) -> ToolResult:
        command = str(args.get("command", ""))
        validation_error = self._validate(command)
        if validation_error:
            return ToolResult(ok=False, output=validation_error)

        self.workspace_root.mkdir(parents=True, exist_ok=True)
        try:
            completed = subprocess.run(
                command,
                shell=True,
                cwd=str(self.workspace_root),
                capture_output=True,
                text=True,
                timeout=self.timeout_seconds,
            )
        except subprocess.TimeoutExpired:
            return ToolResult(ok=False, output=f"Command timed out after {self.timeout_seconds} seconds.")

        output = (completed.stdout or "") + (("\n[stderr]\n" + completed.stderr) if completed.stderr else "")
        if len(output) > self.max_output_chars:
            output = output[: self.max_output_chars] + f"\n... [truncated at {self.max_output_chars} chars]"
        output = output.strip() or "(no output)"

        if completed.returncode != 0:
            return ToolResult(ok=False, output=f"Command failed with exit code {completed.returncode}:\n{output}")
        return ToolResult(ok=True, output=output)
