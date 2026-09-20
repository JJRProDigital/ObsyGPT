from collections.abc import Iterator
import json
import os
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

from ..config import get_settings
from .base import AIProvider, ChatRequest, ProviderDefinition
from .anthropic import AnthropicProvider
from .gemini import GeminiProvider
from .openai_compatible import OpenAICompatibleProvider
from .openrouter import OpenRouterProvider
from .unsupported import UnsupportedProvider


PROVIDER_DEFINITIONS = [
    ProviderDefinition(
        provider_type="openrouter",
        display_name="OpenRouter",
        default_base_url="https://openrouter.ai/api/v1",
        api_key_env="OPENROUTER_API_KEY",
        supports_vision=True,
        supports_tools=True,
        supports_json=True,
    ),
    ProviderDefinition(
        provider_type="openai",
        display_name="OpenAI",
        default_base_url="https://api.openai.com/v1",
        api_key_env="OPENAI_API_KEY",
        supports_vision=True,
        supports_audio=True,
        supports_tools=True,
        supports_json=True,
    ),
    ProviderDefinition(
        provider_type="anthropic",
        display_name="Anthropic",
        default_base_url="https://api.anthropic.com",
        api_key_env="ANTHROPIC_API_KEY",
        supports_vision=True,
        supports_tools=True,
    ),
    ProviderDefinition(
        provider_type="gemini",
        display_name="Gemini",
        default_base_url="https://generativelanguage.googleapis.com",
        api_key_env="GEMINI_API_KEY",
        supports_vision=True,
        supports_audio=True,
        supports_tools=True,
        supports_json=True,
    ),
    ProviderDefinition(
        provider_type="ollama",
        display_name="Ollama",
        default_base_url="http://127.0.0.1:11434/v1",
        api_key_env=None,
        supports_vision=True,
        supports_json=True,
    ),
    ProviderDefinition(
        provider_type="llamacpp",
        display_name="llama.cpp",
        default_base_url="http://127.0.0.1:8080/v1",
        api_key_env=None,
        supports_json=True,
    ),
    ProviderDefinition(
        provider_type="openai_compatible",
        display_name="OpenAI-compatible",
        default_base_url=None,
        api_key_env=None,
        supports_vision=True,
        supports_tools=True,
        supports_json=True,
    ),
]


PROVIDER_TYPES = {definition.provider_type for definition in PROVIDER_DEFINITIONS}


def get_provider_definition(provider_type: str) -> ProviderDefinition:
    for definition in PROVIDER_DEFINITIONS:
        if definition.provider_type == provider_type:
            return definition
    raise ValueError(f"Provider type is not supported: {provider_type}")


def build_provider(provider_type: str, api_key: str | None, base_url: str | None) -> AIProvider:
    definition = get_provider_definition(provider_type)
    resolved_base_url = base_url or definition.default_base_url
    resolved_api_key = api_key or "not-needed"

    if provider_type == "openrouter":
        if not api_key:
            raise ValueError("OpenRouter requires an API key.")
        return OpenRouterProvider(api_key=api_key, base_url=resolved_base_url or "https://openrouter.ai/api/v1")

    if provider_type in {"openai", "ollama", "llamacpp", "openai_compatible"}:
        if not resolved_base_url:
            raise ValueError(f"{definition.display_name} requires a base URL.")
        return OpenAICompatibleProvider(provider_type, resolved_api_key, resolved_base_url)

    if provider_type == "anthropic":
        if not api_key:
            raise ValueError("Anthropic requires an API key.")
        return AnthropicProvider(api_key=api_key, base_url=resolved_base_url or "https://api.anthropic.com")

    if provider_type == "gemini":
        if not api_key:
            raise ValueError("Gemini requires an API key.")
        return GeminiProvider(api_key=api_key, base_url=resolved_base_url or "https://generativelanguage.googleapis.com")

    return UnsupportedProvider(
        provider_type,
        f"{definition.display_name} is configurable in ObsyGPT, but its direct adapter is not enabled in this build yet.",
    )


