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

  it("keeps numbering across blank lines and multi-line items", () => {
    const out = html("1. Primero\ncontinuacion uno\n\n2. Segundo\ncontinuacion dos\n\n3. Tercero");
    expect(out.match(/<ol/g)?.length).toBe(1);
    expect(out.match(/<li>/g)?.length).toBe(3);
    expect(out).toContain("Primero continuacion uno");
    expect(out).toContain("Segundo continuacion dos");
    expect(out).toContain('<ol start="1">');
  });

  it("preserves an explicit starting number", () => {
    const out = html("3. Tercero\n\n4. Cuarto");
    expect(out).toContain('<ol start="3">');
    expect(out).toContain("<li>Tercero</li>");
    expect(out).toContain("<li>Cuarto</li>");
  });

  it("renumbers items when the model repeats the same number", () => {
    const out = html("1. Uno\n\n1. Dos\n\n1. Tres");
    expect(out.match(/<ol/g)?.length).toBe(1);
    expect(out.match(/<li>/g)?.length).toBe(3);
  });

  it("does not absorb a separate paragraph into the list", () => {
    const out = html("1. Primero\n\nNota aparte.");
    expect(out).toContain("<li>Primero</li>");
    expect(out).toContain("<p>Nota aparte.</p>");
  });

  it("renders inline formatting and safe links", () => {    const out = html("**negrita** y *cursiva* y `codigo` y [docs](https://example.com)");
    expect(out).toContain("<strong>negrita</strong>");
    expect(out).toContain("<em>cursiva</em>");
    expect(out).toContain('class="md-inline-code"');
    expect(out).toContain('<a href="https://example.com"');
  });

  it("autolinks bare urls opening in a new tab", () => {
    const out = html("Tu video: https://cdn.example.com/video.mp4 listo.");
    expect(out).toContain('<a href="https://cdn.example.com/video.mp4" target="_blank" rel="noreferrer">');
    expect(out).toContain(">https://cdn.example.com/video.mp4</a> listo");
  });

  it("autolinks bare urls without swallowing trailing punctuation", () => {
    const out = html("Mira https://example.com/video.mp4.");
    expect(out).toContain('<a href="https://example.com/video.mp4"');
    expect(out).not.toContain('href="https://example.com/video.mp4."');
  });

  it("does not double-wrap markdown links", () => {
    const out = html("[ver](https://example.com/a.mp4)");
    expect(out).toContain('<a href="https://example.com/a.mp4"');
    expect(out).toContain(">ver</a>");
    expect(out).not.toContain("https://example.com/a.mp4</a></a>");
  });

  it("never injects raw HTML (XSS-safe)", () => {
    const out = html("<img src=x onerror=alert(1)> texto");
    expect(out).not.toContain("<img");
    expect(out).toContain("&lt;img");
  });

  it("renders workspace images as safe same-origin img tags", () => {
    const out = html("![generada](/api/workspace-image?path=/data/workspace/flow-images/a.jpg)");
    expect(out).toContain('class="md-image"');
    expect(out).toContain('src="/api/workspace-image?path=/data/workspace/flow-images/a.jpg"');
    expect(out).toContain('alt="generada"');
  });

  it("renders remote images and rejects javascript urls", () => {
    expect(html("![x](https://cdn.example.com/a.png)")).toContain('src="https://cdn.example.com/a.png"');
    const evil = html("![x](javascript:alert(1))");
    expect(evil).not.toContain("<img");
  });

  it("treats unterminated fences as code till the end", () => {
    const out = html("antes ```js\ncodigo");
    expect(out).toContain("md-code");
    expect(out).toContain("codigo");
  });
});
