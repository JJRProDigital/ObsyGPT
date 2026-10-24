"""Connector catalog definitions shared by API, UI, and the agent bridge."""

from dataclasses import dataclass
from typing import Callable

from ..agent.tools.base import Tool
from . import gdrive, github, higgsfield, higgsfield_api


@dataclass(frozen=True)
class ConnectorDefinition:
    slug: str
    name: str
    description: str
    token_label: str
    token_help: str
    tool_names: list[str]
    build_tools: Callable[..., list[Tool]]
    test_token: Callable[[str], dict]
    auth_type: str = "token"


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
        ConnectorDefinition(
            slug="higgsfield",
            name="Higgsfield",
            description="Genera imagenes y videos con los modelos de Higgsfield a traves de su servidor MCP.",
            auth_type="oauth",
            token_label="",
            token_help="La conexion usa OAuth: al conectar se abre Higgsfield para iniciar sesion y autorizar el acceso. El token se renueva automaticamente.",
            tool_names=[],
            build_tools=higgsfield.build_tools,
            test_token=higgsfield.test_token,
        ),
        ConnectorDefinition(
            slug="higgsfield_api",
            name="Higgsfield API",
            description="Genera imagenes y videos con la API REST de Open Higgsfield (billing en dolares: Kling, Seedance, Wan, Soul).",
            token_label="Credencial API (key_id:key_secret)",
            token_help="Pega las dos credenciales de console.higgsfield.ai unidas por ':' (key_id:key_secret). Billing en dolares, sin OAuth.",
            tool_names=["higgsfield_api_generate_video", "higgsfield_api_generate_image", "higgsfield_api_request_status"],
            build_tools=higgsfield_api.build_tools,
            test_token=higgsfield_api.test_token,
        ),
    ]
}


def get_connector_definition(slug: str) -> ConnectorDefinition:
    definition = CONNECTOR_DEFINITIONS.get(slug)
    if not definition:
        raise ValueError(f"Unknown connector: {slug}")
    return definition
