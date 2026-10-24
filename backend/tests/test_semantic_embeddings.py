import json
from unittest.mock import patch

import pytest

from app.memory.semantic import embeddings as emb


class FakeResponse:
    def __init__(self, payload):
        self._payload = payload

    def read(self):
        return json.dumps(self._payload).encode()

    def __enter__(self):
        return self

    def __exit__(self, *args):
        return False


def test_endpoint_embed_passages_posts_and_parses():
    service = emb.EmbeddingService(mode="endpoint", base_url="http://emb.local/v1", model="text-embed-x", api_key_env="EMB_KEY")
    payload = {"data": [{"embedding": [0.0] * 384}, {"embedding": [0.5] * 384}]}
    with patch.object(emb, "urlopen", return_value=FakeResponse(payload)) as fake_open:
        vectors = service.embed_passages(["hola", "mundo"])
    assert len(vectors) == 2 and len(vectors[0]) == 384
    request = fake_open.call_args[0][0]
    body = json.loads(request.data)
    assert body["input"] == ["hola", "mundo"] and body["model"] == "text-embed-x"
    assert "Authorization" not in dict(request.header_items())


def test_endpoint_rejects_wrong_dimension():
    service = emb.EmbeddingService(mode="endpoint", base_url="http://emb.local/v1", model="x")
    with patch.object(emb, "urlopen", return_value=FakeResponse({"data": [{"embedding": [0.0] * 100}]})):
        with pytest.raises(emb.EmbeddingError):
            service.embed_passages(["hola"])


def test_embed_query_uses_short_timeout_and_background_keeps_default():
    service = emb.EmbeddingService(mode="endpoint", base_url="http://emb.local/v1", model="text-embed-x")
    payload = {"data": [{"embedding": [0.0] * 384}]}
    with patch.object(emb, "urlopen", return_value=FakeResponse(payload)) as fake_open:
        service.embed_query("hola")
    assert fake_open.call_args.kwargs["timeout"] == emb.QUERY_TIMEOUT
    with patch.object(emb, "urlopen", return_value=FakeResponse(payload)) as fake_open:
        service.embed_passages(["hola", "mundo"])
    assert fake_open.call_args.kwargs["timeout"] == emb.INDEX_TIMEOUT


def test_local_prefixes_e5_query_and_passage(monkeypatch):
    captured = {}

    def fake_embed(texts):
        captured["texts"] = list(texts)
        return [[0.1] * 384 for _ in texts]

    monkeypatch.setattr(emb, "_embed_with_local_model", fake_embed)
    service = emb.EmbeddingService(mode="local")
    service.embed_query("qué hablamos de postgres")
    assert captured["texts"] == ["query: qué hablamos de postgres"]
    service.embed_passages(["texto uno"])
    assert captured["texts"] == ["passage: texto uno"]


def test_get_embedding_service_reads_settings(monkeypatch):
    monkeypatch.setattr(emb, "load_embedding_config", lambda: {"mode": "endpoint", "base_url": "http://e/v1", "model": "m", "api_key_env": "K"})
    service = emb.get_embedding_service()
    assert service.mode == "endpoint" and service.model == "m" and service.base_url == "http://e/v1"
