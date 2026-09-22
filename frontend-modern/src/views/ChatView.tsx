// Auto-extracted from App.tsx: presentational view over useApp() state.
import { MessageItem, LiveActivityBar } from "../components/chat";
import { useApp } from "../state/context";

export function ChatView() {
  const { selectedWorkflowId, setSelectedWorkflowId, metadata, selectedAgentId, setSelectedAgentId, messages, editingMessageIndex, editingMessageDraft, copiedMessageIndex, setEditingMessageDraft, saveEditMessage, cancelEditMessage, copyMessageText, startEditMessage, messageStackRef, messageStackEndRef, pendingApprovals, resumingApprovalId, resumeApproval, habitSuggestions, decideHabitSuggestion, activeProvider, activeModel, selectedAgent, activeProjectName, selectedWorkflow, approximateTokens, liveActivity, sendMessage, paletteOpen, paletteSkills, paletteIndex, selectPaletteSkill, draft, setDraft, setPaletteIndex, handleComposerKeyDown, chatMode, cycleChatMode, handleAttachmentUpload, isStreaming, selectedAttachmentIds } = useApp();
  return (
<section className="chat-column">
          <div className="runtime-selectors">
            <select value={selectedWorkflowId} onChange={(event) => setSelectedWorkflowId(event.target.value)}>
              <option value="">Sin workflow override</option>
              {metadata.workflows.map((workflow) => <option value={workflow.id} key={workflow.id}>{workflow.name} ({workflow.workflow_type})</option>)}
            </select>
            <select value={selectedAgentId} onChange={(event) => setSelectedAgentId(event.target.value)} disabled={Boolean(selectedWorkflowId)}>
              <option value="">Agente por defecto</option>
              {metadata.agents.map((agent) => <option value={agent.id} key={agent.id}>{agent.name}</option>)}
            </select>
          </div>
          <div className="message-stack" ref={messageStackRef}>
            {messages.length === 0 && <div className="empty-state">¿Qué resolvemos hoy?</div>}
            {messages.map((message, index) => (
              <MessageItem
                key={`${message.role}-${index}`}
                message={message}
                index={index}
                isEditing={editingMessageIndex === index}
                editingDraft={editingMessageDraft}
                isCopied={copiedMessageIndex === index}
                onDraftChange={setEditingMessageDraft}
                onSaveEdit={saveEditMessage}
                onCancelEdit={cancelEditMessage}
                onCopy={copyMessageText}
                onEdit={startEditMessage}
              />
            ))}
            <div ref={messageStackEndRef} />
          </div>
          {pendingApprovals.length > 0 && <div className="approval-stack">
            {pendingApprovals.map((approval) => <article className="approval-card" key={approval.id}>
              <div className="approval-head"><strong>Aprobación requerida</strong><span className="chip">{approval.tool_name}</span></div>
              <pre className="approval-args">{JSON.stringify(approval.args, null, 2)}</pre>
              <div className="approval-actions">
                <button className="approve-button" disabled={resumingApprovalId !== null} onClick={() => resumeApproval(approval, true)}>Aprobar y continuar</button>
                <button className="deny-button" disabled={resumingApprovalId !== null} onClick={() => resumeApproval(approval, false)}>Rechazar</button>
              </div>
            </article>)}
          </div>}
          {habitSuggestions.length > 0 && <div className="approval-stack suggestion-stack">
            {habitSuggestions.map((suggestion) => <article className="approval-card suggestion-card" key={suggestion.id}>
              <div className="approval-head"><strong>Hábito detectado</strong><span className="chip">{suggestion.source === "heuristic" ? "patrón de uso" : "análisis IA"}</span></div>
              <p className="suggestion-text">{suggestion.content}</p>
              {suggestion.evidence && <p className="suggestion-evidence">“{suggestion.evidence}”</p>}
              <div className="approval-actions">
                <button className="approve-button" onClick={() => void decideHabitSuggestion(suggestion.id, "accept")}>Guardar hábito</button>
                <button className="deny-button" onClick={() => void decideHabitSuggestion(suggestion.id, "dismiss")}>Descartar</button>
              </div>
            </article>)}
          </div>}
          <div className="runtime-context-bar">
            <span><strong>Provider</strong>{activeProvider?.name ?? "Default"}</span>
            <span><strong>Model</strong>{activeModel?.display_name ?? activeModel?.model_name ?? "Default"}</span>
            <span><strong>Agent</strong>{selectedAgent?.name ?? "Default"}</span>
            {activeProjectName && <span><strong>Proyecto</strong>{activeProjectName}</span>}
            <span><strong>Workflow</strong>{selectedWorkflow?.name ?? "None"}</span>
            <span><strong>Tokens</strong>{approximateTokens.toLocaleString()}</span>
          </div>
          {liveActivity && <LiveActivityBar activity={liveActivity} />}
          <form className="composer" onSubmit={sendMessage}>
            {paletteOpen && <div className="skill-palette">
              {paletteSkills.map((skill, index) => <button type="button" className={index === Math.min(paletteIndex, paletteSkills.length - 1) ? "active" : ""} key={skill.id} onClick={() => selectPaletteSkill(skill.name)}>/&nbsp;{skill.name}<small>{skill.description.slice(0, 60)}</small></button>)}
            </div>}
            <textarea value={draft} onChange={(event) => { setDraft(event.target.value); setPaletteIndex(0); }} onKeyDown={handleComposerKeyDown} placeholder="Escribe a ObsyGPT... o invoca /nombre_skill tarea" />
            <button type="button" className={`mode-button mode-${chatMode}`} onClick={cycleChatMode} title="Ciclar modo (Alt+M)">{chatMode.toUpperCase()}</button>
            <label className="upload-button">Adjuntar<input type="file" accept="text/plain,text/markdown,text/csv,application/pdf,image/png,image/jpeg,image/webp,image/gif" onChange={handleAttachmentUpload} /></label>
            <button disabled={isStreaming}>{isStreaming ? "Generando" : "Enviar"}</button>
          </form>
          {selectedAttachmentIds.length > 0 && <p className="muted">{selectedAttachmentIds.length} adjunto(s) se incluirán en el próximo mensaje.</p>}
        </section>
  );
}
