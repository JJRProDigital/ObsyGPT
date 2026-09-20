"""Filesystem tools sandboxed to a workspace root."""

import os
from pathlib import Path

from .base import ToolResult, ToolSpec


MAX_READ_CHARS = 200_000
MAX_DIR_ENTRIES = 200


class SandboxEscapeError(RuntimeError):
    pass


def default_workspace_root() -> Path:
    configured = os.getenv("AGENT_WORKSPACE_ROOT")
    if configured:
        return Path(configured).resolve()
    return Path(__file__).resolve().parents[3] / "workspace"


class _BaseFileTool:
    def __init__(self, workspace_root: Path):
        self.workspace_root = workspace_root.resolve()

    def resolve_path(self, raw_path: str) -> Path:
        candidate = Path(raw_path)
        if candidate.is_absolute():
            resolved = candidate.resolve()
        else:
            resolved = (self.workspace_root / candidate).resolve()
        if not resolved.is_relative_to(self.workspace_root):
            raise SandboxEscapeError(f"Path escapes the agent workspace sandbox: {raw_path}")
        return resolved

    def sandbox_error(self, raw_path: str) -> ToolResult:
        return ToolResult(ok=False, output=f"Blocked: path escapes the agent workspace sandbox: {raw_path}")


class ReadFileTool(_BaseFileTool):
    spec = ToolSpec(
        name="read_file",
        description="Reads a UTF-8 text file from the workspace and returns its content.",
        parameters='{"path": "<relative path inside the workspace>"}',
        permission="safe",
    )

    def run(self, args: dict) -> ToolResult:
        try:
            path = self.resolve_path(str(args.get("path", "")))
        except SandboxEscapeError:
            return self.sandbox_error(str(args.get("path", "")))
        if not path.exists() or not path.is_file():
            return ToolResult(ok=False, output=f"File not found: {args.get('path')}")
        content = path.read_text(encoding="utf-8", errors="replace")
        if len(content) > MAX_READ_CHARS:
            content = content[:MAX_READ_CHARS] + f"\n... [truncated at {MAX_READ_CHARS} chars]"
        return ToolResult(ok=True, output=content)


class ListDirTool(_BaseFileTool):
    spec = ToolSpec(
        name="list_dir",
        description="Lists entries of a directory inside the workspace.",
        parameters='{"path": "<relative directory path, . for root>"}',
        permission="safe",
    )

    def run(self, args: dict) -> ToolResult:
        try:
            path = self.resolve_path(str(args.get("path", ".")))
        except SandboxEscapeError:
            return self.sandbox_error(str(args.get("path", ".")))
        if not path.exists() or not path.is_dir():
            return ToolResult(ok=False, output=f"Directory not found: {args.get('path')}")
        entries = sorted(path.iterdir(), key=lambda item: item.name.lower())
        lines = []
        for entry in entries[:MAX_DIR_ENTRIES]:
            suffix = "/" if entry.is_dir() else ""
            lines.append(f"{entry.name}{suffix}")
        if len(entries) > MAX_DIR_ENTRIES:
            lines.append(f"... [{len(entries) - MAX_DIR_ENTRIES} more entries]")
        return ToolResult(ok=True, output="\n".join(lines) if lines else "(empty directory)")


class WriteFileTool(_BaseFileTool):
    spec = ToolSpec(
        name="write_file",
        description="Creates or overwrites a text file inside the workspace. Requires user approval.",
        parameters='{"path": "<relative path>", "content": "<full file content>"}',
        permission="sensitive",
    )

    def run(self, args: dict) -> ToolResult:
        try:
            path = self.resolve_path(str(args.get("path", "")))
        except SandboxEscapeError:
            return self.sandbox_error(str(args.get("path", "")))
        content = str(args.get("content", ""))
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(content, encoding="utf-8")
        return ToolResult(ok=True, output=f"Wrote {len(content)} chars to {args.get('path')}")


class EditFileTool(_BaseFileTool):
    spec = ToolSpec(
        name="edit_file",
        description="Replaces the first occurrence of a text snippet inside a workspace file. Requires user approval.",
        parameters='{"path": "<relative path>", "find": "<text to find>", "replace": "<replacement>"}',
        permission="sensitive",
    )

    def run(self, args: dict) -> ToolResult:
        try:
            path = self.resolve_path(str(args.get("path", "")))
        except SandboxEscapeError:
            return self.sandbox_error(str(args.get("path", "")))
        find = str(args.get("find", ""))
        replace = str(args.get("replace", ""))
        if not path.exists() or not path.is_file():
            return ToolResult(ok=False, output=f"File not found: {args.get('path')}")
        content = path.read_text(encoding="utf-8", errors="replace")
        if find not in content:
            return ToolResult(ok=False, output=f"Text not found in {args.get('path')}")
        updated = content.replace(find, replace, 1)
        path.write_text(updated, encoding="utf-8")
        return ToolResult(ok=True, output=f"Edited {args.get('path')}")


class FilesTools:
    def __init__(self, workspace_root: Path):
        self.workspace_root = workspace_root

    def tools(self) -> list:
        return [
            ReadFileTool(self.workspace_root),
            ListDirTool(self.workspace_root),
            WriteFileTool(self.workspace_root),
            EditFileTool(self.workspace_root),
        ]
