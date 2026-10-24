"""User-facing agent tool endpoints."""

from fastapi import APIRouter, Request

from ..auth.routes import require_user
from ..connectors.catalog import CONNECTOR_DEFINITIONS
from .subagents import DISPATCH_SPEC
from .tools import default_tool_registry


router = APIRouter(prefix="/api/agent", tags=["agent"])


def catalog_tool_specs() -> list:
    """All tools an agent can be granted: built-in registry, sub-agent dispatch, and connector tools."""
    registry = default_tool_registry()
    specs = [*registry.list_specs(), DISPATCH_SPEC]
    for definition in CONNECTOR_DEFINITIONS.values():
        specs.extend(tool.spec for tool in definition.build_tools(""))
    return specs


@router.get("/tools")
def list_tools(request: Request):
    require_user(request)
    return {
        "tools": [
            {
                "name": spec.name,
                "description": spec.description,
                "parameters": spec.parameters,
                "permission": spec.permission,
            }
            for spec in catalog_tool_specs()
        ]
    }
