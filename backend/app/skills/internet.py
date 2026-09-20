import re
from dataclasses import asdict, dataclass
from html.parser import HTMLParser
from typing import Callable
from urllib.parse import quote_plus, urlparse
from urllib.request import Request, urlopen


@dataclass(frozen=True)
class SearchResult:
    title: str
    url: str
    snippet: str


class CleanTextParser(HTMLParser):
    def __init__(self):
        super().__init__()
        self.parts: list[str] = []
        self.title_parts: list[str] = []
        self.skip_depth = 0
        self.in_title = False

    def handle_starttag(self, tag: str, attrs):  # noqa: ANN001
        if tag in {"script", "style", "noscript", "svg"}:
            self.skip_depth += 1
        if tag == "title":
            self.in_title = True

    def handle_endtag(self, tag: str):
        if tag in {"script", "style", "noscript", "svg"} and self.skip_depth:
            self.skip_depth -= 1
        if tag == "title":
            self.in_title = False

    def handle_data(self, data: str):
        text = data.strip()
        if not text:
            return
        if self.in_title:
            self.title_parts.append(text)
        if self.skip_depth == 0 and not self.in_title:
            self.parts.append(text)

    @property
    def title(self) -> str:
        return normalize_space(" ".join(self.title_parts))

    @property
    def content(self) -> str:
        return normalize_space(" ".join(self.parts))


def normalize_space(value: str) -> str:
    return re.sub(r"\s+", " ", value).strip()


class ReadUrlSkill:
    name = "read_url"

    def run(self, payload: dict) -> dict:
        url = str(payload.get("url", "")).strip()
        parsed = urlparse(url)

        if parsed.scheme not in {"http", "https"}:
            raise ValueError("Only http and https URLs are supported.")

        request = Request(url, headers={"User-Agent": "ObsyGPT/1.0"})

        with urlopen(request, timeout=20) as response:
            body = response.read()

        parser = CleanTextParser()
        parser.feed(body.decode("utf-8", errors="ignore"))

        return {
            "url": url,
            "title": parser.title or url,
            "content": parser.content[:12000],
        }


class WebSearchSkill:
    name = "web_search"

    def __init__(self, search_client: Callable[[str, int], list[SearchResult]] | None = None):
        self.search_client = search_client or self.default_search_client

    def run(self, payload: dict) -> dict:
        query = str(payload.get("query", "")).strip()
        limit = int(payload.get("limit", 5))

        if not query:
            raise ValueError("Search query is required.")

        limit = max(1, min(limit, 10))
        results = self.search_client(query, limit)

        return {"query": query, "results": [asdict(result) for result in results]}

    def default_search_client(self, query: str, limit: int) -> list[SearchResult]:
        # Dependency-free fallback: returns a search URL artifact rather than scraping.
        # A real search provider can replace this callable without changing the skill API.
        search_url = f"https://duckduckgo.com/?q={quote_plus(query)}"
        return [
            SearchResult(
                title=f"Search web for: {query}",
                url=search_url,
                snippet="Open this search result to inspect live web sources.",
            )
        ][:limit]
