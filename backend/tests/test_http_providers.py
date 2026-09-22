import json
from io import BytesIO

from app.providers import ChatMessage, ChatRequest
from app.providers.anthropic import AnthropicProvider
from app.providers.gemini import GeminiProvider


class FakeResponse:
    def __init__(self, payload: dict):
        self.body = BytesIO(json.dumps(payload).encode("utf-8"))

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc, traceback):
        return False

    def read(self, limit: int = -1):
        return self.body.read() if limit < 0 else self.body.read(limit)


def test_anthropic_provider_posts_messages_payload(monkeypatch):
    captured = {}

    def fake_urlopen(request, timeout):
        captured["url"] = request.full_url
        captured["headers"] = dict(request.header_items())
        captured["body"] = json.loads(request.data.decode("utf-8"))
        return FakeResponse({"content": [{"type": "text", "text": "anthropic answer"}]})

    monkeypatch.setattr("app.providers.anthropic.urlopen", fake_urlopen)

    provider = AnthropicProvider(api_key="anthropic-key", base_url="https://api.anthropic.com")
    request = ChatRequest(
        model="claude-3-5-sonnet-latest",
        messages=[
            ChatMessage(role="system", content="Be concise."),
            ChatMessage(role="user", content="Hello"),
        ],
        temperature=0.3,
    )

    assert "".join(provider.stream_chat(request)) == "anthropic answer"
    assert captured["url"] == "https://api.anthropic.com/v1/messages"
    assert captured["headers"]["X-api-key"] == "anthropic-key"
    assert captured["headers"]["Anthropic-version"] == "2023-06-01"
    assert captured["body"]["system"] == "Be concise."
    assert captured["body"]["messages"] == [{"role": "user", "content": "Hello"}]
    assert captured["body"]["model"] == "claude-3-5-sonnet-latest"


def test_gemini_provider_posts_generate_content_payload(monkeypatch):
    captured = {}

    def fake_urlopen(request, timeout):
        captured["url"] = request.full_url
        captured["headers"] = dict(request.header_items())
        captured["body"] = json.loads(request.data.decode("utf-8"))
        return FakeResponse({"candidates": [{"content": {"parts": [{"text": "gemini answer"}]}}]})

    monkeypatch.setattr("app.providers.gemini.urlopen", fake_urlopen)

    provider = GeminiProvider(api_key="gemini-key", base_url="https://generativelanguage.googleapis.com")
    request = ChatRequest(
        model="gemini-1.5-pro",
        messages=[
            ChatMessage(role="system", content="Be precise."),
            ChatMessage(role="user", content="Hello"),
            ChatMessage(role="assistant", content="Hi"),
        ],
        temperature=0.4,
    )

    assert "".join(provider.stream_chat(request)) == "gemini answer"
    assert captured["url"] == "https://generativelanguage.googleapis.com/v1beta/models/gemini-1.5-pro:streamGenerateContent?alt=sse&key=gemini-key"
    assert captured["headers"]["Content-type"] == "application/json"
    assert captured["body"]["systemInstruction"] == {"parts": [{"text": "Be precise."}]}
    assert captured["body"]["contents"] == [
        {"role": "user", "parts": [{"text": "Hello"}]},
        {"role": "model", "parts": [{"text": "Hi"}]},
    ]


class FakeSSEResponse:
    """Response whose body is SSE-framed (data: lines), like the real APIs."""

    def __init__(self, events: list[dict]):
        lines = []
        for event in events:
            lines.append("data: " + json.dumps(event) + "\n")
        lines.append("data: [DONE]\n\n")
        self.body = BytesIO("".join(lines).encode("utf-8"))

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc, traceback):
        return False

    def read(self, limit: int = -1):
        return self.body.read() if limit < 0 else self.body.read(limit)

    def __iter__(self):
        return iter(self.body)


def test_anthropic_streams_text_deltas_incrementally(monkeypatch):
    events = [
        {"type": "message_start"},
        {"type": "content_block_delta", "delta": {"type": "text_delta", "text": "Hola "}},
        {"type": "content_block_delta", "delta": {"type": "text_delta", "text": "mundo"}},
    ]
    monkeypatch.setattr("app.providers.anthropic.urlopen", lambda request, timeout: FakeSSEResponse(events))

    provider = AnthropicProvider(api_key="k")
    request = ChatRequest(model="claude-3-5-sonnet-latest", messages=[ChatMessage(role="user", content="hi")], temperature=0.2)

    tokens = list(provider.stream_chat(request))
    assert tokens == ["Hola ", "mundo"]


def test_anthropic_stream_error_event_raises(monkeypatch):
    events = [{"type": "error", "error": {"message": "overloaded"}}]
    monkeypatch.setattr("app.providers.anthropic.urlopen", lambda request, timeout: FakeSSEResponse(events))

    provider = AnthropicProvider(api_key="k")
    request = ChatRequest(model="claude-3-5-sonnet-latest", messages=[ChatMessage(role="user", content="hi")], temperature=0.2)

    import pytest

    with pytest.raises(RuntimeError, match="overloaded"):
        list(provider.stream_chat(request))


def test_gemini_streams_sse_chunks_incrementally(monkeypatch):
    events = [
        {"candidates": [{"content": {"parts": [{"text": "respuesta "}]}}]},
        {"candidates": [{"content": {"parts": [{"text": "parcial"}]}}]},
    ]
    monkeypatch.setattr("app.providers.gemini.urlopen", lambda request, timeout: FakeSSEResponse(events))

    provider = GeminiProvider(api_key="k")
    request = ChatRequest(model="gemini-1.5-pro", messages=[ChatMessage(role="user", content="hi")], temperature=0.2)

    tokens = list(provider.stream_chat(request))
    assert tokens == ["respuesta ", "parcial"]
