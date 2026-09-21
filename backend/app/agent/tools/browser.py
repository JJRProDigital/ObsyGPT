"""Browser automation tool backed by Playwright (Chromium).

A single dedicated worker thread owns the Playwright instance, browser and
page; every tool call submits a callable to that thread and waits for the
result. Snapshots assign numeric refs to visible interactive elements so the
model can click/type without crafting CSS selectors.
"""

import queue
import threading
import time
import traceback
from pathlib import Path

from .base import ToolResult, ToolSpec
from .files import default_workspace_root


COMMAND_TIMEOUT_SECONDS = 45
MAX_TEXT_CHARS = 1800
MAX_ELEMENTS = 60

_COLLECT_ELEMENTS_JS = """
() => {
  const interactive = ['a', 'button', 'input', 'textarea', 'select', 'summary'];
  const results = [];
  const seen = new Set();
  const cssPath = (el) => {
    const parts = [];
    let node = el;
    while (node && node.nodeType === 1) {
      let part = node.nodeName.toLowerCase();
      if (node.id) { part = '#' + node.id; parts.unshift(part); break; }
      const parent = node.parentNode;
      if (parent) {
        const siblings = Array.from(parent.children).filter(c => c.nodeName === node.nodeName);
        const index = siblings.indexOf(node) + 1;
        if (siblings.length > 1) part += ':nth-of-type(' + index + ')';
      }
      parts.unshift(part);
      node = parent;
    }
    return parts.join(' > ');
  };
  for (const el of document.querySelectorAll(interactive.join(','))) {
    const rect = el.getBoundingClientRect();
    const style = window.getComputedStyle(el);
    if (rect.width === 0 || rect.height === 0 || style.visibility === 'hidden' || style.display === 'none') continue;
    const path = cssPath(el);
    if (!path || seen.has(path)) continue;
    seen.add(path);
    const name = (el.getAttribute('aria-label') || el.getAttribute('placeholder') || (el.innerText || el.value || '') || '').trim().replace(/\\s+/g, ' ').slice(0, 90);
    const tag = el.nodeName.toLowerCase();
    const type = el.getAttribute('type');
    const role = tag === 'a' ? 'link' : (tag === 'select' ? 'select' : (type ? tag + ':' + type : tag));
    const value = tag === 'input' || tag === 'textarea' ? String(el.value || '').slice(0, 60) : '';
    results.push({ role, name, value, href: tag === 'a' ? (el.href || '') : '', selector: path });
    if (results.length >= 120) break;
  }
  return results;
}
"""


class _BrowserWorker:
    """Dedicated thread owning the Playwright browser; executes one command at a time."""

    def __init__(self, headless: bool = True):
        self.headless = headless
        self._queue: queue.Queue = queue.Queue()
        self._thread: threading.Thread | None = None
        self._lock = threading.Lock()
        self._started = threading.Event()

    def _ensure_thread(self) -> None:
        with self._lock:
            if self._thread is None or not self._thread.is_alive():
                self._started.clear()
                self._thread = threading.Thread(target=self._run, name="obsygpt-browser", daemon=True)
                self._thread.start()
                if not self._started.wait(timeout=20):
                    raise RuntimeError("Browser worker failed to start.")

    def _run(self) -> None:
        from playwright.sync_api import sync_playwright

        with sync_playwright() as playwright:
            browser = playwright.chromium.launch(headless=self.headless)
            context = browser.new_context(viewport={"width": 1280, "height": 900})
            page = context.new_page()
            self._started.set()
            while True:
                item = self._queue.get()
                if item is None:
                    break
                func, future = item
                try:
                    future["result"] = func(page, context, browser)
                except Exception as error:  # noqa: BLE001
                    future["error"] = f"{type(error).__name__}: {error}"
                finally:
                    future["done"].set()
            try:
                context.close()
                browser.close()
            except Exception:  # noqa: BLE001
                pass

    def submit(self, func):  # noqa: ANN001, ANN201
        self._ensure_thread()
        future = {"done": threading.Event()}
        self._queue.put((func, future))
        if not future["done"].wait(timeout=COMMAND_TIMEOUT_SECONDS):
            return None, "Browser command timed out."
        if "error" in future:
            return None, future["error"]
        return future.get("result"), None

    def stop(self) -> None:
        with self._lock:
            if self._thread is not None and self._thread.is_alive():
                self._queue.put(None)


