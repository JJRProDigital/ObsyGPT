// Auto-extracted from App.tsx: presentational view over useApp() state.

import { useApp } from "../state/context";

export function RightRail() {
  const { setRightSidebarOpen, approximateTokens, runs, selectedAgent, selectedWorkflow, activeSkills, activeMcps, toolCalls, attachments, selectedAttachmentIds, setSelectedAttachmentIds, deleteAttachment } = useApp();
  return (
<aside className="right-rail">
        <button className="drawer-close" onClick={() => setRightSidebarOpen(false)}>Cerrar</button>
        <section className="panel"><h2>Consumo</h2><p className="metric">{approximateTokens.toLocaleString()} tokens</p><p className="muted">Estimado por conversaciÃ³n activa.</p>{runs[0] && <p className="run-status">Run #{runs[0].id}: {runs[0].status}</p>}</section>
        <section className="panel"><h2>Agent activo</h2><p>{selectedAgent?.name ?? "Default agent"}</p><p className="muted">Workflow: {selectedWorkflow?.name ?? "Sin override"}</p></section>
        <section className="panel"><h2>Skills activas</h2>{activeSkills.length ? activeSkills.map((skill) => <p key={skill.id}>{skill.name}</p>) : <p className="muted">Ninguna skill asignada.</p>}</section>
        <section className="panel"><h2>MCPs activos</h2>{activeMcps.length ? activeMcps.map((server) => <p key={server.id}>{server.name} ({server.connection_type})</p>) : <p className="muted">NingÃºn MCP asignado.</p>}</section>
        <section className="panel trace-panel"><h2>Tools</h2>{toolCalls.length === 0 ? <p className="muted">Sin tool calls.</p> : toolCalls.slice(0, 6).map((toolCall) => <div className="tool-call" key={toolCall.id}><strong>{toolCall.skill_name}</strong><span>{toolCall.status}: {toolCall.input_summary}</span></div>)}</section>
        <section className="panel"><h2>Files</h2>{attachments.length === 0 ? <p className="muted">Sin adjuntos.</p> : attachments.map((attachment) => <div className="attachment-row" key={attachment.id}>
          <label className="attachment-check" title="Incluir en el prÃ³ximo mensaje"><input type="checkbox" checked={selectedAttachmentIds.includes(attachment.id)} onChange={(event) => setSelectedAttachmentIds((current) => event.target.checked ? [...current, attachment.id] : current.filter((id) => id !== attachment.id))} /><span>{attachment.file_name}</span></label>
          <span className="muted">{Math.max(1, Math.round(attachment.size_bytes / 1024))} KB</span>
          <button className="text-button danger" title="Borrar adjunto para siempre" onClick={() => void deleteAttachment(attachment)}>Borrar</button>
        </div>)}
        {attachments.length > 0 && <p className="muted">Los adjuntos que marques se aÃ±aden al contexto del prÃ³ximo mensaje. Borrar un adjunto elimina el archivo y su texto extraÃ­do; no afecta a los chats que ya lo usaron.</p>}</section>
      </aside>
  );
}
