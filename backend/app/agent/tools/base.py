"""Tool abstractions for the agent loop."""

from dataclasses import dataclass
from typing import Literal, Protocol


Permission = Literal["safe", "sensitive"]


@dataclass(frozen=True)
class ToolSpec:
    name: str
    description: str
    parameters: str
    permission: Permission


@dataclass(frozen=True)
class ToolResult:
    ok: bool
    output: str


class UnknownToolError(KeyError):
    pass


class Tool(Protocol):
    spec: ToolSpec

    def run(self, args: dict) -> ToolResult:
        ...


class ToolRegistry:
    def __init__(self) -> None:
        self._tools: dict[str, Tool] = {}

    def register(self, tool: Tool) -> None:
        self._tools[tool.spec.name] = tool

    def register_many(self, tools: list[Tool]) -> None:
        for tool in tools:
            self.register(tool)

    def get(self, name: str) -> Tool:
        tool = self._tools.get(name)
        if not tool:
            raise UnknownToolError(f"Tool is not registered: {name}")
        return tool

    def list_specs(self) -> list[ToolSpec]:
        return [tool.spec for tool in self._tools.values()]

    def run(self, name: str, args: dict) -> ToolResult:
        return self.get(name).run(args)
