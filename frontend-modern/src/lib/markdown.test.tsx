import { describe, expect, it } from "vitest";
import { renderToStaticMarkup } from "react-dom/server";
import { renderMarkdown } from "./markdown";

function html(text: string): string {
  return renderToStaticMarkup(renderMarkdown(text) as never);
}

describe("renderMarkdown", () => {
  it("renders fenced code blocks", () => {
    const out = html("```python\nprint('hola')\n```");
    expect(out).toContain('class="md-code"');
    expect(out).toContain("print(&#x27;hola&#x27;)");
    expect(out).not.toContain("python"); // language tag stripped
  });

  it("renders headings, lists and tables", () => {
    const out = html("# Titulo\n- item uno\n- item dos\n\n| a | b |\n|---|---|\n| 1 | 2 |");
    expect(out).toContain("<h3>");
    expect(out).toContain("<ul>");
    expect(out).toContain("<li>item uno</li>");
    expect(out).toContain("<table>");
    expect(out).toContain("<td>2</td>");
  });

  it("renders inline formatting and safe links", () => {
    const out = html("**negrita** y *cursiva* y `codigo` y [docs](https://example.com)");
    expect(out).toContain("<strong>negrita</strong>");
    expect(out).toContain("<em>cursiva</em>");
    expect(out).toContain('class="md-inline-code"');
    expect(out).toContain('<a href="https://example.com"');
  });

  it("never injects raw HTML (XSS-safe)", () => {
    const out = html("<img src=x onerror=alert(1)> texto");
    expect(out).not.toContain("<img");
    expect(out).toContain("&lt;img");
  });

  it("treats unterminated fences as code till the end", () => {
    const out = html("antes ```js\ncodigo");
    expect(out).toContain("md-code");
    expect(out).toContain("codigo");
  });
});