class BrowserSessionManager:
    """Process-wide browser session with snapshot refs shared by all browser tools."""

    def __init__(self):
        self.worker = _BrowserWorker(headless=True)
        self.refs: dict[int, dict] = {}
        self._counter = 0
        self._ref_lock = threading.Lock()

    def run(self, func):  # noqa: ANN001, ANN201
        return self.worker.submit(func)

    def reset_refs(self) -> None:
        with self._ref_lock:
            self.refs = {}

    def remember(self, elements: list[dict]) -> None:
        with self._ref_lock:
            self._counter += 1
            self.refs = {index + 1: element for index, element in enumerate(elements[:MAX_ELEMENTS])}

    def selector_for_ref(self, ref: int) -> str | None:
        with self._ref_lock:
            element = self.refs.get(ref)
            return element["selector"] if element else None

    def current_page_info(self) -> dict:
        def info(page, context, browser):  # noqa: ANN001
            return {"url": page.url, "title": page.title()}

        result, error = self.run(info)
        if error:
            return {"url": "", "title": ""}
        return result or {"url": "", "title": ""}


_manager: BrowserSessionManager | None = None
_manager_lock = threading.Lock()


def get_browser_manager() -> BrowserSessionManager:
    global _manager
    with _manager_lock:
        if _manager is None:
            _manager = BrowserSessionManager()
        return _manager


def _valid_url(url: str) -> bool:
    return url.startswith("http://") or url.startswith("https://")


def _format_snapshot(info: dict, elements: list[dict], text: str) -> str:
    lines = [f"TITLE: {info.get('title', '')}", f"URL: {info.get('url', '')}", "", "ELEMENTS:"]
    if not elements:
        lines.append("(no interactive elements found)")
    for index, element in enumerate(elements[:MAX_ELEMENTS], start=1):
        label = element.get("name") or element.get("value") or "(sin nombre)"
        suffix = f" -> {element['href'][:90]}" if element.get("href") else ""
        value = f" [valor: {element['value']}]" if element.get("value") else ""
        lines.append(f"[{index}] {element.get('role', 'element')} \"{label}\"{value}{suffix}")
    lines.append("")
    lines.append("VISIBLE TEXT:")
    lines.append(text[:MAX_TEXT_CHARS] if text else "(sin texto visible)")
    return "\n".join(lines)


class _BrowserTool:
    spec: ToolSpec

    def __init__(self, manager: BrowserSessionManager | None = None, workspace_root: Path | None = None):
        self.manager = manager or get_browser_manager()
        self.workspace_root = (workspace_root or default_workspace_root()).resolve()

    def _fail(self, message: str) -> ToolResult:
        return ToolResult(ok=False, output=message)


class BrowserNavigateTool(_BrowserTool):
    spec = ToolSpec(
        name="browser_navigate",
        description="Opens a public http(s) URL in the built-in browser and returns the page snapshot.",
        parameters='{"url": "<url publica http o https>"}',
        permission="safe",
    )

    def run(self, args: dict) -> ToolResult:
        url = str(args.get("url", "")).strip()
        if not _valid_url(url):
            return self._fail("Missing or invalid url (only http/https is supported).")

        def navigate(page, context, browser):  # noqa: ANN001
            page.goto(url, wait_until="domcontentloaded", timeout=30000)
            page.wait_for_timeout(400)
            elements = page.evaluate(_COLLECT_ELEMENTS_JS)
            text = page.evaluate("() => document.body ? document.body.innerText : ''")
            return {"url": page.url, "title": page.title(), "elements": elements, "text": text}

        result, error = self.manager.run(navigate)
        if error:
            return self._fail(f"browser_navigate failed: {error}")
        self.manager.remember(result["elements"])
        return ToolResult(ok=True, output=_format_snapshot(result, result["elements"], result["text"]))


class BrowserSnapshotTool(_BrowserTool):
    spec = ToolSpec(
        name="browser_snapshot",
        description="Returns the current page snapshot: title, URL, numbered interactive elements and visible text.",
        parameters='{"sin_argumentos": "captura el estado actual de la pagina"}',
        permission="safe",
    )

    def run(self, args: dict) -> ToolResult:
        def snapshot(page, context, browser):  # noqa: ANN001
            elements = page.evaluate(_COLLECT_ELEMENTS_JS)
            text = page.evaluate("() => document.body ? document.body.innerText : ''")
            return {"url": page.url, "title": page.title(), "elements": elements, "text": text}

        result, error = self.manager.run(snapshot)
        if error:
            return self._fail(f"browser_snapshot failed: {error}")
        self.manager.remember(result["elements"])
        return ToolResult(ok=True, output=_format_snapshot(result, result["elements"], result["text"]))


