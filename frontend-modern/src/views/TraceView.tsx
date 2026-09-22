// Auto-extracted from App.tsx: presentational view over useApp() state.

import { useApp } from "../state/context";

export function TraceView() {
  const { runs, formatDateTime, events, toolCalls, sources } = useApp();
  return (
<section className="panel full-panel"><h2>Traza de runs</h2>{runs.length === 0 ? <p className="muted">Sin runs registrados en esta conversacion.</p> : runs.map((run) => <div className="trace-run" key={run.id}><div className="trace-run-head"><strong>{run.parent_run_id ? `â†³ Run #${run.id} (sub-agente de #${run.parent_run_id})` : `Run #${run.id}`}</strong><span className={`chip ${run.status === "completed" ? "muted-chip" : "agentic-chip"}`}>{run.status}</span></div>{run.final_response && <p className="muted">{run.final_response.slice(0, 300)}...</p>}<div className="trace-section"><h3>Eventos</h3>{events.length === 0 ? <p className="muted">Sin eventos.</p> : events.slice(0, 20).map((event) => <div className="trace-event" key={event.id}><strong>{event.title}</strong><span>{event.created_at ? formatDateTime(event.created_at) : ""}</span>{event.content && <small>{event.content.slice(0, 220)}</small>}</div>)}</div><div className="trace-section"><h3>Tool calls</h3>{toolCalls.length === 0 ? <p className="muted">Sin tool calls.</p> : toolCalls.map((toolCall) => <div className="tool-call" key={toolCall.id}><strong>{toolCall.skill_name}</strong><span>{toolCall.status}: {toolCall.input_summary}</span><small>{toolCall.output_summary}</small></div>)}</div><div className="trace-section"><h3>Fuentes</h3>{sources.length === 0 ? <p className="muted">Sin fuentes.</p> : sources.map((source) => <a className="source-link" href={source.url} target="_blank" rel="noreferrer" key={source.id}>{source.title} â€” {source.url}</a>)}</div></div>)}</section>
  );
}
