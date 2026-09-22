from app.agent.tools.web import WebSearchTool
from app.skills.internet import SearchResult, WebSearchSkill, duckduckgo_html_client

DDG_HTML_FIXTURE = """
<div class="links_main links_deep result__body">
  <h2 class="result__title">
    <a rel="nofollow" class="result__a" href="//duckduckgo.com/l/?uddg=https%3A%2F%2Fwww.reuters.com%2Ftechnology%2Fai-news&amp;rut=abc123">Reuters &amp; AI <b>news</b> today</a>
  </h2>
  <a class="result__snippet" href="//duckduckgo.com/l/?uddg=https%3A%2F%2Fwww.reuters.com%2Ftechnology%2Fai-news">Latest artificial intelligence coverage from Reuters.</a>
</div>
<div class="links_main links_deep result__body">
  <h2 class="result__title">
    <a rel="nofollow" class="result__a" href="https://www.bbc.com/news/technology">BBC technology coverage</a>
  </h2>
  <a class="result__snippet" href="https://www.bbc.com/news/technology">AI and tech headlines from the BBC.</a>
</div>
"""


def test_web_search_tool_returns_formatted_results():
    tool = WebSearchTool(searcher=lambda payload: {
        "query": payload["query"],
        "results": [
            {"title": "Noticia IA", "url": "https://example.com/ia", "snippet": "Resumen de la noticia."},
        ],
    })

    result = tool.run({"query": "noticias ia"})

    assert result.ok
    assert "1. Noticia IA" in result.output
    assert "https://example.com/ia" in result.output


def test_web_search_tool_requires_query():
    result = WebSearchTool().run({})

    assert not result.ok
    assert "query" in result.output


def test_web_search_tool_reports_failure():
    def broken_searcher(payload):
        raise RuntimeError("blocked")

    result = WebSearchTool(searcher=broken_searcher).run({"query": "x"})

    assert not result.ok
    assert "web_search failed" in result.output


def test_duckduckgo_html_client_parses_results(monkeypatch):
    from app.skills import internet

    class FakeResponse:
        def read(self):
            return DDG_HTML_FIXTURE.encode("utf-8")

    monkeypatch.setattr(internet, "urlopen", lambda request, timeout: FakeResponse())

    results = duckduckgo_html_client("noticias ia", 5)

    assert len(results) == 2
    assert results[0].url == "https://www.reuters.com/technology/ai-news"
    assert results[0].title == "Reuters & AI news today"
    assert "Reuters" in results[0].snippet
    assert results[1].url == "https://www.bbc.com/news/technology"


def test_duckduckgo_html_client_raises_when_blocked(monkeypatch):
    from app.skills import internet

    class EmptyResponse:
        def read(self):
            return b"<html><body>403 forbidden</body></html>"

    monkeypatch.setattr(internet, "urlopen", lambda request, timeout: EmptyResponse())

    try:
        duckduckgo_html_client("x", 5)
        raised = False
    except ValueError as error:
        raised = "no parsable results" in str(error)
    assert raised


def test_web_search_skill_falls_back_to_stub_when_blocked(monkeypatch):
    from app.skills import internet

    class EmptyResponse:
        def read(self):
            return b"<html>blocked</html>"

    monkeypatch.setattr(internet, "urlopen", lambda request, timeout: EmptyResponse())
    skill = WebSearchSkill()

    result = skill.run({"query": "noticias ia", "limit": 3})

    assert result["query"] == "noticias ia"
    assert len(result["results"]) == 1
    assert result["results"][0]["url"].startswith("https://duckduckgo.com/?q=")


def test_search_result_dataclass_shape():
    item = SearchResult(title="t", url="https://x", snippet="s")

    assert (item.title, item.url, item.snippet) == ("t", "https://x", "s")


BING_RSS_FIXTURE = """<?xml version="1.0" encoding="utf-8" ?>
<rss version="2.0"><channel><title>q - BingNoticias</title>
<item>
  <title><![CDATA[Del apocalipsis al consenso global: ¿a quién interesa que la IA sea segura?]]></title>
  <link>http://www.bing.com/news/apiclick.aspx?ref=FexRss&amp;tid=abc&amp;url=https%3a%2f%2fwww.rtve.es%2fnoticias%2f20260920%2fia-segura%2f17231504.shtml&amp;c=99&amp;mkt=es-es</link>
  <pubDate>Sun, 20 Sep 2026 01:03:00 GMT</pubDate>
  <description><![CDATA[Europa tambi&eacute;n ha hablado. <a href="x">Von der Leyen</a> compareci&oacute; este jueves.]]></description>
</item>
<item>
  <title>Argentina quedó última en un ranking global de adopción de IA</title>
  <link>https://www.c5n.com/tecnologia/ranking-ia-n249425</link>
  <pubDate>Sun, 20 Sep 2026 14:34:00 GMT</pubDate>
  <description>La banca de inversión Goldman Sachs analizó 28 economías.</description>
</item>
</channel></rss>
"""


def test_bing_news_client_parses_items_and_decodes_links(monkeypatch):
    from app.skills import internet

    class FakeResponse:
        def read(self):
            return BING_RSS_FIXTURE.encode("utf-8")

    monkeypatch.setattr(internet, "urlopen", lambda request, timeout: FakeResponse())

    results = internet.bing_news_client("inteligencia artificial", 5)

    assert len(results) == 2
    assert results[0].url == "https://www.rtve.es/noticias/20260920/ia-segura/17231504.shtml"
    assert "apocalipsis" in results[0].title
    assert results[0].published == "Sun, 20 Sep 2026 01:03:00 GMT"
    assert "Europa también ha hablado" in results[0].snippet
    assert "<a href" not in results[0].snippet
    assert results[1].url == "https://www.c5n.com/tecnologia/ranking-ia-n249425"


def test_news_search_tool_formats_results_with_dates():
    from app.agent.tools.web import NewsSearchTool
    from app.skills.internet import NewsResult

    tool = NewsSearchTool(searcher=lambda payload: [
        NewsResult(title="Noticia IA", url="https://rtve.es/x", snippet="Resumen.", published="Sun, 20 Sep 2026"),
    ])

    result = tool.run({"query": "ia"})

    assert result.ok
    assert "1. Noticia IA" in result.output
    assert "https://rtve.es/x" in result.output
    assert "Published: Sun, 20 Sep 2026" in result.output


def test_news_search_tool_requires_query():
    from app.agent.tools.web import NewsSearchTool

    result = NewsSearchTool().run({})

    assert not result.ok
    assert "query" in result.output


def test_news_search_tool_reports_failure():
    from app.agent.tools.web import NewsSearchTool

    def broken(payload):
        raise RuntimeError("blocked")

    result = NewsSearchTool(searcher=broken).run({"query": "x"})

    assert not result.ok
    assert "news_search failed" in result.output
