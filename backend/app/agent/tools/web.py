"""Web fetch and web search tools reusing the existing skills."""

from .base import ToolResult, ToolSpec


def _default_fetcher(payload: dict) -> dict:
    from ...skills.internet import ReadUrlSkill

    return ReadUrlSkill().run(payload)


def _default_searcher(payload: dict) -> dict:
    from ...skills.internet import WebSearchSkill

    return WebSearchSkill().run(payload)


class WebFetchTool:
    spec = ToolSpec(
        name="web_fetch",
        description="Fetches a public http(s) URL and returns its cleaned text content.",
        parameters='{"url": "https://example.com"}',
        permission="safe",
    )

    def __init__(self, fetcher=None):
        self.fetcher = fetcher or _default_fetcher

    def run(self, args: dict) -> ToolResult:
        url = str(args.get("url", "")).strip()
        if not url:
            return ToolResult(ok=False, output="Missing required argument: url")
        try:
            result = self.fetcher({"url": url})
        except Exception as error:  # noqa: BLE001
            return ToolResult(ok=False, output=f"web_fetch failed: {error}")
        return ToolResult(ok=True, output=f"Title: {result.get('title', url)}\nURL: {result.get('url', url)}\n\n{result.get('content', '')}")


class WebSearchTool:
    spec = ToolSpec(
        name="web_search",
        description="Searches the web (DuckDuckGo) and returns the top results with title, URL and snippet.",
        parameters='{"query": "noticias inteligencia artificial hoy", "limit": 5}',
        permission="safe",
    )

    def __init__(self, searcher=None):
        self.searcher = searcher or _default_searcher

    def run(self, args: dict) -> ToolResult:
        query = str(args.get("query", "")).strip()
        if not query:
            return ToolResult(ok=False, output="Missing required argument: query")
        try:
            limit = int(args.get("limit", 5))
        except (TypeError, ValueError):
            limit = 5
        try:
            result = self.searcher({"query": query, "limit": limit})
        except Exception as error:  # noqa: BLE001
            return ToolResult(ok=False, output=f"web_search failed: {error}")
        lines = [f"Web search results for: {result.get('query', query)}"]
        for index, item in enumerate(result.get("results", []), start=1):
            lines.append(f"{index}. {item.get('title', '')}\n   URL: {item.get('url', '')}\n   {item.get('snippet', '')}")
        return ToolResult(ok=True, output="\n".join(lines))


def _default_news_searcher(payload: dict) -> list:
    from ...skills.internet import bing_news_client

    return bing_news_client(str(payload.get("query", "")), int(payload.get("limit", 5)))


class NewsSearchTool:
    spec = ToolSpec(
        name="news_search",
        description=(
            "Searches recent NEWS articles (Bing News) with publication dates. "
            "Use this instead of web_search when the user asks for news, today's headlines or current events."
        ),
        parameters='{"query": "inteligencia artificial", "limit": 5}',
        permission="safe",
    )

    def __init__(self, searcher=None):
        self.searcher = searcher or _default_news_searcher

    def run(self, args: dict) -> ToolResult:
        query = str(args.get("query", "")).strip()
        if not query:
            return ToolResult(ok=False, output="Missing required argument: query")
        try:
            limit = int(args.get("limit", 5))
        except (TypeError, ValueError):
            limit = 5
        try:
            results = self.searcher({"query": query, "limit": limit})
        except Exception as error:  # noqa: BLE001
            return ToolResult(ok=False, output=f"news_search failed: {error}")
        lines = [f"Recent news for: {query}"]
        for index, item in enumerate(results, start=1):
            lines.append(
                f"{index}. {item.title}\n   URL: {item.url}\n   Published: {item.published}\n   {item.snippet}"
            )
        return ToolResult(ok=True, output="\n".join(lines))
