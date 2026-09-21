from app.files.context import AttachmentRecord, build_attachment_context
from app.providers import ChatMessage, ChatRequest
from app.providers.anthropic import AnthropicProvider
from app.providers.gemini import GeminiProvider
from app.providers.openai_compatible import message_payload, OpenAICompatibleProvider
from app.providers.openrouter import OpenRouterProvider


def record(mime: str) -> AttachmentRecord:
    return AttachmentRecord(id=1, file_name="foto.png", mime_type=mime, storage_path="x", size_bytes=10)


def test_image_context_honest_when_no_vision():
    context = build_attachment_context([record("image/png")], vision_supported=False)
    assert "cannot see image content" in context
    assert "Do NOT invent" in context


def test_image_context_announces_attachment_when_vision():
    context = build_attachment_context([record("image/png")], vision_supported=True)
    assert "attached to this message" in context
    assert "cannot see" not in context


def test_openai_message_payload_with_and_without_images():
    plain = message_payload(ChatMessage(role="user", content="hola"))
    assert plain == {"role": "user", "content": "hola"}

    rich = message_payload(ChatMessage(role="user", content="mira", images=("data:image/png;base64,QUJD",)))
    assert rich["content"][0] == {"type": "text", "text": "mira"}
    assert rich["content"][1] == {"type": "image_url", "image_url": {"url": "data:image/png;base64,QUJD"}}


def test_anthropic_payload_encodes_images_as_blocks():
    provider = AnthropicProvider(api_key="k")
    payload = provider.build_payload(ChatRequest(
        model="claude-x",
        messages=[ChatMessage(role="user", content="mira", images=("data:image/png;base64,QUJD",))],
    ))
    blocks = payload["messages"][0]["content"]
    assert blocks[0] == {"type": "image", "source": {"type": "base64", "media_type": "image/png", "data": "QUJD"}}
    assert blocks[1] == {"type": "text", "text": "mira"}


def test_gemini_payload_encodes_images_as_inline_data():
    provider = GeminiProvider(api_key="k")
    payload = provider.build_payload(ChatRequest(
        model="gemini-x",
        messages=[ChatMessage(role="user", content="mira", images=("data:image/jpeg;base64,QUJD",))],
    ))
    parts = payload["contents"][0]["parts"]
    assert parts[0] == {"inline_data": {"mime_type": "image/jpeg", "data": "QUJD"}}
    assert parts[1] == {"text": "mira"}


def test_data_url_parsing():
    from app.providers.base import parse_data_url
    assert parse_data_url("data:image/png;base64,QUJD") == ("image/png", "QUJD")
    assert parse_data_url("https://x/img.png") is None
    assert parse_data_url("data:image/png;base64,") is None
