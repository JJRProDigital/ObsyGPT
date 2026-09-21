"""Connector catalog definitions shared by API, UI, and the agent bridge."""

from dataclasses import dataclass
from typing import Callable

from ..agent.tools.base import Tool
from . import gdrive, github


@dataclass(frozen=True)
class ConnectorDefinition:
    slug: str
    name: str
    description: str
    token_label: str
    token_help: str
    tool_names: list[str]
    build_tools: Callable[[str], list[Tool]]
    test_token: Callable[[str], dict]


CONNECTOR_DEFINITIONS: dict[str, ConnectorDefinition] = {
    definition.slug: definition
    for definition in [
        ConnectorDefinition(
            slug="github",
            name="GitHub",
            description="Buscar repos, leer archivos e issues, y crear issues en nombre del usuario.",
            token_label="Personal access token (PAT)",
            token_help="Crea un token en GitHub > Settings > Developer settings > Personal access tokens con permisos de repo.",
            tool_names=["github_search_repos", "github_list_issues", "github_read_file", "github_create_issue"],
            build_tools=github.build_tools,
            test_token=github.test_token,
        ),
        ConnectorDefinition(
            slug="gdrive",
            name="Google Drive",
            description="Buscar archivos y leer documentos de Google Drive del usuario (solo lectura).",
            token_label="OAuth access token",
            token_help="Pega un access token de OAuth con scope drive.readonly (por ejemplo generado con OAuth Playground). Caduca en ~1h.",
            tool_names=["drive_search_files", "drive_read_file"],
            build_tools=gdrive.build_tools,
            test_token=gdrive.test_token,
        ),
    ]
}


def get_connector_definition(slug: str) -> ConnectorDefinition:
    definition = CONNECTOR_DEFINITIONS.get(slug)
    if not definition:
        raise ValueError(f"Unknown connector: {slug}")
    return definition
