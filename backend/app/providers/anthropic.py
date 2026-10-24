import json
from collections.abc import Iterator
from urllib.request import Request as UrlRequest
from urllib.request import urlopen

from .base import AIProvider, ChatRequest, parse_data_url
from .sse import stream_response_tokens


class AnthropicProvider(AIProvider):
    provider_type = "anthropic"

    def __init__(self, api_key: str, base_url: str = "https://api.anthropic.com"):
        self.api_key = api_key
        self.base_url = base_url.rstrip("/")

    def stream_chat(self, request: ChatRequest) -> Iterator[str]:
        body = self.build_payload(request)
        body["stream"] = True
        http_request = UrlRequest(
            f"{self.base_url}/v1/messages",
            data=json.dumps(body).encode("utf-8"),
            headers={
                "content-type": "application/json",
                "x-api-key": self.api_key,
                "anthropic-version": "2023-06-01",
            },
            method="POST",
        )

        with urlopen(http_request, timeout=120) as response:
            yield from stream_response_tokens(response, self.event_text, self.extract_text)

    @staticmethod
    def event_text(event: dict) -> str:
        if event.get("type") == "content_block_delta":
            delta = event.get("delta") or {}
            if delta.get("type") == "text_delta":
                return delta.get("text") or ""
            return ""
        if event.get("type") == "error":
            detail = event.get("error") or {}
            raise RuntimeError(f"Anthropic stream error: {detail.get('message', 'unknown error')}")
        return ""

    def build_payload(self, request: ChatRequest) -> dict:
        system_parts = [message.content for message in request.messages if message.role == "system"]
        messages = []
        for message in request.messages:
            if message.role not in {"user", "assistant"}:
                continue
            if message.images:
                blocks = []
                for image in message.images:
                    parsed = parse_data_url(image)
                    if parsed:
                        mime, payload = parsed
                        blocks.append({"type": "image", "source": {"type": "base64", "media_type": mime, "data": payload}})
                if message.content:
                    blocks.append({"type": "text", "text": message.content})
                messages.append({"role": message.role, "content": blocks})
            else:
                messages.append({"role": message.role, "content": message.content})

        return {
            "model": request.model,
            "system": "\n\n".join(system_parts),
            "messages": messages,
            "temperature": float(request.temperature),
            "max_tokens": 4096,
        }

    def extract_text(self, data: dict) -> str:
        parts = data.get("content", [])
        return "".join(part.get("text", "") for part in parts if part.get("type") == "text")
