// Dependency-free markdown renderer (XSS-safe by construction: no innerHTML).
import { ReactNode } from "react";

// Image tokens must match before links: only same-origin /api/workspace-image and http(s) sources.
// Groups: 1 = whole token, 2 = image url, 3 = link url, 4 = bare url.
const INLINE_PATTERN = /(!\[[^\]]*\]\((\/api\/workspace-image[^)\s]+|https?:\/\/[^)\s]+)\)|\*\*[^*]+\*\*|\*[^*\s][^*]*\*|`[^`]+`|\[[^\]]+\]\((https?:\/\/[^)\s]+)\)|(https?:\/\/[^\s)\]}>,]+))/g;

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
    if (token.startsWith("![")) {
      const alt = token.slice(2, token.indexOf("]"));
      nodes.push(
        <a key={id} href={match[2]} target="_blank" rel="noreferrer" className="md-image-link" title="Abrir imagen en una pestaña nueva">
          <img src={match[2]} alt={alt} className="md-image" loading="lazy" />
        </a>
      );
    }
    else if (token.startsWith("**")) nodes.push(<strong key={id}>{token.slice(2, -2)}</strong>);
    else if (token.startsWith("`")) nodes.push(<code key={id} className="md-inline-code">{token.slice(1, -1)}</code>);
    else if (token.startsWith("[")) nodes.push(<a key={id} href={match[3]} target="_blank" rel="noreferrer">{token.slice(1, token.indexOf("]"))}</a>);
    else if (token.startsWith("http")) {
      const url = token.replace(/[.,;:]+$/, "");
      const trailing = token.slice(url.length);
      nodes.push(<a key={id} href={url} target="_blank" rel="noreferrer">{url}</a>, trailing);
    }
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

    const orderedMatch = line.match(/^\s*(\d+)[.)]\s+(.*)$/);
    if (orderedMatch) {
      // Keep multi-line items and blank-line spacing in ONE list, and honor the
      // source number. Splitting into several <ol> made every list restart at 1.
      const start = Number(orderedMatch[1]);
      const items: string[] = [orderedMatch[2]];
      i++;
      while (i < lines.length) {
        const current = lines[i];
        const nextItem = current.match(/^\s*\d+[.)]\s+(.*)$/);
        if (nextItem) { items.push(nextItem[1]); i++; continue; }
        if (!current.trim()) {
          let j = i + 1;
          while (j < lines.length && !lines[j].trim()) j++;
          if (j < lines.length && /^\s*\d+[.)]\s+/.test(lines[j])) { i = j; continue; }
          break;
        }
        if (/^\s*([-*+]\s+|#{1,4}\s+|\||```)/.test(current) || /^\s*(-{3,}|\*{3,})\s*$/.test(current)) break;
        items[items.length - 1] += ` ${current.trim()}`;
        i++;
      }
      blocks.push(<ol key={id} start={start}>{items.map((item, n) => <li key={n}>{renderInline(item, `${id}-${n}`)}</li>)}</ol>);
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
