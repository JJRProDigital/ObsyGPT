import json
from collections.abc import Iterator
from urllib.parse import quote
from urllib.request import Request as UrlRequest
from urllib.request import urlopen

from .base import AIProvider, ChatRequest, parse_data_url
from .sse import stream_response_tokens


class GeminiProvider(AIProvider):
    provider_type = "gemini"

    def __init__(self, api_key: str, base_url: str = "https://generativelanguage.googleapis.com"):
        self.api_key = api_key
        self.base_url = base_url.rstrip("/")

    def stream_chat(self, request: ChatRequest) -> Iterator[str]:
        body = self.build_payload(request)
        model = quote(request.model, safe="")
        http_request = UrlRequest(
            f"{self.base_url}/v1beta/models/{model}:streamGenerateContent?alt=sse&key={self.api_key}",
            data=json.dumps(body).encode("utf-8"),
            headers={"content-type": "application/json"},
            method="POST",
        )

        with urlopen(http_request, timeout=120) as response:
            yield from stream_response_tokens(response, self.extract_text, self.extract_text)

    def build_payload(self, request: ChatRequest) -> dict:
        system_text = "\n\n".join(message.content for message in request.messages if message.role == "system")
        contents = []

        for message in request.messages:
            if message.role == "system":
                continue
            role = "model" if message.role == "assistant" else "user"
            parts = []
            for image in message.images:
                parsed = parse_data_url(image)
                if parsed:
                    mime, payload = parsed
                    parts.append({"inline_data": {"mime_type": mime, "data": payload}})
            if message.content:
                parts.append({"text": message.content})
            contents.append({"role": role, "parts": parts or [{"text": ""}]})

        body = {
            "contents": contents,
            "generationConfig": {"temperature": float(request.temperature)},
        }
        if system_text:
            body["systemInstruction"] = {"parts": [{"text": system_text}]}
        return body

    def extract_text(self, data: dict) -> str:
        candidates = data.get("candidates", [])
        if not candidates:
            return ""
        parts = candidates[0].get("content", {}).get("parts", [])
        return "".join(part.get("text", "") for part in parts)