def _model_url_candidates(provider_type: str, resolved_base_url: str) -> list[str]:
    base = resolved_base_url.rstrip("/")
    root = base[: -len("/v1")] if base.endswith("/v1") else base

    if provider_type == "gemini":
        return [f"{root}/v1beta/models"]
    if provider_type == "anthropic":
        return [f"{root}/v1/models"]

    candidates = [f"{base}/models"]
    if not base.endswith("/v1"):
        candidates.append(f"{base}/v1/models")
    if provider_type == "ollama":
        candidates.append(f"{root}/api/tags")
    return list(dict.fromkeys(candidates))


def _build_model_headers(provider_type: str, api_key: str | None) -> dict[str, str]:
    headers = {"User-Agent": "ObsyGPT/1.0"}
    if not api_key:
        return headers
    if provider_type == "anthropic":
        headers["x-api-key"] = api_key
        headers["anthropic-version"] = "2023-06-01"
    else:
        headers["Authorization"] = f"Bearer {api_key}"
    return headers


def _parse_model_payload(provider_type: str, body: dict) -> list[dict]:
    raw_models = body.get("data") or body.get("models") or []
    detected = []
    for item in raw_models:
        if not isinstance(item, dict):
            continue
        model_id = str(item.get("id") or item.get("name") or item.get("model") or "").strip()
        if provider_type == "gemini" and model_id.startswith("models/"):
            model_id = model_id[len("models/"):]
        if not model_id:
            continue
        detected.append({"model_name": model_id, "display_name": item.get("display_name") or item.get("title") or model_id})
    return detected


def list_provider_models(provider_type: str, api_key: str | None, base_url: str | None) -> list[dict]:
    """Detects models from a provider's /models endpoint, retrying common URL variants."""
    definition = get_provider_definition(provider_type)
    resolved_base_url = (base_url or definition.default_base_url or "").rstrip("/")
    if not resolved_base_url:
        raise ValueError(f"{definition.display_name} requires a base URL to detect models.")

    headers = _build_model_headers(provider_type, api_key)
    candidates = _model_url_candidates(provider_type, resolved_base_url)

    body: dict | None = None
    last_error: Exception | None = None
    for index, models_url in enumerate(candidates):
        final_url = f"{models_url}?key={api_key}" if provider_type == "gemini" and api_key else models_url
        try:
            request = Request(final_url, headers=headers)
            with urlopen(request, timeout=15) as response:
                body = json.loads(response.read().decode("utf-8"))
            break
        except HTTPError as error:
            last_error = error
            if error.code in {404, 405} and index < len(candidates) - 1:
                continue
            raise
        except URLError as error:
            last_error = error
            if index < len(candidates) - 1:
                continue
            raise

    if body is None:
        raise last_error or ValueError(f"{definition.display_name} model detection failed.")

    return _parse_model_payload(provider_type, body)


class ProviderRegistry:
    def __init__(self, include_defaults: bool = True):
        self.providers: dict[str, AIProvider] = {}

        if not include_defaults:
            return

        settings = get_settings()
        self.providers["openrouter"] = build_provider("openrouter", settings.openrouter_api_key, None)

        for definition in PROVIDER_DEFINITIONS:
            if definition.provider_type == "openrouter":
                continue
            api_key = os.getenv(definition.api_key_env) if definition.api_key_env else None
            if definition.default_base_url and (api_key or definition.api_key_env is None):
                self.providers[definition.provider_type] = build_provider(
                    definition.provider_type,
                    api_key,
                    definition.default_base_url,
                )

    def stream_chat(self, provider_type: str, request: ChatRequest) -> Iterator[str]:
        provider = self.providers.get(provider_type)
        if not provider:
            raise ValueError(f"Provider is not configured: {provider_type}")
        return provider.stream_chat(request)

    def stream_chat_with_config(
        self,
        provider_type: str,
        request: ChatRequest,
        api_key_env: str | None = None,
        base_url: str | None = None,
    ) -> Iterator[str]:
        api_key = os.getenv(api_key_env) if api_key_env else None
        cache_key = f"{provider_type}:{api_key_env or ''}:{base_url or ''}"

        provider = self.providers.get(cache_key)
        if not provider:
            provider = build_provider(provider_type, api_key, base_url)
            self.providers[cache_key] = provider

        return provider.stream_chat(request)
