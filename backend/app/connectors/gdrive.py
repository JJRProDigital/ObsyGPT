"""Google Drive connector tools (REST API with a user-provided OAuth access token, read-only)."""

import json
from urllib.error import HTTPError
from urllib.parse import quote
from urllib.request import Request, urlopen

from ..agent.tools.base import Tool, ToolResult, ToolSpec

DRIVE_API = "https://www.googleapis.com/drive/v3"
MAX_OUTPUT_CHARS = 20000


def _drive_request(token: str, path: str, params: str = "") -> bytes:
    request = Request(
        f"{DRIVE_API}{path}{params}",
        method="GET",
        headers={"Authorization": f"Bearer {token}", "User-Agent": "obsygpt"},
    )
    try:
        with urlopen(request, timeout=20) as response:
            return response.read()
    except HTTPError as error:
        detail = error.read().decode("utf-8", errors="replace")[:300]
        raise RuntimeError(f"Drive API {error.code}: {detail}") from error


def test_token(token: str) -> dict:
    raw = _drive_request(token, "/about", "?fields=user")
    about = json.loads(raw.decode("utf-8"))
    email = about.get("user", {}).get("emailAddress", "usuario desconocido")
    return {"ok": True, "detail": f"Drive de {email}"}


class DriveSearchFilesTool:
    spec = ToolSpec(
        name="drive_search_files",
        description="Busca archivos en el Google Drive del usuario por nombre o texto completo.",
        parameters='{"query": "informe trimestral", "limit": 10}',
        permission="safe",
    )

    def __init__(self, token: str):
        self.token = token

    def run(self, args: dict) -> ToolResult:
        query = str(args.get("query", "")).strip()
        if not query:
            return ToolResult(ok=False, output="Missing required argument: query")
        limit = max(1, min(int(args.get("limit", 10) or 10), 25))
        escaped = quote(f"fullText contains '{query.replace(chr(39), '')}'")
        try:
            raw = _drive_request(
                self.token,
                "/files",
                f"?q={escaped}&pageSize={limit}&fields=files(id,name,mimeType,webViewLink)",
            )
        except Exception as error:  # noqa: BLE001
            return ToolResult(ok=False, output=f"drive_search_files failed: {error}")
        files = json.loads(raw.decode("utf-8")).get("files", [])
        if not files:
            return ToolResult(ok=True, output="Sin resultados.")
        lines = [f"{file['name']} ({file.get('mimeType', '?')}) - {file.get('webViewLink') or file.get('id', '')}" for file in files]
        return ToolResult(ok=True, output="\n".join(lines)[:MAX_OUTPUT_CHARS])


class DriveReadFileTool:
    spec = ToolSpec(
        name="drive_read_file",
        description="Lee el contenido de un archivo de Google Drive como texto (documentos de Google se exportan a texto plano).",
        parameters='{"file_id": "1AbC..."}',
        permission="safe",
    )

    def __init__(self, token: str):
        self.token = token

    def run(self, args: dict) -> ToolResult:
        file_id = str(args.get("file_id", "")).strip()
        if not file_id:
            return ToolResult(ok=False, output="Missing required argument: file_id")
        try:
            metadata_raw = _drive_request(self.token, f"/files/{quote(file_id)}", "?fields=name,mimeType")
            metadata = json.loads(metadata_raw.decode("utf-8"))
            mime_type = metadata.get("mimeType", "")
            if mime_type.startswith("application/vnd.google-apps"):
                content_raw = _drive_request(self.token, f"/files/{quote(file_id)}/export", "?mimeType=text/plain")
            else:
                content_raw = _drive_request(self.token, f"/files/{quote(file_id)}", "?alt=media")
        except Exception as error:  # noqa: BLE001
            return ToolResult(ok=False, output=f"drive_read_file failed: {error}")
        content = content_raw.decode("utf-8", errors="replace")
        header = f"Archivo: {metadata.get('name', file_id)}\n\n"
        return ToolResult(ok=True, output=(header + content)[:MAX_OUTPUT_CHARS])


def build_tools(token: str) -> list[Tool]:
    return [
        DriveSearchFilesTool(token),
        DriveReadFileTool(token),
    ]
