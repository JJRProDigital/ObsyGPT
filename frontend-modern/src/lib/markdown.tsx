// Dependency-free markdown renderer (XSS-safe by construction: no innerHTML).
import { ReactNode } from "react";

const INLINE_PATTERN = /(\*\*[^*]+\*\*|\*[^*\s][^*]*\*|`[^`]+`|\[[^\]]+\]\((https?:\/\/[^)\s]+)\))/g;

function renderInline(text: string, keyPrefix: string): ReactNode[] {
  const nodes: ReactNode[] = [];
  const pattern = new RegExp(INLINE_PATTERN.source, "g");
  let lastIndex = 0;
  let key = 0;
  let match: RegExpExecArray | null;
  while ((match = pattern.exec(text)) !== null) {
    if (match.index > lastIndex) nodes.push(text.slice(lastIndex, match.index));
    const token = match[0];
    const id = `${keyPrefix}-${key++}`;
    if (token.startsWith("**")) nodes.push(<strong key={id}>{token.slice(2, -2)}</strong>);
    else if (token.startsWith("`")) nodes.push(<code key={id} className="md-inline-code">{token.slice(1, -1)}</code>);
    else if (token.startsWith("[")) nodes.push(<a key={id} href={match[2]} target="_blank" rel="noreferrer">{token.slice(1, token.indexOf("]"))}</a>);
    else nodes.push(<em key={id}>{token.slice(1, -1)}</em>);
    lastIndex = pattern.lastIndex;
  }
  if (lastIndex < text.length) nodes.push(text.slice(lastIndex));
  return nodes;
}

function renderBlocks(text: string, keyPrefix: string): ReactNode[] {
  const lines = text.split("\n");
  const blocks: ReactNode[] = [];
  let i = 0;
  let key = 0;
  while (i < lines.length) {
    const line = lines[i];
    if (!line.trim()) { i++; continue; }
    const id = `${keyPrefix}-b${key++}`;

    const heading = line.match(/^(#{1,4})\s+(.*)$/);
    if (heading) {
      const content = renderInline(heading[2], id);
      if (heading[1].length === 1) blocks.push(<h3 key={id}>{content}</h3>);
      else if (heading[1].length === 2) blocks.push(<h4 key={id}>{content}</h4>);
      else blocks.push(<h5 key={id}>{content}</h5>);
      i++; continue;
    }

    if (/^\s*(-{3,}|\*{3,})\s*$/.test(line)) { blocks.push(<hr key={id} />); i++; continue; }

    if (/^\s*[-*+]\s+/.test(line)) {
      const items: string[] = [];
      while (i < lines.length && /^\s*[-*+]\s+/.test(lines[i])) { items.push(lines[i].replace(/^\s*[-*+]\s+/, "")); i++; }
      blocks.push(<ul key={id}>{items.map((item, n) => <li key={n}>{renderInline(item, `${id}-${n}`)}</li>)}</ul>);
      continue;
    }

    if (/^\s*\d+[.)]\s+/.test(line)) {
      const items: string[] = [];
      while (i < lines.length && /^\s*\d+[.)]\s+/.test(lines[i])) { items.push(lines[i].replace(/^\s*\d+[.)]\s+/, "")); i++; }
      blocks.push(<ol key={id}>{items.map((item, n) => <li key={n}>{renderInline(item, `${id}-${n}`)}</li>)}</ol>);
      continue;
    }

    if (line.trim().startsWith("|") && i + 1 < lines.length && /^\s*\|?[\s:|-]+\|?\s*$/.test(lines[i + 1]) && lines[i + 1].includes("-")) {
      const parseRow = (row: string) => row.trim().replace(/^\|/, "").replace(/\|$/, "").split("|").map((cell) => cell.trim());
      const header = parseRow(lines[i]);
      i += 2;
      const rows: string[][] = [];
      while (i < lines.length && lines[i].trim().startsWith("|")) { rows.push(parseRow(lines[i])); i++; }
      blocks.push(
        <div className="md-table-wrap" key={id}>
          <table>
            <thead><tr>{header.map((cell, n) => <th key={n}>{renderInline(cell, `${id}-th${n}`)}</th>)}</tr></thead>
            <tbody>{rows.map((row, r) => <tr key={r}>{row.map((cell, n) => <td key={n}>{renderInline(cell, `${id}-td${r}-${n}`)}</td>)}</tr>)}</tbody>
          </table>
        </div>
      );
      continue;
    }

    const paragraph: string[] = [];
    while (i < lines.length && lines[i].trim()) { paragraph.push(lines[i]); i++; }
    blocks.push(<p key={id}>{renderInline(paragraph.join(" "), id)}</p>);
  }
  return blocks;
}

export function renderMarkdown(text: string): ReactNode {
  const segments = text.split("```");
  return segments.map((segment, index) => {
    const id = `seg${index}`;
    if (index % 2 === 1) {
      const firstBreak = segment.indexOf("\n");
      const looksLikeLanguageTag = firstBreak > 0 && firstBreak < 24 && !segment.slice(0, firstBreak).includes(" ");
      const code = looksLikeLanguageTag ? segment.slice(firstBreak + 1) : segment;
      return <pre className="md-code" key={id}><code>{code.replace(/\n$/, "")}</code></pre>;
    }
    return <div className="md-text" key={id}>{renderBlocks(segment, id)}</div>;
  });
}
