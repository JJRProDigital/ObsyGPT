from collections.abc import Iterator

from openai import OpenAI

from .base import AIProvider, ChatRequest, ChatMessage

# Without a cap, a degenerate local-model generation (no EOS) produces tokens
# forever and wedges single-slot llama.cpp servers for every other request.
DEFAULT_MAX_TOKENS = 4096
# The OpenAI SDK default timeout is 600s; a wedged server should fail the run
# much sooner so the UI surfaces the error instead of a silent stall.
REQUEST_TIMEOUT_SECONDS = 300


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
        self.client = OpenAI(base_url=base_url, api_key=api_key, timeout=REQUEST_TIMEOUT_SECONDS)

    def stream_chat(self, request: ChatRequest) -> Iterator[str]:
        stream = self.client.chat.completions.create(
            model=request.model,
            messages=[message_payload(message) for message in request.messages],
            temperature=float(request.temperature),
            max_tokens=DEFAULT_MAX_TOKENS,
            stream=True,
        )

        for chunk in stream:
            if not chunk.choices:
                continue
            delta = chunk.choices[0].delta
            reasoning = getattr(delta, "reasoning_content", None)
            if reasoning and request.reasoning_sink is not None:
                request.reasoning_sink(reasoning)
            token = getattr(delta, "content", None)
            if token:
                yield token
