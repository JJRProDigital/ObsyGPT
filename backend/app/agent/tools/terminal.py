"""Real terminal tool with allowlist, blocklist, timeout, and output truncation."""

import os
import re
import subprocess
import sys
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

# Shell operators that chain multiple commands: every segment is validated.
# Windows cmd separates commands with & and |; POSIX sh also uses ;.
_IS_WINDOWS = sys.platform.startswith("win")


def _split_command_segments(command: str) -> list[str]:
    """Splits a command on shell separators, honoring quoted spans per platform."""
    quote_chars = '"' if _IS_WINDOWS else "\"'"
    segments: list[str] = []
    current: list[str] = []
    quote: str | None = None
    index = 0
    while index < len(command):
        char = command[index]
        if quote is not None:
            if char == quote:
                quote = None
            current.append(char)
        elif char in quote_chars:
            quote = char
            current.append(char)
        elif char in "&|;":
            if char in "&|" and index + 1 < len(command) and command[index + 1] == char:
                index += 1
            segments.append("".join(current))
            current = []
        else:
            current.append(char)
        index += 1
    segments.append("".join(current))
    return [segment.strip() for segment in segments if segment.strip()]

# Minimal environment passed to executed commands. Process secrets
# (API keys, SESSION_SECRET, DB passwords) are deliberately NOT inherited.
SAFE_ENV_KEYS = {
    "PATH",
    "PATHEXT",
    "SYSTEMROOT",
    "COMSPEC",
    "TEMP",
    "TMP",
    "USERNAME",
    "USERPROFILE",
    "HOME",
    "LANG",
    "LC_ALL",
    "TERM",
    "PYTHONIOENCODING",
    "PYTHONUTF8",
}


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


def build_safe_env() -> dict[str, str]:
    """Returns a minimal environment for subprocesses, free of process secrets.

    Extra variables can be whitelisted via AGENT_COMMAND_ENV_PASSTHROUGH
    (comma-separated names) when a workflow genuinely needs them. Encoding
    variables are passed through as-is (no forced default) so parent/child
    stay consistent with the platform locale.
    """
    passthrough = os.getenv("AGENT_COMMAND_ENV_PASSTHROUGH", "")
    allowed = SAFE_ENV_KEYS | {name.strip() for name in passthrough.split(",") if name.strip()}
    env = {name: value for name, value in os.environ.items() if name in allowed and value is not None}
    if sys.platform.startswith("win") and "SYSTEMROOT" not in env:
        env["SYSTEMROOT"] = os.environ.get("SYSTEMROOT", r"C:\Windows")
    return env


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
        for segment in _split_command_segments(stripped):
            first_token = segment.split()[0].lower()
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
                env=build_safe_env(),
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
