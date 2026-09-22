from collections.abc import Callable, Iterator
from dataclasses import dataclass


@dataclass(frozen=True)
class ChatMessage:
    role: str
    content: str
    images: tuple[str, ...] = ()  # data URLs (data:<mime>;base64,<payload>)


def parse_data_url(data_url: str) -> tuple[str, str] | None:
    """Splits a data URL into (mime_type, base64_payload); None when malformed."""
    if not data_url.startswith("data:") or "," not in data_url:
        return None
    header, payload = data_url.split(",", 1)
    mime = header[5:].split(";", 1)[0]
    if not mime or not payload:
        return None
    return mime, payload


@dataclass(frozen=True)
class ChatRequest:
    model: str
    messages: list[ChatMessage]
    temperature: float = 0.7
    # Optional sink for reasoning-model deltas (ChatGPT-style live thinking).
    reasoning_sink: Callable[[str], None] | None = None


@dataclass(frozen=True)
class ProviderDefinition:
    provider_type: str
    display_name: str
    default_base_url: str | None
    api_key_env: str | None
    supports_text: bool = True
    supports_streaming: bool = True
    supports_vision: bool = False
    supports_audio: bool = False
    supports_tools: bool = False
    supports_json: bool = False


class AIProvider:
    provider_type: str

    def stream_chat(self, request: ChatRequest) -> Iterator[str]:
        raise NotImplementedError
