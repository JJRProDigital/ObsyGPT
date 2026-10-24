import pytest

from app.agent.tools import default_tool_registry
from app.agent.tools.browser import (
    BrowserClickTool,
    BrowserNavigateTool,
    BrowserSnapshotTool,
    BrowserScreenshotTool,
    BrowserTypeTool,
    BrowserTools,
    _format_snapshot,
)


class FakeManager:
    def __init__(self, result=None, error=None):
        self.result = result
        self.error = error
        self.submitted = []

    def run(self, func, session_key="default"):
        self.submitted.append(func)
        if self.error:
            return None, self.error
        return self.result, None

    def reset_refs(self, session_key="default"):
        pass

    def remember(self, elements, session_key="default"):
        self.remembered = elements

    def selector_for_ref(self, ref, session_key="default"):
        return {1: "#buscar"}.get(ref)


@pytest.fixture
def snapshot_result():
    return {
        "url": "https://example.com",
        "title": "Example",
        "elements": [
            {"role": "input", "name": "Buscar", "value": "", "href": "", "selector": "#q"},
            {"role": "link", "name": "Docs", "value": "", "href": "https://example.com/docs", "selector": "a:nth-of-type(2)"},
        ],
        "text": "Contenido visible de la pagina",
    }


def test_registry_exposes_browser_tools_with_permissions():
    registry = default_tool_registry()
    specs = {spec.name: spec for spec in registry.list_specs()}

    assert specs["browser_navigate"].permission == "safe"
    assert specs["browser_snapshot"].permission == "safe"
    assert specs["browser_screenshot"].permission == "safe"
    assert specs["browser_close"].permission == "safe"
    assert specs["browser_click"].permission == "sensitive"
    assert specs["browser_type"].permission == "sensitive"


def test_navigate_rejects_non_http_url():
    manager = FakeManager()
    tool = BrowserNavigateTool(manager=manager)

    result = tool.run({"url": "ftp://ejemplo.com"})

    assert not result.ok
    assert "http" in result.output.lower()
    assert manager.submitted == []


def test_navigate_formats_snapshot(snapshot_result):
    manager = FakeManager(result=snapshot_result)
    tool = BrowserNavigateTool(manager=manager)

    result = tool.run({"url": "https://example.com"})

    assert result.ok
    assert "TITLE: Example" in result.output
    assert "[1] input \"Buscar\"" in result.output
    assert "[2] link \"Docs\" -> https://example.com/docs" in result.output
    assert "Contenido visible" in result.output
    assert len(manager.remembered) == 2


def test_snapshot_remember_refs(snapshot_result):
    manager = FakeManager(result=snapshot_result)
    tool = BrowserSnapshotTool(manager=manager)

    result = tool.run({})

    assert result.ok
    assert "ELEMENTS:" in result.output


def test_click_requires_known_ref():
    manager = FakeManager()
    tool = BrowserClickTool(manager=manager)

    result = tool.run({"ref": 99})

    assert not result.ok
    assert "Unknown ref" in result.output
    assert manager.submitted == []


def test_click_reports_new_state(snapshot_result):
    manager = FakeManager(result=snapshot_result, error=None)
    manager.selector_for_ref = lambda ref, session_key="default": "#buscar"
    tool = BrowserClickTool(manager=manager)

    result = tool.run({"ref": 1})

    assert result.ok
    assert "Clicked [1]" in result.output


def test_type_validates_text_and_ref():
    manager = FakeManager()
    tool = BrowserTypeTool(manager=manager)

    no_text = tool.run({"ref": 1})
    assert not no_text.ok
    assert "text" in no_text.output.lower()

    no_ref = tool.run({"text": "hola"})
    assert not no_ref.ok
    assert "ref" in no_ref.output.lower()


def test_type_returns_new_state(snapshot_result):
    manager = FakeManager(result=snapshot_result)
    manager.selector_for_ref = lambda ref, session_key="default": "#q"
    tool = BrowserTypeTool(manager=manager)

    result = tool.run({"ref": 1, "text": "consulta", "submit": True})

    assert result.ok
    assert 'typed and submitted "consulta" into [1]' in result.output


def test_screenshot_saves_into_workspace(tmp_path):
    manager = FakeManager(result=str(tmp_path / "screenshots" / "browser_1.png"))
    tool = BrowserScreenshotTool(manager=manager, workspace_root=tmp_path)

    result = tool.run({})

    assert result.ok
    assert "Screenshot saved" in result.output
    assert (tmp_path / "screenshots").exists()


def test_tool_errors_map_to_failed_result(snapshot_result):
    manager = FakeManager(error="TimeoutError: navigation timeout")
    tool = BrowserNavigateTool(manager=manager)

    result = tool.run({"url": "https://example.com"})

    assert not result.ok
    assert "TimeoutError" in result.output


def test_format_snapshot_empty_elements():
    output = _format_snapshot({"title": "X", "url": "https://x"}, [], "")

    assert "(no interactive elements found)" in output
    assert "(sin texto visible)" in output


def test_browser_tools_bundle_returns_all():
    tools = BrowserTools().tools()

    assert {tool.spec.name for tool in tools} == {
        "browser_navigate",
        "browser_snapshot",
        "browser_click",
        "browser_type",
        "browser_screenshot",
        "browser_close",
    }


def test_chat_registry_includes_browser_tools():
    """Regression: the chat pipeline registry once missed browser tools entirely."""
    from app.chat.routes import build_agent_tool_registry

    registry = build_agent_tool_registry(user_id=None)
    names = {spec.name for spec in registry.list_specs()}

    assert {"browser_navigate", "browser_snapshot", "browser_click", "browser_type", "browser_screenshot", "browser_close"} <= names
    assert "web_fetch" in names
