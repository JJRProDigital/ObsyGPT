"""GitHub connector tools (REST API with a user-provided PAT)."""

import base64
import json
from urllib.error import HTTPError
from urllib.parse import quote
from urllib.request import Request, urlopen

from ..agent.tools.base import Tool, ToolResult, ToolSpec

GITHUB_API = "https://api.github.com"
MAX_OUTPUT_CHARS = 20000


def _github_request(token: str, method: str, path: str, body: dict | None = None) -> dict:
    data = json.dumps(body).encode("utf-8") if body is not None else None
    request = Request(
        f"{GITHUB_API}{path}",
        data=data,
        method=method,
        headers={
            "Authorization": f"Bearer {token}",
            "Accept": "application/vnd.github+json",
            "X-GitHub-Api-Version": "2022-11-28",
            "User-Agent": "obsygpt",
        },
    )
    try:
        with urlopen(request, timeout=20) as response:
            raw = response.read().decode("utf-8")
    except HTTPError as error:
        detail = error.read().decode("utf-8", errors="replace")[:300]
        raise RuntimeError(f"GitHub API {error.code}: {detail}") from error
    return json.loads(raw) if raw else {}


def test_token(token: str) -> dict:
    user = _github_request(token, "GET", "/user")
    return {"ok": True, "detail": f"Autenticado como {user.get('login', 'usuario desconocido')}"}


def _format_repos(payload: dict) -> str:
    items = payload.get("items", [])
    if not items:
        return "Sin resultados."
    lines = [f"{repo['full_name']} (stars {repo.get('stargazers_count', 0)}) - {repo.get('description') or 'sin descripción'}" for repo in items]
    return "\n".join(lines)[:MAX_OUTPUT_CHARS]


def _format_issues(issues: list[dict]) -> str:
    if not issues:
        return "Sin issues."
    lines = [f"#{issue['number']} {issue['title']} ({issue.get('user', {}).get('login', '?')}) - {issue.get('html_url', '')}" for issue in issues]
    return "\n".join(lines)[:MAX_OUTPUT_CHARS]


class GitHubSearchReposTool:
    spec = ToolSpec(
        name="github_search_repos",
        description="Busca repositorios públicos en GitHub por consulta y devuelve nombre, stars y descripción.",
        parameters='{"query": "fastapi postgres", "limit": 5}',
        permission="safe",
    )

    def __init__(self, token: str):
        self.token = token

    def run(self, args: dict) -> ToolResult:
        query = str(args.get("query", "")).strip()
        if not query:
            return ToolResult(ok=False, output="Missing required argument: query")
        limit = max(1, min(int(args.get("limit", 5) or 5), 10))
        try:
            payload = _github_request(self.token, "GET", f"/search/repositories?q={quote(query)}&per_page={limit}")
        except Exception as error:  # noqa: BLE001
            return ToolResult(ok=False, output=f"github_search_repos failed: {error}")
        return ToolResult(ok=True, output=_format_repos(payload))


class GitHubListIssuesTool:
    spec = ToolSpec(
        name="github_list_issues",
        description="Lista issues de un repositorio GitHub (owner/repo) con estado abierto o cerrado.",
        parameters='{"owner": "fastapi", "repo": "fastapi", "state": "open"}',
        permission="safe",
    )

    def __init__(self, token: str):
        self.token = token

    def run(self, args: dict) -> ToolResult:
        owner = str(args.get("owner", "")).strip()
        repo = str(args.get("repo", "")).strip()
        if not owner or not repo:
            return ToolResult(ok=False, output="Missing required arguments: owner and repo")
        state = "open" if str(args.get("state", "open")) == "closed" else "open"
        try:
            payload = _github_request(self.token, "GET", f"/repos/{quote(owner)}/{quote(repo)}/issues?state={state}&per_page=10")
        except Exception as error:  # noqa: BLE001
            return ToolResult(ok=False, output=f"github_list_issues failed: {error}")
        return ToolResult(ok=True, output=_format_issues(payload))


class GitHubReadFileTool:
    spec = ToolSpec(
        name="github_read_file",
        description="Lee el contenido de un archivo de texto de un repositorio GitHub y lo devuelve decodificado.",
        parameters='{"owner": "fastapi", "repo": "fastapi", "path": "README.md", "branch": "master"}',
        permission="safe",
    )

    def __init__(self, token: str):
        self.token = token

    def run(self, args: dict) -> ToolResult:
        owner = str(args.get("owner", "")).strip()
        repo = str(args.get("repo", "")).strip()
        path = str(args.get("path", "")).strip()
        if not owner or not repo or not path:
            return ToolResult(ok=False, output="Missing required arguments: owner, repo and path")
        branch = str(args.get("branch", "")).strip()
        ref = f"?ref={quote(branch)}" if branch else ""
        try:
            payload = _github_request(self.token, "GET", f"/repos/{quote(owner)}/{quote(repo)}/contents/{quote(path)}{ref}")
        except Exception as error:  # noqa: BLE001
            return ToolResult(ok=False, output=f"github_read_file failed: {error}")
        if payload.get("encoding") != "base64" or "content" not in payload:
            return ToolResult(ok=False, output=f"El archivo no se puede leer como texto (tamaño {payload.get('size', '?')} bytes).")
        content = base64.b64decode(payload["content"]).decode("utf-8", errors="replace")
        return ToolResult(ok=True, output=content[:MAX_OUTPUT_CHARS])


class GitHubCreateIssueTool:
    spec = ToolSpec(
        name="github_create_issue",
        description="Crea un issue en un repositorio GitHub en nombre del usuario conectado.",
        parameters='{"owner": "fastapi", "repo": "fastapi", "title": "Bug en X", "body": "Descripcion del problema"}',
        permission="sensitive",
    )

    def __init__(self, token: str):
        self.token = token

    def run(self, args: dict) -> ToolResult:
        owner = str(args.get("owner", "")).strip()
        repo = str(args.get("repo", "")).strip()
        title = str(args.get("title", "")).strip()
        if not owner or not repo or not title:
            return ToolResult(ok=False, output="Missing required arguments: owner, repo and title")
        body = str(args.get("body", ""))
        try:
            payload = _github_request(
                self.token,
                "POST",
                f"/repos/{quote(owner)}/{quote(repo)}/issues",
                {"title": title, "body": body},
            )
        except Exception as error:  # noqa: BLE001
            return ToolResult(ok=False, output=f"github_create_issue failed: {error}")
        return ToolResult(ok=True, output=f"Issue creado: {payload.get('html_url', payload.get('number', '?'))}")


def build_tools(token: str) -> list[Tool]:
    return [
        GitHubSearchReposTool(token),
        GitHubListIssuesTool(token),
        GitHubReadFileTool(token),
        GitHubCreateIssueTool(token),
    ]
