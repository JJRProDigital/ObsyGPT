import pytest
from fastapi import HTTPException
from urllib.error import HTTPError

from app.admin.routes import AgentFallbackPayload, detect_provider_models
from app.providers.registry import list_provider_models
from app.workflows.runtime import FallbackSpec


class FakeRequest:
    session = {"user_id": 1, "role": "admin"}


def test_list_provider_models_parses_openai_style_response(monkeypatch):
    class FakeResponse:
        def __enter__(self):
            return self

        def __exit__(self, exc_type, exc, traceback):
            return False

        def read(self):
            return b'{"data": [{"id": "gpt-test", "display_name": "GPT Test"}, {"id": "mini"}]}'

    def fake_urlopen(request, timeout=15):
        assert request.full_url.endswith("/models")
        assert request.headers["Authorization"] == "Bearer key-test"
        return FakeResponse()

    monkeypatch.setattr("app.providers.registry.urlopen", fake_urlopen)

    detected = list_provider_models("llamacpp", "key-test", "http://127.0.0.1:8080/v1")

    assert detected == [
        {"model_name": "gpt-test", "display_name": "GPT Test"},
        {"model_name": "mini", "display_name": "mini"},
    ]


def test_list_provider_models_requires_base_url():
    with pytest.raises(Exception):
        list_provider_models("openai_compatible", None, None)


def test_list_provider_models_anthropic_uses_x_api_key(monkeypatch):
    class FakeResponse:
        def __enter__(self):
            return self

        def __exit__(self, exc_type, exc, traceback):
            return False

        def read(self):
            return b'{"data": []}'

    captured = {}

    def fake_urlopen(request, timeout=15):
        captured["headers"] = dict(request.headers)
        return FakeResponse()

    monkeypatch.setattr("app.providers.registry.urlopen", fake_urlopen)

    list_provider_models("anthropic", "key-ant", "https://api.anthropic.com")

    header_keys = {key.lower() for key in captured["headers"]}
    assert any(key == "x-api-key" for key in header_keys)
    assert any(captured["headers"][key] == "key-ant" for key in captured["headers"] if key.lower() == "x-api-key")


def test_detect_provider_models_marks_registered_models(monkeypatch):
    monkeypatch.setattr("app.admin.routes.require_admin", lambda request: 1)
    monkeypatch.setattr(
        "app.admin.routes.fetch_one",
        lambda query, params: {"id": 6, "name": "llama.cpp", "provider_type": "llamacpp", "base_url": "http://127.0.0.1:8080/v1", "api_key_env": None, "enabled": True},
    )
    monkeypatch.setattr(
        "app.admin.routes.fetch_all",
        lambda query, params=(): [{"model_name": "Gemma-4-E2B"}],
    )
    monkeypatch.setattr(
        "app.admin.routes.list_provider_models",
        lambda provider_type, api_key, base_url: [{"model_name": "Gemma-4-E2B", "display_name": "Gemma"}, {"model_name": "new-model", "display_name": "New"}],
    )

    result = detect_provider_models(6, FakeRequest())

    assert result["models"][0]["already_registered"] is True
    assert result["models"][1]["already_registered"] is False


def test_detect_provider_models_maps_error_to_502(monkeypatch):
    monkeypatch.setattr("app.admin.routes.require_admin", lambda request: 1)
    monkeypatch.setattr(
        "app.admin.routes.fetch_one",
        lambda query, params: {"id": 6, "name": "llama.cpp", "provider_type": "llamacpp", "base_url": None, "api_key_env": None, "enabled": True},
    )
    monkeypatch.setattr(
        "app.admin.routes.list_provider_models",
        lambda provider_type, api_key, base_url: (_ for _ in ()).throw(ValueError("requires a base URL")),
    )

    with pytest.raises(HTTPException) as error:
        detect_provider_models(6, FakeRequest())

    assert error.value.status_code == 502


def test_agent_fallback_payload_validates_entries():
    payload = AgentFallbackPayload(fallbacks=[{"provider_id": 6, "model_id": 6}])

    assert payload.fallbacks == [{"provider_id": 6, "model_id": 6}]

    with pytest.raises(Exception):
        AgentFallbackPayload(fallbacks=[{"provider_id": "6"}])


def test_fallback_spec_carries_provider_config():
    fallback = FallbackSpec(provider_type="llamacpp", provider_base_url="http://127.0.0.1:8080/v1", provider_api_key_env=None, model="gemma")

    assert fallback.provider_type == "llamacpp"
    assert fallback.model == "gemma"


