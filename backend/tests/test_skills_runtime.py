from io import BytesIO

import pytest

from app.skills.internet import ReadUrlSkill, SearchResult, WebSearchSkill
from app.skills.runtime import SkillRegistry


class FakeResponse:
    def __init__(self, body: bytes, content_type: str = "text/html; charset=utf-8"):
        self.body = BytesIO(body)
        self.headers = {"Content-Type": content_type}

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc, traceback):
        return False

    def read(self, limit: int = -1):
        return self.body.read() if limit < 0 else self.body.read(limit)


def test_read_url_skill_extracts_title_and_clean_text(monkeypatch):
    html = b"""
    <html>
      <head><title>Example Page</title><script>bad()</script></head>
      <body><nav>menu</nav><h1>Hello</h1><p>This is useful text.</p></body>
    </html>
    """

    monkeypatch.setattr("app.skills.internet.urlopen", lambda request, timeout: FakeResponse(html))

    result = ReadUrlSkill().run({"url": "https://example.com"})

    assert result["url"] == "https://example.com"
    assert result["title"] == "Example Page"
    assert "Hello" in result["content"]
    assert "This is useful text." in result["content"]
    assert "bad()" not in result["content"]


def test_read_url_skill_rejects_non_http_urls():
    with pytest.raises(ValueError, match="Only http and https URLs are supported"):
        ReadUrlSkill().run({"url": "file:///etc/passwd"})


def test_web_search_skill_uses_injected_search_client():
    def search_client(query: str, limit: int):
        assert query == "multi agent systems"
        assert limit == 2
        return [SearchResult(title="One", url="https://example.com/one", snippet="First")]

    result = WebSearchSkill(search_client=search_client).run({"query": "multi agent systems", "limit": 2})

    assert result["results"] == [{"title": "One", "url": "https://example.com/one", "snippet": "First"}]


def test_skill_registry_exposes_initial_internet_skills():
    registry = SkillRegistry()

    assert set(registry.skill_names()) >= {"read_url", "web_search"}
    assert registry.get("read_url").name == "read_url"
