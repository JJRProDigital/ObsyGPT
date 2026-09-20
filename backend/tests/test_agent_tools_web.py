from app.agent.tools.base import ToolRegistry
from app.agent.tools.web import WebFetchTool


class FakeFetch:
    def __init__(self, fail: bool = False):
        self.fail = fail
        self.calls: list[dict] = []

    def __call__(self, payload: dict) -> dict:
        self.calls.append(payload)
        if self.fail:
            raise ValueError("boom")
        return {"url": payload["url"], "title": "Example", "content": "contenido limpio"}


def test_web_fetch_returns_clean_content():
    fetch = FakeFetch()
    registry = ToolRegistry()
    registry.register(WebFetchTool(fetcher=fetch))

    result = registry.run("web_fetch", {"url": "https://example.com"})

    assert result.ok
    assert "Example" in result.output
    assert "contenido limpio" in result.output
    assert fetch.calls == [{"url": "https://example.com"}]


def test_web_fetch_is_safe_permission():
    tool = WebFetchTool(fetcher=FakeFetch())

    assert tool.spec.permission == "safe"
    assert tool.spec.name == "web_fetch"


def test_web_fetch_failure_returns_clean_error():
    registry = ToolRegistry()
    registry.register(WebFetchTool(fetcher=FakeFetch(fail=True)))

    result = registry.run("web_fetch", {"url": "https://example.com"})

    assert not result.ok
    assert "boom" in result.output


def test_web_fetch_rejects_missing_url():
    registry = ToolRegistry()
    registry.register(WebFetchTool(fetcher=FakeFetch()))

    result = registry.run("web_fetch", {})

    assert not result.ok
    assert "url" in result.output.lower()


class FakeUrlOpenResponse:
    def __init__(self, body: bytes):
        self.body = body

    def read(self) -> bytes:
        return self.body

    def __enter__(self):
        return self

    def __exit__(self, *args):
        return False


def test_web_fetch_default_fetcher_import_and_run(monkeypatch):
    """Regression: the default fetcher must import app.skills.internet (once broke via app.agent.skills)."""
    html = b"<html><head><title>Portfolio</title></head><body><p>Hola mundo</p></body></html>"
    captured = {}

    def fake_urlopen(request, timeout):
        captured["url"] = request.full_url
        return FakeUrlOpenResponse(html)

    monkeypatch.setattr("app.skills.internet.urlopen", fake_urlopen)

    result = WebFetchTool().run({"url": "https://example.com"})

    assert result.ok
    assert captured["url"] == "https://example.com"
    assert "Portfolio" in result.output
    assert "Hola mundo" in result.output
