import pytest

from app.providers import ChatMessage, ChatRequest
from app.providers.registry import PROVIDER_DEFINITIONS, build_provider


def test_provider_definitions_include_requested_provider_types():
    provider_types = {definition.provider_type for definition in PROVIDER_DEFINITIONS}

    assert provider_types == {
        "openrouter",
        "openai",
        "anthropic",
        "gemini",
        "ollama",
        "llamacpp",
        "openai_compatible",
    }


def test_provider_definitions_expose_capabilities():
    openai = next(definition for definition in PROVIDER_DEFINITIONS if definition.provider_type == "openai")
    ollama = next(definition for definition in PROVIDER_DEFINITIONS if definition.provider_type == "ollama")

    assert openai.supports_text is True
    assert openai.supports_streaming is True
    assert openai.supports_vision is True
    assert openai.supports_tools is True
    assert ollama.default_base_url == "http://127.0.0.1:11434/v1"
    assert ollama.api_key_env is None


def test_build_provider_rejects_unknown_provider_type():
    with pytest.raises(ValueError, match="Provider type is not supported: unknown"):
        build_provider("unknown", api_key="key", base_url=None)


def test_build_provider_creates_openai_compatible_provider():
    provider = build_provider(
        "openai_compatible",
        api_key="test-key",
        base_url="http://localhost:8080/v1",
    )

    assert provider.provider_type == "openai_compatible"


def test_build_provider_creates_anthropic_and_gemini_providers():
    anthropic = build_provider("anthropic", api_key="anthropic-key", base_url=None)
    gemini = build_provider("gemini", api_key="gemini-key", base_url=None)

    assert anthropic.provider_type == "anthropic"
    assert gemini.provider_type == "gemini"


def test_provider_registry_stream_chat_with_config_uses_env_key(monkeypatch):
    from app.providers.registry import ProviderRegistry

    captured = {}

    class FakeProvider:
        provider_type = "openai_compatible"

        def stream_chat(self, request):
            yield "ok"

    def fake_build_provider(provider_type, api_key, base_url):
        captured["provider_type"] = provider_type
        captured["api_key"] = api_key
        captured["base_url"] = base_url
        return FakeProvider()

    monkeypatch.setenv("LOCAL_API_KEY", "secret")
    monkeypatch.setattr("app.providers.registry.build_provider", fake_build_provider)

    registry = ProviderRegistry(include_defaults=False)
    result = "".join(
        registry.stream_chat_with_config(
            "openai_compatible",
            ChatRequest(model="local", messages=[ChatMessage(role="user", content="hi")]),
            api_key_env="LOCAL_API_KEY",
            base_url="http://127.0.0.1:8080/v1",
        )
    )

    assert result == "ok"
    assert captured == {
        "provider_type": "openai_compatible",
        "api_key": "secret",
        "base_url": "http://127.0.0.1:8080/v1",
    }
