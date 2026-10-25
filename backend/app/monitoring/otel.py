"""Optional OTLP http/json export of ObsyGPT activity events.

Configured through env vars (no-op until OTEL_EXPORTER_OTLP_ENDPOINT is set):
- OTEL_EXPORTER_OTLP_ENDPOINT: collector base URL, e.g. http://collector:4318
- OTEL_EXPORTER_OTLP_HEADERS: comma-separated key=value auth headers
- OTEL_CONTENT_CAPTURE: comma list from {prompts, responses, tool_details}; default metadata-only (content redacted)
"""

import contextvars
import json
import os
import queue
import threading
import time
from urllib.request import Request, urlopen

SERVICE_NAME = "obsygpt"
_MAX_QUEUE = 1000
_FLUSH_BATCH = 10
_FLUSH_INTERVAL_SECONDS = 2.0

_queue: "queue.Queue[dict]" = queue.Queue(maxsize=_MAX_QUEUE)
_context: contextvars.ContextVar = contextvars.ContextVar("otel_context", default={})
_worker_started = threading.Lock()
_worker_running = False


def endpoint() -> str | None:
    value = os.getenv("OTEL_EXPORTER_OTLP_ENDPOINT")
    return value.rstrip("/") if value else None


def _headers() -> dict[str, str]:
    raw = os.getenv("OTEL_EXPORTER_OTLP_HEADERS", "")
    headers = {"Content-Type": "application/json"}
    for pair in raw.split(","):
        if "=" in pair:
            key, value = pair.split("=", 1)
            headers[key.strip()] = value.strip()
    return headers


def _captures(flag: str) -> bool:
    raw = os.getenv("OTEL_CONTENT_CAPTURE", "metadata")
    return flag in {item.strip() for item in raw.split(",")}


def bind_context(**attributes) -> None:
    """Attaches correlation attributes (user, conversation) to events on this task."""
    current = dict(_context.get())
    current.update({key: value for key, value in attributes.items() if value is not None})
    _context.set(current)


def _emit(event_name: str, attributes: dict) -> None:
    if not endpoint():
        return
    record = {
        "timeUnixNano": str(time.time_ns()),
        "severityText": "INFO",
        "body": {"stringValue": event_name},
        "attributes": [
            {"key": key, "value": {"stringValue": str(value)}}
            for key, value in {**_context.get(), **attributes}.items()
            if value is not None
        ],
    }
    try:
        _queue.put_nowait(record)
    except queue.Full:
        pass
    _ensure_worker()


def record_user_prompt(prompt_length: int, prompt: str | None = None) -> None:
    _emit(
        "user_prompt",
        {"prompt_length": prompt_length, "prompt": prompt if _captures("prompts") else "<REDACTED>"},
    )


def record_assistant_response(model: str, response_length: int, response: str | None = None) -> None:
    _emit(
        "assistant_response",
        {
            "model": model,
            "response_length": response_length,
            "response": response if _captures("responses") else "<REDACTED>",
        },
    )


def record_tool_result(run_id: int, tool_name: str, status: str, output: str | None = None) -> None:
    _emit(
        "tool_result",
        {
            "run.id": run_id,
            "tool_name": tool_name,
            "success": status == "completed",
            "tool_result_size": len(output or ""),
            "tool_output": output[:2000] if _captures("tool_details") else "<REDACTED>",
        },
    )


def record_api_error(model: str, error: str, stage: str = "primary") -> None:
    _emit("api_error", {"model": model, "error": error[:500], "stage": stage})


def _ensure_worker() -> None:
    global _worker_running
    with _worker_started:
        if _worker_running:
            return
        _worker_running = True
        threading.Thread(target=_worker_loop, name="otel-exporter", daemon=True).start()


def _worker_loop() -> None:
    while True:
        batch = []
        try:
            batch.append(_queue.get(timeout=_FLUSH_INTERVAL_SECONDS))
            while len(batch) < _FLUSH_BATCH:
                batch.append(_queue.get_nowait())
        except queue.Empty:
            pass
        except queue.Full:
            continue
        if batch:
            _post_batch(batch)


def _post_batch(batch: list[dict]) -> None:
    target = endpoint()
    if not target:
        return
    payload = {
        "resourceLogs": [
            {
                "resource": {
                    "attributes": [
                        {"key": "service.name", "value": {"stringValue": SERVICE_NAME}},
                        {"key": "service.version", "value": {"stringValue": os.getenv("OBSYGPT_VERSION", "dev")}},
                    ]
                },
                "scopeLogs": [{"scope": {"name": "obsygpt.activity"}, "logRecords": batch}],
            }
        ]
    }
    try:
        request = Request(
            f"{target}/v1/logs",
            data=json.dumps(payload).encode("utf-8"),
            headers=_headers(),
            method="POST",
        )
        with urlopen(request, timeout=5) as response:
            response.read()
    except Exception:  # noqa: BLE001 - monitoring must never break the app
        pass


def drain_for_tests() -> list[dict]:
    records = []
    while True:
        try:
            records.append(_queue.get_nowait())
        except queue.Empty:
            return records
