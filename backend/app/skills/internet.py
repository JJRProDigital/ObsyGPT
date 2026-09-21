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
        # Real DuckDuckGo HTML results; falls back to a search-URL stub when offline/blocked.
        try:
            return duckduckgo_html_client(query, limit)
        except Exception:  # noqa: BLE001 - offline or blocked; keep the skill usable
            search_url = f"https://duckduckgo.com/?q={quote_plus(query)}"
            return [
                SearchResult(
                    title=f"Search web for: {query}",
                    url=search_url,
                    snippet="Open this search result to inspect live web sources.",
                )
            ][:limit]


_DDG_RESULT_LINK_PATTERN = re.compile(r'class="result__a"[^>]*href="([^"]+)"[^>]*>(.*?)</a>', re.DOTALL)
_DDG_SNIPPET_PATTERN = re.compile(r'class="result__snippet"[^>]*>(.*?)</a>', re.DOTALL)


def _strip_html_tags(fragment: str) -> str:
    from html import unescape

    return unescape(re.sub(r"<[^>]+>", "", fragment)).strip()


def _decode_ddg_href(href: str) -> str:
    from urllib.parse import parse_qs, urlparse

    try:
        query = parse_qs(urlparse(href).query)
        if "uddg" in query:
            return query["uddg"][0]
    except ValueError:
        pass
    return href


def duckduckgo_html_client(query: str, limit: int) -> list[SearchResult]:
    """Searches DuckDuckGo's HTML endpoint (no API key) and returns title/url/snippet results."""
    from urllib.parse import quote_plus

    url = "https://html.duckduckgo.com/html/?q=" + quote_plus(query)
    request = Request(
        url,
        headers={
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
            "(KHTML, like Gecko) Chrome/124.0 Safari/537.36",
            "Accept-Language": "en-US,en;q=0.9,es;q=0.8",
        },
    )
    html = urlopen(request, timeout=15).read().decode("utf-8", "ignore")

    links = _DDG_RESULT_LINK_PATTERN.findall(html)
    snippets = [_strip_html_tags(snippet) for snippet in _DDG_SNIPPET_PATTERN.findall(html)]
    results: list[SearchResult] = []
    for index, (href, title) in enumerate(links):
        if "duckduckgo.com" in href and "uddg=" not in href:
            continue
        if len(results) >= limit:
            break
        results.append(
            SearchResult(
                title=_strip_html_tags(title),
                url=_decode_ddg_href(href),
                snippet=snippets[index] if index < len(snippets) else "",
            )
        )
    if not results:
        raise ValueError("DuckDuckGo returned no parsable results (blocked or empty page).")
    return results


_RSS_ITEM_PATTERN = re.compile(r"<item>(.*?)</item>", re.DOTALL)
_RSS_TAG_PATTERNS = {
    "title": re.compile(r"<title>(.*?)</title>", re.DOTALL),
    "link": re.compile(r"<link>(.*?)</link>", re.DOTALL),
    "pubDate": re.compile(r"<pubDate>(.*?)</pubDate>", re.DOTALL),
    "description": re.compile(r"<description>(.*?)</description>", re.DOTALL),
}


def _clean_rss_value(fragment: str) -> str:
    from html import unescape

    fragment = fragment.strip()
    if fragment.startswith("<![CDATA[") and fragment.endswith("]]>"):
        fragment = fragment[9:-3]
    return unescape(re.sub(r"<[^>]+>", "", fragment)).strip()


@dataclass(frozen=True)
class NewsResult:
    title: str
    url: str
    snippet: str
    published: str


def _decode_bing_link(link: str) -> str:
    from urllib.parse import parse_qs, urlparse

    try:
        if "apiclick.aspx" in link:
            query = parse_qs(urlparse(link).query)
            if "url" in query:
                return query["url"][0]
    except ValueError:
        pass
    return link


def bing_news_client(query: str, limit: int) -> list[NewsResult]:
    """Searches Bing News RSS (no API key) and returns recent articles with publication dates."""
    from urllib.parse import quote_plus

    url = "https://www.bing.com/news/search?q=" + quote_plus(query) + "&format=RSS"
    request = Request(
        url,
        headers={
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
            "(KHTML, like Gecko) Chrome/124.0 Safari/537.36",
            "Accept-Language": "es-ES,es;q=0.9,en;q=0.8",
        },
    )
    xml = urlopen(request, timeout=15).read().decode("utf-8", "ignore")

    results: list[NewsResult] = []
    for item in _RSS_ITEM_PATTERN.findall(xml):
        values = {name: _clean_rss_value(pattern.search(item).group(1)) if pattern.search(item) else "" for name, pattern in _RSS_TAG_PATTERNS.items()}
        if not values["title"] or not values["link"]:
            continue
        if len(results) >= limit:
            break
        results.append(
            NewsResult(
                title=values["title"],
                url=_decode_bing_link(values["link"]),
                snippet=values["description"][:300],
                published=values["pubDate"],
            )
        )
    if not results:
        raise ValueError("Bing News returned no items (blocked or empty feed).")
    return results