def test_list_provider_models_retries_v1_variant_on_404(monkeypatch):
    class FakeResponse:
        def __enter__(self):
            return self

        def __exit__(self, exc_type, exc, traceback):
            return False

        def read(self):
            return b'{"data": [{"id": "gemma"}]}'

    attempted = []

    def fake_urlopen(request, timeout=15):
        attempted.append(request.full_url)
        if request.full_url.endswith("/models") and not request.full_url.endswith("/v1/models"):
            raise HTTPError(request.full_url, 404, "Not Found", {}, None)
        return FakeResponse()

    monkeypatch.setattr("app.providers.registry.urlopen", fake_urlopen)

    detected = list_provider_models("llamacpp", None, "http://127.0.0.1:8080")

    assert detected == [{"model_name": "gemma", "display_name": "gemma"}]
    assert attempted == ["http://127.0.0.1:8080/models", "http://127.0.0.1:8080/v1/models"]


def test_list_provider_models_ollama_tags_fallback(monkeypatch):
    class FakeResponse:
        def __enter__(self):
            return self

        def __exit__(self, exc_type, exc, traceback):
            return False

        def read(self):
            return b'{"models": [{"name": "llama3.1:8b"}]}'

    attempted = []

    def fake_urlopen(request, timeout=15):
        attempted.append(request.full_url)
        if request.full_url.endswith("/api/tags"):
            return FakeResponse()
        raise HTTPError(request.full_url, 404, "Not Found", {}, None)

    monkeypatch.setattr("app.providers.registry.urlopen", fake_urlopen)

    detected = list_provider_models("ollama", None, "http://127.0.0.1:11434/v1")

    assert detected == [{"model_name": "llama3.1:8b", "display_name": "llama3.1:8b"}]
    assert attempted[-1] == "http://127.0.0.1:11434/api/tags"


def test_list_provider_models_gemini_strips_models_prefix(monkeypatch):
    class FakeResponse:
        def __enter__(self):
            return self

        def __exit__(self, exc_type, exc, traceback):
            return False

        def read(self):
            return b'{"models": [{"name": "models/gemini-1.5-pro"}]}'

    monkeypatch.setattr("app.providers.registry.urlopen", lambda request, timeout=15: FakeResponse())

    detected = list_provider_models("gemini", "key-g", "https://generativelanguage.googleapis.com")

    assert detected == [{"model_name": "gemini-1.5-pro", "display_name": "gemini-1.5-pro"}]


def test_workflow_runtime_falls_back_when_primary_fails():
    from app.agent.tools.base import ToolResult
    from app.providers import ChatMessage
    from app.workflows.runtime import AgentSpec, WorkflowSpec, WorkflowRuntime

    class FailingThenOkRegistry:
        def __init__(self):
            self.calls: list[str] = []

        def stream_chat_with_config(self, provider_type, request, api_key_env=None, base_url=None):
            self.calls.append(provider_type)
            if provider_type == "openrouter":
                raise RuntimeError("primary down")
            return iter(["respuesta del fallback"])

    registry = FailingThenOkRegistry()
    traces = type("FakeTraceStore", (), {
        "add_event": lambda self, *args, **kwargs: None,
        "add_tool_call": lambda self, *args, **kwargs: None,
        "add_source": lambda self, *args, **kwargs: None,
        "complete_run": lambda self, *args, **kwargs: None,
        "fail_run": lambda self, *args, **kwargs: None,
        "create_run": lambda self, *args, **kwargs: 1,
    })()

    agent = AgentSpec(
        id=1,
        name="Test",
        system_prompt="s",
        provider_type="openrouter",
        provider_base_url=None,
        provider_api_key_env="OPENROUTER_API_KEY",
        model="primary-model",
        temperature=0.7,
        fallbacks=[FallbackSpec(provider_type="llamacpp", provider_base_url=None, provider_api_key_env=None, model="gemma")],
    )
    runtime = WorkflowRuntime(provider_registry=registry, trace_store=traces, skill_registry=None)
    workflow = WorkflowSpec(id=None, name="wf", workflow_type="single_agent", agents=[agent])

    output = "".join(runtime.stream_workflow(1, workflow, [ChatMessage(role="user", content="hola")]))

    assert output == "respuesta del fallback"
    assert registry.calls == ["openrouter", "llamacpp"]
