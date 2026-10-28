from collections.abc import Iterator

from openai import OpenAI

from .base import AIProvider, ChatRequest, ChatMessage
from .openai_compatible import message_payload


class OpenRouterProvider(AIProvider):
    provider_type = "openrouter"

    def __init__(self, api_key: str, base_url: str = "https://openrouter.ai/api/v1"):
        self.client = OpenAI(
            base_url=base_url,
            api_key=api_key,
        )

    def stream_chat(self, request: ChatRequest) -> Iterator[str]:
        stream = self.client.chat.completions.create(
            model=request.model,
            messages=[message_payload(message) for message in request.messages],
            temperature=float(request.temperature),
            stream=True,
            extra_body={"provider": {"sort": "latency"}},
        )

        for chunk in stream:
            token = chunk.choices[0].delta.content
            if token:
                yield token
