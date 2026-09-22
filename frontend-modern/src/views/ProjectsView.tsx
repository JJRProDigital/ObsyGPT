// Auto-extracted from App.tsx: presentational view over useApp() state.

import { renderMarkdown } from "../lib/markdown";
import { useApp } from "../state/context";

export function ProjectsView() {
  const { projectDetail, createProject, projectDraft, setProjectDraft, projects, setProjectTab, openProjectDetail, archiveProject, setProjectDetail, createProjectChat, removeProject, projectTab, conversations, projectLinkConversation, formatDateTime, createProjectTask, projectTaskDraft, setProjectTaskDraft, projectTasks, projectTaskAction, uploadProjectKnowledge, projectLinkAttachment, attachments, projectInstructionsDraft, setProjectInstructionsDraft, saveProjectInstructions, addProjectMemory, projectMemoryDraft, setProjectMemoryDraft, projectMemories, deleteProjectMemory, projectFiles, refreshProjectFiles, unlinkProjectWorkspace, enableProjectWorkspace, deleteProjectFile, setActiveConversationId, setActiveView } = useApp();
  return (
<section className="panel full-panel projects-view">
          <h2>Proyectos</h2>
          {!projectDetail && <>
            <p className="muted">Espacios de trabajo dedicados: chats, tareas, archivos e instrucciones propias. Los tools operan en la carpeta del proyecto si la configuras.</p>
            <form className="task-create project-create-form" onSubmit={createProject}>
              <input value={projectDraft.name} onChange={(event) => setProjectDraft({ ...projectDraft, name: event.target.value })} placeholder="Nombre del proyecto" required />
              <input value={projectDraft.folder_path} onChange={(event) => setProjectDraft({ ...projectDraft, folder_path: event.target.value })} placeholder="Carpeta local (opcional, absoluta)" />
              <button type="submit">Crear</button>
            </form>
            {projects.filter((project) => !project.archived).length === 0 ? <p className="muted">Sin proyectos todavia.</p> : <div className="skill-grid">{projects.filter((project) => !project.archived).map((project) => <article className="skill-card project-card" key={project.id}>
              <div className="skill-card-head"><div><strong>{project.name}</strong><span>{project.conversation_count ?? 0} chats · {project.active_task_count ?? 0} tareas activas · {project.attachment_count ?? 0} archivos{project.folder_path ? " · con carpeta" : ""}</span></div></div>
              <p>{project.description || "Sin descripcion."}</p>
              <div className="skill-actions">
                <button className="text-button" onClick={() => { setProjectTab("chats"); openProjectDetail(project.id); }}>Abrir</button>
                <button className="text-button danger" onClick={() => archiveProject(project.id, true)}>Archivar</button>
              </div>
            </article>)}</div>}
            {projects.some((project) => project.archived) && <details className="archived-projects"><summary>Archivados</summary>
              {projects.filter((project) => project.archived).map((project) => <div className="attachment-row" key={project.id}><span>{project.name}</span><button className="text-button" onClick={() => { setProjectTab("chats"); openProjectDetail(project.id); }}>Abrir</button><button className="text-button" onClick={() => archiveProject(project.id, false)}>Desarchivar</button></div>)}
            </details>}
          </>}
          {projectDetail && <>
            <div className="settings-heading-row">
              <div>
                <button className="text-button" onClick={() => setProjectDetail(null)}>← Proyectos</button>
                <h3 className="project-detail-title">{projectDetail.name}{projectDetail.archived ? " (archivado)" : ""}</h3>
                {projectDetail.description && <p className="muted">{projectDetail.description}</p>}
                {projectDetail.folder_path && <p className="muted">Carpeta: <code>{projectDetail.folder_path}</code></p>}
              </div>
              <div className="skill-actions">
                {!projectDetail.archived && <button onClick={() => createProjectChat(projectDetail.id)}>Nuevo chat</button>}
                <button className="deny-button" onClick={() => archiveProject(projectDetail.id, !projectDetail.archived)}>{projectDetail.archived ? "Desarchivar" : "Archivar"}</button>
                <button className="text-button danger" onClick={() => removeProject(projectDetail.id)}>Eliminar</button>
              </div>
            </div>
            <div className="subtabs">
              <button className={projectTab === "chats" ? "active" : ""} onClick={() => setProjectTab("chats")}>Chats</button>
              <button className={projectTab === "tareas" ? "active" : ""} onClick={() => setProjectTab("tareas")}>Tareas</button>
              <button className={projectTab === "conocimiento" ? "active" : ""} onClick={() => setProjectTab("conocimiento")}>Conocimiento</button>
              <button className={projectTab === "instrucciones" ? "active" : ""} onClick={() => setProjectTab("instrucciones")}>Instrucciones</button>
              <button className={projectTab === "memoria" ? "active" : ""} onClick={() => setProjectTab("memoria")}>Memoria</button>
              <button className={projectTab === "archivos" ? "active" : ""} onClick={() => setProjectTab("archivos")}>Archivos</button>
            </div>

            {projectTab === "chats" && <section className="panel">
              <h2>Chats del proyecto</h2>
              <div className="skill-actions"><button onClick={() => createProjectChat(projectDetail.id)}>Nuevo chat en el proyecto</button></div>
              {projectDetail.conversations.length === 0 ? <p className="muted">Sin chats todavia. Cada chat del proyecto hereda sus instrucciones, conocimiento y memoria.</p> : projectDetail.conversations.map((conversation) => <div className="attachment-row" key={conversation.id}>
                <button className="text-button" onClick={() => { setActiveConversationId(conversation.id); setActiveView("chat"); }}>{conversation.title || `Chat ${conversation.id}`}</button>
                <span className="muted">{formatDateTime(conversation.created_at)}</span>
                <button className="text-button danger" onClick={() => projectLinkConversation(projectDetail.id, conversation.id, false)}>Quitar</button>
              </div>)}
              <div className="project-link-row">
                <select value="" onChange={(event) => { const id = Number(event.target.value); if (id) void projectLinkConversation(projectDetail.id, id, true); }}>
                  <option value="">Anadir conversacion existente...</option>
                  {conversations.filter((conversation) => !projectDetail.conversations.some((linked) => linked.id === conversation.id)).map((conversation) => <option value={conversation.id} key={conversation.id}>{conversation.label ?? conversation.title}</option>)}
                </select>
              </div>
            </section>}

            {projectTab === "tareas" && <section className="panel">
              <h2>Tareas del proyecto</h2>
              <form className="task-create" onSubmit={(event) => createProjectTask(projectDetail.id, event)}>
                <input value={projectTaskDraft.goal} onChange={(event) => setProjectTaskDraft({ ...projectTaskDraft, goal: event.target.value })} placeholder="Objetivo de la tarea..." required />
                <select value={projectTaskDraft.mode} onChange={(event) => setProjectTaskDraft({ ...projectTaskDraft, mode: event.target.value })}><option value="act">Act</option><option value="plan">Plan</option><option value="think">Think</option></select>
                <select value={projectTaskDraft.recurrence} onChange={(event) => setProjectTaskDraft({ ...projectTaskDraft, recurrence: event.target.value })}><option value="">Una vez</option><option value="daily">Diaria</option><option value="weekly">Semanal</option></select>
                <input type="datetime-local" value={projectTaskDraft.scheduled_at} onChange={(event) => setProjectTaskDraft({ ...projectTaskDraft, scheduled_at: event.target.value })} title="Programar (opcional)" />
                <button type="submit">Lanzar</button>
              </form>
              <p className="muted">Las tareas heredan las instrucciones del proyecto y los tools operan en su carpeta. Las recurrentes se clonan al completarse.</p>
              {projectTasks.length === 0 ? <p className="muted">Sin tareas en este proyecto.</p> : projectTasks.map((task) => <article className="task-card" key={task.id}>
                <div className="task-card-head">
                  <div><strong>{task.goal}</strong><span className="muted">{task.mode.toUpperCase()}{task.recurrence ? ` · ${task.recurrence === "daily" ? "diaria" : "semanal"}` : ""}{task.attempts > 0 ? ` · intentos: ${task.attempts}` : ""}</span></div>
                  <span className={`chip ${["completed", "failed", "cancelled"].includes(task.status) ? "muted-chip" : "agentic-chip"}`}>{task.status}</span>
                </div>
                {task.error && <p className="muted">Error: {task.error.slice(0, 200)}</p>}
                {task.result && <div className="task-result md-message">{renderMarkdown(task.result)}</div>}
                <div className="skill-actions">
                  {["pending", "scheduled", "running"].includes(task.status) && <button className="text-button" onClick={() => projectTaskAction(projectDetail.id, task.id, "pause")}>Pausar</button>}
                  {["paused", "interrupted", "failed"].includes(task.status) && <button className="text-button" onClick={() => projectTaskAction(projectDetail.id, task.id, "resume")}>Reanudar</button>}
                  {!["completed", "failed", "cancelled"].includes(task.status) && <button className="text-button danger" onClick={() => projectTaskAction(projectDetail.id, task.id, "cancel")}>Cancelar</button>}
                </div>
              </article>)}
            </section>}

            {projectTab === "conocimiento" && <section className="panel">
              <h2>Conocimiento</h2>
              <label className="upload-button">Subir archivo<input type="file" accept="text/plain,text/markdown,text/csv,application/pdf,image/png,image/jpeg,image/webp,image/gif" onChange={(event) => uploadProjectKnowledge(projectDetail.id, event)} /></label>
              <p className="muted">El contenido de estos archivos se inyecta como contexto en todos los chats y tareas del proyecto.</p>
              {projectDetail.attachments.length === 0 ? <p className="muted">Sin archivos todavia.</p> : projectDetail.attachments.map((attachment) => <div className="attachment-row" key={attachment.id}>
                <span>{attachment.file_name}</span>
                <span className="muted">{Math.max(1, Math.round(attachment.size_bytes / 1024))} KB</span>
                <button className="text-button danger" onClick={() => projectLinkAttachment(projectDetail.id, attachment.id, false)}>Quitar</button>
              </div>)}
              <div className="project-link-row">
                <select value="" onChange={(event) => { const id = Number(event.target.value); if (id) void projectLinkAttachment(projectDetail.id, id, true); }}>
                  <option value="">Vincular archivo subido...</option>
                  {attachments.filter((attachment) => !projectDetail.attachments.some((linked) => linked.id === attachment.id)).map((attachment) => <option value={attachment.id} key={attachment.id}>{attachment.file_name}</option>)}
                </select>
              </div>
            </section>}

            {projectTab === "instrucciones" && <section className="panel">
              <h2>Instrucciones del proyecto</h2>
              <textarea rows={6} value={projectInstructionsDraft} onChange={(event) => setProjectInstructionsDraft(event.target.value)} placeholder="Ej: responde en espanol, usa tono formal, sigue la guia de estilo del brief..." />
              <div className="skill-actions"><button onClick={() => void saveProjectInstructions()} disabled={projectInstructionsDraft === projectDetail.instructions}>Guardar instrucciones</button></div>
              <p className="muted">Se aplican a todos los chats y tareas del proyecto.</p>
            </section>}

            {projectTab === "memoria" && <section className="panel">
              <h2>Memoria del proyecto</h2>
              <form className="task-create" onSubmit={(event) => addProjectMemory(projectDetail.id, event)}>
                <input value={projectMemoryDraft} onChange={(event) => setProjectMemoryDraft(event.target.value)} placeholder="Anade algo que ObsyGPT debe recordar SOLO en este proyecto..." required />
                <button type="submit">Anadir</button>
              </form>
              <p className="muted">Esta memoria solo se inyecta en conversaciones y tareas de este proyecto, ademas de tu memoria global.</p>
              {projectMemories.length === 0 ? <p className="muted">Sin memoria de proyecto.</p> : projectMemories.map((memory) => <div className="attachment-row" key={memory.id}>
                <span>{memory.content}</span>
                <button className="text-button danger" onClick={() => deleteProjectMemory(projectDetail.id, memory.id)}>Borrar</button>
              </div>)}
            </section>}

            {projectTab === "archivos" && <section className="panel">
              <h2>Carpeta del proyecto</h2>
              {!projectDetail.folder_path ? <>
                <p className="muted">Sin carpeta asignada: los tools de este proyecto usan tu workspace global, compartido con el resto de trabajos.</p>
                <p className="muted">Al activar una carpeta independiente, los chats y tareas del proyecto crean, editan y ejecutan archivos solo dentro de ella, aislados del resto (como Claude Cowork).</p>
                <div className="skill-actions"><button onClick={() => void enableProjectWorkspace(projectDetail.id)}>Crear carpeta independiente</button></div>
              </> : <>
                <p className="muted">Chats y tareas de este proyecto operan en <code>{projectFiles.folder ?? projectDetail.folder_path}</code>. Los tools no pueden salir de esa carpeta.</p>
                <div className="file-browser-bar">
                  <span className="chip">/{projectFiles.subpath || ""}</span>
                  {projectFiles.parent !== null && <button className="text-button" onClick={() => void refreshProjectFiles(projectDetail.id, projectFiles.parent ?? "")}>↑ Subir</button>}
                  <button className="text-button danger" onClick={() => void unlinkProjectWorkspace(projectDetail.id)}>Desvincular</button>
                </div>
                {projectFiles.entries.length === 0 ? <p className="muted">Carpeta vacía. Pide a ObsyGPT que cree archivos desde un chat del proyecto.</p> : projectFiles.entries.map((entry) => {
                  const entryPath = `${projectFiles.subpath ? `${projectFiles.subpath}/` : ""}${entry.name}`;
                  return <div className="attachment-row" key={entry.name}>
                    {entry.is_dir
                      ? <button className="text-button" onClick={() => void refreshProjectFiles(projectDetail.id, entryPath)}>{entry.name}/</button>
                      : <span>{entry.name}</span>}
                    <span className="muted">{entry.is_dir ? "carpeta" : `${Math.max(1, Math.round(entry.size / 1024))} KB`}</span>
                    <button className="text-button danger" title={entry.is_dir ? "Eliminar carpeta (debe estar vacía)" : "Eliminar archivo"} onClick={() => void deleteProjectFile(projectDetail.id, entryPath, entry.name, projectFiles.subpath)}>Eliminar</button>
                  </div>;
                })}
                <p className="muted">Al eliminar el proyecto, su carpeta independiente (y todo su contenido) se borra también. Si la carpeta es personalizada solo se desvincula.</p>
              </>}
            </section>}
          </>}
        </section>
  );
}
