"""Shared SSE stream parsing for HTTP providers.

`stream_response_tokens` consumes an SSE-framed response incrementally; when
the response is NOT SSE-framed (unit-test fakes, non-streaming proxies) it
falls back to a single full-body JSON payload so callers keep working.
"""

import json
from collections.abc import Callable, Iterator


def _looks_like_sse(first_bytes: bytes) -> bool:
    stripped = first_bytes.lstrip()
    return stripped.startswith(b"data:") or stripped.startswith(b"event:")


def stream_response_tokens(
    response,  # noqa: ANN001 - urllib-style response object
    event_text: Callable[[dict], str],
    fallback_extract: Callable[[dict], str],
) -> Iterator[str]:
    """Yields text tokens from an SSE (or plain JSON) provider response."""
    first = response.read(16)
    if not _looks_like_sse(first):
        payload = json.loads((first + response.read()).decode("utf-8"))
        text = fallback_extract(payload)
        if text:
            yield text
        return

    def _lines():
        pending = first
        for line in response:
            yield pending + line
            pending = b""
        if pending.strip():
            yield pending

    for raw_line in _lines():
        line = raw_line.strip()
        if not line.startswith(b"data:"):
            continue
        chunk = line[len(b"data:"):].strip()
        if not chunk or chunk == b"[DONE]":
            continue
        event = json.loads(chunk)
        text = event_text(event)
        if text:
            yield text
