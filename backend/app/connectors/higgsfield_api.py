"""Higgsfield API connector (Open Higgsfield, https://open.higgsfield.ai).

REST API with static credentials: "Authorization: Key {KEY_ID}:{KEY_SECRET}".
The pasted token must be the credential pair joined with a colon. Generation is
asynchronous: submissions return a request handle (request_id + status_url) and
a second tool polls the status until completion.
"""

import json
import re
import time
from urllib.error import HTTPError
from urllib.request import Request, urlopen

from ..agent.tools.base import Tool, ToolResult, ToolSpec

API_BASE = "https://api.higgsfield.ai"
DEFAULT_VIDEO_ENDPOINT = "kling-video/v3.0/std/text-to-video"
DEFAULT_IMAGE_ENDPOINT = "higgsfield-ai/soul/v2/standard"
KNOWN_VIDEO_ENDPOINTS = (
    DEFAULT_VIDEO_ENDPOINT,
    "kling-video/v3.0/turbo/text-to-video",
    "kling-video/v3.0/4k/text-to-video",
    "bytedance/seedance-2.5/text-to-video",
    "alibaba/wan-3.0/text-to-video",
    "alibaba/wan-3.0-prime/text-to-video",
)
ENDPOINT_PATTERN = re.compile(r"^[a-z0-9\-]+(/[a-z0-9\-\.]+)+$")
MAX_OUTPUT_CHARS = 20000
TERMINAL_STATUSES = {"completed", "failed", "nsfw", "canceled"}


def _split_credentials(token: str) -> tuple[str, str]:
    parts = token.split(":", 1)
    if len(parts) != 2 or not parts[0].strip() or not parts[1].strip():
        raise RuntimeError(
            "Formato de credencial invalido: usa key_id:key_secret (dos valores de console.higgsfield.ai unidos por ':')."
        )
    return parts[0].strip(), parts[1].strip()


def _auth_header(token: str) -> dict:
    key_id, key_secret = _split_credentials(token)
    return {"Authorization": f"Key {key_id}:{key_secret}"}


def _http_json(url: str, token: str, payload: dict | None = None, timeout: int = 60) -> dict:
    headers = _auth_header(token)
    headers["Accept"] = "application/json"
    if payload is not None:
        headers["Content-Type"] = "application/json"
        request = Request(url, data=json.dumps(payload).encode("utf-8"), headers=headers, method="POST")
    else:
        request = Request(url, headers=headers, method="GET")
    try:
        with urlopen(request, timeout=timeout) as response:
            return json.loads(response.read().decode("utf-8", errors="replace") or "{}")
    except HTTPError as error:
        detail = error.read().decode("utf-8", errors="replace")[:300]
        raise RuntimeError(f"Higgsfield API {error.code}: {detail}") from error


def _validate_endpoint(endpoint: str) -> str:
    endpoint = str(endpoint).strip().strip("/")
    if not ENDPOINT_PATTERN.match(endpoint):
        raise RuntimeError(f"Endpoint invalido: {endpoint!r}. Usa el Endpoint ID de la documentacion (ej. {DEFAULT_VIDEO_ENDPOINT}).")
    return endpoint


def _format_submission(response: dict) -> str:
    request_id = response.get("request_id", "")
    status_url = response.get("status_url", "")
    lines = [f"Request aceptado: estado {response.get('status', 'desconocido')}."]
    if request_id:
        lines.append(f"request_id: {request_id}")
    if status_url:
        lines.append(f"Consulta el resultado con higgsfield_api_request_status (request_id o status_url): {status_url}")
    return "\n".join(lines)


def _format_status(response: dict) -> str:
    status = str(response.get("status", "unknown"))
    lines = [f"Estado: {status}"]
    if status == "completed":
        video = response.get("video")
        if isinstance(video, dict) and video.get("url"):
            lines.append(f"video: {video['url']}")
        images = response.get("images")
        if isinstance(images, list):
            for image in images[:4]:
                if isinstance(image, dict) and image.get("url"):
                    lines.append(f"imagen: {image['url']}")
        audio = response.get("audio")
        if isinstance(audio, dict) and audio.get("url"):
            lines.append(f"audio: {audio['url']}")
    elif status in TERMINAL_STATUSES:
        error = response.get("error")
        if error:
            lines.append(f"error: {json.dumps(error)[:300]}")
    else:
        lines.append("El request sigue en curso; vuelve a consultar en un rato.")
    return "\n".join(lines)


class _HiggsfieldApiGenerationTool:
    endpoint_label = "generation"

    def __init__(self, token: str, default_endpoint: str, extra_description: str = ""):
        self.token = token
        self.default_endpoint = default_endpoint
        self.extra_description = extra_description

    def _spec(self, name: str, description: str, parameters: str) -> ToolSpec:
        return ToolSpec(name=name, description=description, parameters=parameters, permission="sensitive")

    def run(self, args: dict) -> ToolResult:
        endpoint = str(args.get("endpoint", "")).strip() or self.default_endpoint
        try:
            endpoint = _validate_endpoint(endpoint)
            body = {key: value for key, value in args.items() if key not in ("endpoint",)}
            if not str(body.get("prompt", "")).strip():
                return ToolResult(ok=False, output="Missing required argument: prompt")
            response = _http_json(f"{API_BASE}/{endpoint}", self.token, payload=body)
        except Exception as error:  # noqa: BLE001
            return ToolResult(ok=False, output=f"{self.endpoint_label} failed: {error}")
        return ToolResult(ok=True, output=_format_submission(response)[:MAX_OUTPUT_CHARS])


