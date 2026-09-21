from collections.abc import Iterator

from openai import OpenAI

from .base import AIProvider, ChatRequest, ChatMessage


def message_payload(message: ChatMessage) -> dict:
    """Text-only message, or OpenAI content-parts when the message carries images."""
    if not message.images:
        return {"role": message.role, "content": message.content}
    parts = []
    if message.content:
        parts.append({"type": "text", "text": message.content})
    for image in message.images:
        parts.append({"type": "image_url", "image_url": {"url": image}})
    return {"role": message.role, "content": parts}


class OpenAICompatibleProvider(AIProvider):
    def __init__(self, provider_type: str, api_key: str, base_url: str):
        self.provider_type = provider_type
        self.client = OpenAI(base_url=base_url, api_key=api_key)

    def stream_chat(self, request: ChatRequest) -> Iterator[str]:
        stream = self.client.chat.completions.create(
            model=request.model,
            messages=[message_payload(message) for message in request.messages],
            temperature=float(request.temperature),
            stream=True,
        )

        for chunk in stream:
            token = chunk.choices[0].delta.content
            if token:
                yield token
