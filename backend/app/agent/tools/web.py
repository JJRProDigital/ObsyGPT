"""Web fetch tool reusing the existing read_url skill."""

from .base import ToolResult, ToolSpec


def _default_fetcher(payload: dict) -> dict:
    from ...skills.internet import ReadUrlSkill

    return ReadUrlSkill().run(payload)


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