class HiggsfieldApiVideoTool(_HiggsfieldApiGenerationTool):
    def __init__(self, token: str):
        known = ", ".join(KNOWN_VIDEO_ENDPOINTS[:3])
        super().__init__(token, DEFAULT_VIDEO_ENDPOINT)
        self.spec = self._spec(
            name="higgsfield_api_generate_video",
            description=(
                "Genera un video con Higgsfield API (billing en DOLARES del saldo API, no creditos de la app). Herramienta preferida para videos. "
                f"Endpoint por defecto: {DEFAULT_VIDEO_ENDPOINT} (Kling 3.0 Standard). Otros conocidos: {known}. "
                "Devuelve un request en cola (1-5 min de generacion); consulta el resultado con higgsfield_api_request_status usando wait_seconds para esperar."
            ),
            parameters='{"endpoint": "kling-video/v3.0/std/text-to-video", "prompt": "un gato astronauta", "duration": 5, "aspect_ratio": "16:9"}',
        )


class HiggsfieldApiImageTool(_HiggsfieldApiGenerationTool):
    def __init__(self, token: str):
        super().__init__(token, DEFAULT_IMAGE_ENDPOINT)
        self.spec = self._spec(
            name="higgsfield_api_generate_image",
            description=(
                "Genera una imagen con Higgsfield API (billing en DOLARES del saldo API, no creditos de la app). Herramienta preferida para imagenes. "
                f"Endpoint por defecto: {DEFAULT_IMAGE_ENDPOINT} (Soul V2 Standard). "
                "Devuelve un request en cola; consulta el resultado con higgsfield_api_request_status."
            ),
            parameters='{"endpoint": "higgsfield-ai/soul/v2/standard", "prompt": "retrato editorial con luz suave"}',
        )


class HiggsfieldApiStatusTool:
    spec = ToolSpec(
        name="higgsfield_api_request_status",
        description=(
            "Consulta el estado de un request de Higgsfield API. Cuando esta completed devuelve las URLs del video/imagen generados. "
            "Las generaciones tardan 1-5 minutos: usa wait_seconds (hasta 120) para que la tool espere y no consultes repetidamente con los mismos argumentos."
        ),
        parameters='{"request_id": "d7e6c0f3-6699-4f6c-bb45-2ad7fd9158ff", "wait_seconds": 90}',
        permission="safe",
    )

    POLL_INTERVAL_SECONDS = 5
    MAX_WAIT_SECONDS = 120

    def __init__(self, token: str):
        self.token = token

    def run(self, args: dict) -> ToolResult:
        status_url = str(args.get("status_url", "")).strip()
        request_id = str(args.get("request_id", "")).strip()
        if not status_url and not request_id:
            return ToolResult(ok=False, output="Missing required argument: request_id (o status_url)")
        if status_url and not status_url.startswith(API_BASE):
            return ToolResult(ok=False, output="status_url invalido: debe apuntar a api.higgsfield.ai")
        url = status_url or f"{API_BASE}/requests/{request_id}/status"
        try:
            wait_seconds = min(int(args.get("wait_seconds") or 0), self.MAX_WAIT_SECONDS)
        except (TypeError, ValueError):
            wait_seconds = 0
        elapsed = 0.0
        response: dict = {}
        while True:
            try:
                response = _http_json(url, self.token)
            except Exception as error:  # noqa: BLE001
                return ToolResult(ok=False, output=f"request_status failed: {error}")
            status = str(response.get("status", "unknown"))
            if status in TERMINAL_STATUSES or elapsed >= wait_seconds:
                break
            time.sleep(min(self.POLL_INTERVAL_SECONDS, wait_seconds - elapsed))
            elapsed += self.POLL_INTERVAL_SECONDS
        return ToolResult(ok=True, output=_format_status(response)[:MAX_OUTPUT_CHARS])


def test_token(token: str) -> dict:
    _split_credentials(token)
    try:
        _http_json(f"{API_BASE}/requests/00000000-0000-0000-0000-000000000000/status", token, timeout=20)
    except RuntimeError as error:
        message = str(error)
        if "401" in message or "403" in message:
            raise RuntimeError(f"Credenciales rechazadas por Higgsfield: {message}") from error
        return {"ok": True, "detail": "Credenciales Higgsfield API aceptadas (auth OK, request inexistente esperado)."}
    return {"ok": True, "detail": "Credenciales Higgsfield API aceptadas."}


def build_tools(token: str) -> list[Tool]:
    return [HiggsfieldApiVideoTool(token), HiggsfieldApiImageTool(token), HiggsfieldApiStatusTool(token)]
