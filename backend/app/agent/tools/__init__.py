"""Agent tool registry composition."""

from .base import ToolRegistry, ToolResult, ToolSpec
from .browser import BrowserTools
from .files import FilesTools, default_workspace_root
from .terminal import TerminalTool
from .web import WebFetchTool


def default_tool_registry(workspace_root=None) -> ToolRegistry:
    workspace = workspace_root or default_workspace_root()
    try:
        workspace.mkdir(parents=True, exist_ok=True)
    except OSError:
        pass
    registry = ToolRegistry()
    registry.register_many(FilesTools(workspace_root=workspace).tools())
    registry.register(TerminalTool(workspace_root=workspace))
    registry.register(WebFetchTool())
    registry.register_many(BrowserTools(workspace_root=workspace).tools())
    return registry
