"""Agent tool registry composition."""

from .base import ToolRegistry, ToolResult, ToolSpec
from .browser import BrowserTools
from .files import FilesTools, default_workspace_root
from .memory import MemorySearchTool
from .terminal import TerminalTool
from .triggers import CancelTriggerTool, MyTriggersTool, ScheduleTriggerTool
from .web import NewsSearchTool, WebFetchTool, WebSearchTool


def default_tool_registry(workspace_root=None) -> ToolRegistry:
    from ...admin.skill_files import SKILLS_ROOT

    workspace = workspace_root or default_workspace_root()
    try:
        workspace.mkdir(parents=True, exist_ok=True)
    except OSError:
        pass
    # Read-only access to agent skill folders so skills can ship reference files.
    registry = ToolRegistry()
    registry.register_many(FilesTools(workspace_root=workspace, read_only_roots=[SKILLS_ROOT]).tools())
    registry.register(TerminalTool(workspace_root=workspace))
    registry.register(WebFetchTool())
    registry.register_many(BrowserTools(workspace_root=workspace).tools())
    registry.register(ScheduleTriggerTool())
    registry.register(MyTriggersTool())
    registry.register(CancelTriggerTool())
    registry.register(MemorySearchTool())
    registry.register(WebSearchTool())
    registry.register(NewsSearchTool())
    return registry
