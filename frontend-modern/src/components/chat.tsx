// Chat-specific components: memoized message and the live activity bar.
import { memo, useEffect, useMemo, useState } from "react";
import { renderMarkdown } from "../lib/markdown";
import type { Message } from "../types";

export type LiveActivityState = { label: string; startedAt: number; lastAt: number; iteration?: number; chars?: number; detail?: string; thought?: string };

/** Isolated 1s ticker: only this bar re-renders while an agent run is active. */
export function LiveActivityBar({ activity }: { activity: LiveActivityState }) {
  const [nowTick, setNowTick] = useState(() => Date.now());
  useEffect(() => {
    const interval = window.setInterval(() => setNowTick(Date.now()), 1000);
    return () => window.clearInterval(interval);
  }, []);
  const elapsed = Math.max(0, Math.floor((nowTick - activity.startedAt) / 1000));
  const stale = Math.floor((nowTick - activity.lastAt) / 1000);
  const mm = String(Math.floor(elapsed / 60)).padStart(2, "0");
  const ss = String(elapsed % 60).padStart(2, "0");
  const tokens = Math.round((activity.chars ?? 0) / 4);
  return (
    <div className={`live-activity${stale > 45 ? " stale" : ""}`} role="status">
      <span className="live-dot" aria-hidden="true" />
      <span className="live-elapsed">⏱ {mm}:{ss}</span>
      {activity.iteration !== undefined && <span className="live-iter">iter {activity.iteration}</span>}
      {tokens > 0 && <span className="live-tokens">~{tokens.toLocaleString()} tokens</span>}
      <span className="live-label">{activity.label}{activity.detail ? ` (${activity.detail})` : ""}</span>
      {activity.thought && <div className="live-thought" title={activity.thought}>{activity.thought}</div>}
      {stale > 45 && <span className="live-stale">sin señal nueva hace {stale}s</span>}
    </div>
  );
}

type MessageItemProps = {
  message: Message;
  index: number;
  isEditing: boolean;
  editingDraft: string;
  isCopied: boolean;
  onDraftChange: (value: string) => void;
  onSaveEdit: (index: number) => void;
  onCancelEdit: () => void;
  onCopy: (index: number) => void;
  onEdit: (index: number) => void;
  onSpeak?: (index: number) => void;
  speaking?: boolean;
};

/**
 * Memoized chat message: markdown parsing is memoized per content, so a
 * streaming token only re-renders the last message instead of re-parsing
 * the whole conversation history.
 */
export const MessageItem = memo(function MessageItem({ message, index, isEditing, editingDraft, isCopied, onDraftChange, onSaveEdit, onCancelEdit, onCopy, onEdit, onSpeak, speaking }: MessageItemProps) {
  const rendered = useMemo(
    () => (message.role === "assistant" ? renderMarkdown(message.content || "Pensando...") : message.content),
    [message.role, message.content]
  );
  if (isEditing) {
    return (
      <article className={`message ${message.role} editing`}>
        <div className="message-edit">
          <textarea value={editingDraft} onChange={(event) => onDraftChange(event.target.value)} rows={4} autoFocus />
          <div className="message-edit-actions">
            <button type="button" onClick={() => onSaveEdit(index)}>Guardar</button>
            <button type="button" className="text-button" onClick={onCancelEdit}>Cancelar</button>
          </div>
        </div>
      </article>
    );
  }
  return (
    <article className={`message ${message.role}${message.role === "assistant" ? " md-message" : ""}`}>
      <div className="message-body">{rendered}</div>
      <div className="message-actions">
        {message.role === "assistant" && onSpeak && <button type="button" className="text-button" disabled={speaking} onClick={() => onSpeak(index)} title="Reproducir en voz alta">{speaking ? "..." : (<svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.8" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true"><path d="M11 5L6 9H3v6h3l5 4z" /><path d="M15.5 8.5a5 5 0 010 7" /><path d="M18 6a8.5 8.5 0 010 12" /></svg>)}</button>}
        <button type="button" className="text-button" onClick={() => onCopy(index)} title="Copiar">{isCopied ? "✓" : "⧉"}</button>
        {message.role === "user" && <button type="button" className="text-button" onClick={() => onEdit(index)} title="Editar">✎</button>}
      </div>
    </article>
  );
});