class BrowserClickTool(_BrowserTool):
    spec = ToolSpec(
        name="browser_click",
        description="Clicks an interactive element by its [ref] number from the last snapshot. Requires user approval.",
        parameters='{"ref": "<numero [N] del elemento listado en el snapshot>"}',
        permission="sensitive",
    )

    def run(self, args: dict) -> ToolResult:
        try:
            ref = int(args.get("ref"))
        except (TypeError, ValueError):
            return self._fail("Missing or invalid ref (use the [N] number from the snapshot).")
        selector = self.manager.selector_for_ref(ref)
        if not selector:
            return self._fail(f"Unknown ref {ref}. Take a browser_snapshot first and use a listed [N].")

        def click(page, context, browser):  # noqa: ANN001
            page.locator(selector).first.click(timeout=15000)
            page.wait_for_timeout(500)
            elements = page.evaluate(_COLLECT_ELEMENTS_JS)
            text = page.evaluate("() => document.body ? document.body.innerText : ''")
            return {"url": page.url, "title": page.title(), "elements": elements, "text": text}

        result, error = self.manager.run(click)
        if error:
            return self._fail(f"browser_click failed on [{ref}]: {error}")
        self.manager.remember(result["elements"])
        return ToolResult(ok=True, output=f"Clicked [{ref}]. New state:\n\n" + _format_snapshot(result, result["elements"], result["text"]))


class BrowserTypeTool(_BrowserTool):
    spec = ToolSpec(
        name="browser_type",
        description="Types text into an input element by its [ref] number; optionally submits with Enter. Requires user approval.",
        parameters='{"ref": "<numero [N] del input>", "text": "<texto a escribir>", "submit": true}',
        permission="sensitive",
    )

    def run(self, args: dict) -> ToolResult:
        try:
            ref = int(args.get("ref"))
        except (TypeError, ValueError):
            return self._fail("Missing or invalid ref (use the [N] number from the snapshot).")
        text = str(args.get("text", ""))
        if not text:
            return self._fail("Missing required argument: text")
        submit = bool(args.get("submit", False))
        selector = self.manager.selector_for_ref(ref)
        if not selector:
            return self._fail(f"Unknown ref {ref}. Take a browser_snapshot first and use a listed [N].")

        def type_and_maybe_submit(page, context, browser):  # noqa: ANN001
            locator = page.locator(selector).first
            locator.fill(text, timeout=15000)
            if submit:
                locator.press("Enter")
                page.wait_for_timeout(900)
            elements = page.evaluate(_COLLECT_ELEMENTS_JS)
            text_body = page.evaluate("() => document.body ? document.body.innerText : ''")
            return {"url": page.url, "title": page.title(), "elements": elements, "text": text_body}

        result, error = self.manager.run(type_and_maybe_submit)
        if error:
            return self._fail(f"browser_type failed on [{ref}]: {error}")
        self.manager.remember(result["elements"])
        action = "typed and submitted" if submit else "typed"
        return ToolResult(ok=True, output=f"{action} \"{text}\" into [{ref}]. New state:\n\n" + _format_snapshot(result, result["elements"], result["text"]))


class BrowserScreenshotTool(_BrowserTool):
    spec = ToolSpec(
        name="browser_screenshot",
        description="Captures a PNG screenshot of the current page into the workspace and returns the file path.",
        parameters='{"sin_argumentos": "guarda la captura en workspace/screenshots/"}',
        permission="safe",
    )

    def run(self, args: dict) -> ToolResult:
        screenshots_dir = self.workspace_root / "screenshots"
        screenshots_dir.mkdir(parents=True, exist_ok=True)
        target = screenshots_dir / f"browser_{int(time.time() * 1000)}.png"

        def screenshot(page, context, browser):  # noqa: ANN001
            page.screenshot(path=str(target), full_page=False)
            return str(target)

        result, error = self.manager.run(screenshot)
        if error:
            return self._fail(f"browser_screenshot failed: {error}")
        return ToolResult(ok=True, output=f"Screenshot saved to {result}")


class BrowserCloseTool(_BrowserTool):
    spec = ToolSpec(
        name="browser_close",
        description="Closes the built-in browser session and discards the current page.",
        parameters='{"sin_argumentos": "cierra y limpia la sesion del navegador"}',
        permission="safe",
    )

    def run(self, args: dict) -> ToolResult:
        self.manager.reset_refs()
        def close(page, context, browser):  # noqa: ANN001
            page.goto("about:blank")
            return "closed"

        result, error = self.manager.run(close)
        if error:
            return self._fail(f"browser_close failed: {error}")
        return ToolResult(ok=True, output="Browser session closed.")


class BrowserTools:
    def __init__(self, workspace_root: Path | None = None, manager: BrowserSessionManager | None = None):
        self.workspace_root = workspace_root
        self.manager = manager

    def tools(self) -> list:
        return [
            BrowserNavigateTool(manager=self.manager, workspace_root=self.workspace_root),
            BrowserSnapshotTool(manager=self.manager, workspace_root=self.workspace_root),
            BrowserClickTool(manager=self.manager, workspace_root=self.workspace_root),
            BrowserTypeTool(manager=self.manager, workspace_root=self.workspace_root),
            BrowserScreenshotTool(manager=self.manager, workspace_root=self.workspace_root),
            BrowserCloseTool(manager=self.manager, workspace_root=self.workspace_root),
        ]
