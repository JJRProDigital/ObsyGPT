// Auto-extracted from App.tsx: presentational view over useApp() state.

import { renderMarkdown } from "../lib/markdown";
import { useApp } from "../state/context";

export function TasksView() {
  const { createTask, taskDraft, setTaskDraft, taskApprovals, decideTaskApproval, tasks, formatDateTime, taskAction, expandedTaskId, toggleTaskEvents, removeTask, taskEvents } = useApp();
  return (
<section className="panel full-panel tasks-view">
          <h2>Tareas en segundo plano</h2>
          <form className="task-create" onSubmit={createTask}>
            <input value={taskDraft.goal} onChange={(event) => setTaskDraft({ ...taskDraft, goal: event.target.value })} placeholder="Objetivo: busca esto y compara precios..." required />
            <select value={taskDraft.mode} onChange={(event) => setTaskDraft({ ...taskDraft, mode: event.target.value })}><option value="act">Act</option><option value="plan">Plan</option><option value="think">Think</option></select>
            <select value={taskDraft.recurrence ?? ""} onChange={(event) => setTaskDraft({ ...taskDraft, recurrence: event.target.value })}><option value="">Una vez</option><option value="daily">Diaria</option><option value="weekly">Semanal</option></select>
            <input type="datetime-local" value={taskDraft.scheduled_at} onChange={(event) => setTaskDraft({ ...taskDraft, scheduled_at: event.target.value })} title="Programar (opcional)" />
            <button type="submit">Lanzar</button>
          </form>
          <p className="muted">Cada tarea usa su propio agente con guardrails. Las herramientas sensibles pausan la tarea esperando tu aprobacion aqui.</p>
          {(taskApprovals ? Object.entries(taskApprovals).flatMap(([taskId, approvals]) => approvals.map((approval) => ({ ...approval, taskId: Number(taskId) }))) : []).length > 0 && <div className="approval-stack">
            {Object.entries(taskApprovals).flatMap(([taskId, approvals]) => approvals.map((approval) => <article className="approval-card" key={approval.id}>
              <div className="approval-head"><strong>Aprobacion requerida</strong><span className="chip">{approval.tool_name}</span><span className="chip muted-chip">Tarea #{taskId}</span></div>
              <pre className="approval-args">{JSON.stringify(approval.args, null, 2)}</pre>
              <div className="approval-actions">
                <button className="approve-button" onClick={() => decideTaskApproval(approval, true)}>Aprobar y continuar</button>
                <button className="deny-button" onClick={() => decideTaskApproval(approval, false)}>Rechazar</button>
              </div>
            </article>))}
          </div>}
          {tasks.length === 0 ? <p className="muted">Sin tareas todavia.</p> : tasks.map((task) => <article className="task-card" key={task.id}>
            <div className="task-card-head">
              <div><strong>{task.goal}</strong><span className="muted">{task.mode.toUpperCase()}{task.recurrence ? ` · ${task.recurrence === "daily" ? "diaria" : "semanal"}` : ""} · {formatDateTime(task.created_at)}{task.attempts > 0 ? ` · intentos: ${task.attempts}` : ""}{task.scheduled_at ? ` · programada: ${formatDateTime(task.scheduled_at)}` : ""}</span></div>
              <span className={`chip ${["completed", "failed", "cancelled"].includes(task.status) ? "muted-chip" : "agentic-chip"}`}>{task.status}{task.project_id ? ` · P${task.project_id}` : ""}</span>
            </div>
            {task.error && <p className="muted">Error: {task.error.slice(0, 300)}</p>}
            {task.result && <div className="task-result md-message">{renderMarkdown(task.result)}</div>}
            <div className="skill-actions">
              {["pending", "scheduled", "running"].includes(task.status) && <button className="text-button" onClick={() => taskAction(task.id, "pause")}>Pausar</button>}
              {["paused", "interrupted", "failed"].includes(task.status) && <button className="text-button" onClick={() => taskAction(task.id, "resume")}>Reanudar</button>}
              {!["completed", "failed", "cancelled"].includes(task.status) && <button className="text-button danger" onClick={() => taskAction(task.id, "cancel")}>Cancelar</button>}
              <button className="text-button" onClick={() => toggleTaskEvents(task.id)}>{expandedTaskId === task.id ? "Ocultar pasos" : "Ver pasos"}</button>
              <button className="text-button danger" onClick={() => removeTask(task.id)}>Eliminar</button>
            </div>
            {expandedTaskId === task.id && <div className="trace-section">
              {(taskEvents[task.id] ?? []).length === 0 ? <p className="muted">Sin pasos registrados.</p> : (taskEvents[task.id] ?? []).map((eventItem) => <div className="trace-event" key={eventItem.id}><strong>{eventItem.title}</strong><span>{formatDateTime(eventItem.created_at)}</span>{eventItem.content && <small>{eventItem.content.slice(0, 200)}</small>}</div>)}
            </div>}
          </article>)}
        </section>
  );
}
