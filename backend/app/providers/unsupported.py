from collections.abc import Iterator

from .base import AIProvider, ChatRequest


class UnsupportedProvider(AIProvider):
    def __init__(self, provider_type: str, message: str):
        self.provider_type = provider_type
        self.message = message

    def stream_chat(self, request: ChatRequest) -> Iterator[str]:
        raise RuntimeError(self.message)
