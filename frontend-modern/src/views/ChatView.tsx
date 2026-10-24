// Auto-extracted from App.tsx: presentational view over useApp() state.
import { useRef, useState } from "react";
import { MessageItem, LiveActivityBar } from "../components/chat";
import { transcribeAudio, speakText } from "../api";
import { useApp } from "../state/context";

type SuggestionCard = { mode: string; title: string; prompts: string[] };

const SUGGESTION_CARDS: SuggestionCard[] = [
  {
    mode: "ACT",
    title: "Organiza mi esfuerzo",
    prompts: [
      "Planifica mi semana con prioridades",
      "Arma una lista de tareas del proyecto",
      "Diseña una rutina diaria de trabajo enfocado",
      "Haz un balance de qué mejoré esta semana"
    ]
  },
  {
    mode: "PLAN",
    title: "Investiga y compara",
    prompts: [
      "Investiga un tema y resume las 3 claves",
      "Compara 3 alternativas para resolver esto",
      "Busca las noticias de hoy sobre mi sector",
      "Pon pros y contras de cada opción"
    ]
  },
  {
    mode: "THINK",
    title: "Piensa un proyecto",
    prompts: [
      "Haz una revisión general de mi proyecto",
      "Dame ideas creativas para este objetivo",
      "Analiza críticamente este plan",
      "Desglosa este objetivo en pasos concretos"
    ]
  }
];

export function ChatView() {
  const [recording, setRecording] = useState(false);
  const [transcribing, setTranscribing] = useState(false);
  const [speakingIndex, setSpeakingIndex] = useState<number | null>(null);
  const recorderRef = useRef<MediaRecorder | null>(null);
  const chunksRef = useRef<Blob[]>([]);
  const { selectedWorkflowId, setSelectedWorkflowId, metadata, selectedAgentId, setSelectedAgentId, messages, editingMessageIndex, editingMessageDraft, copiedMessageIndex, setEditingMessageDraft, saveEditMessage, cancelEditMessage, copyMessageText, startEditMessage, messageStackRef, messageStackEndRef, pendingApprovals, resumingApprovalId, resumeApproval, habitSuggestions, decideHabitSuggestion, activeProvider, activeModel, selectedAgent, activeProjectName, selectedWorkflow, approximateTokens, liveActivity, sendMessage, paletteOpen, paletteSkills, paletteIndex, selectPaletteSkill, draft, setDraft, setPaletteIndex, handleComposerKeyDown, chatMode, cycleChatMode, handleAttachmentUpload, isStreaming, selectedAttachmentIds, setError } = useApp();

  async function toggleMic() {
    if (recording) {
      recorderRef.current?.stop();
      return;
    }
    try {
      const stream = await navigator.mediaDevices.getUserMedia({ audio: true });
      const recorder = new MediaRecorder(stream);
      chunksRef.current = [];
      recorder.ondataavailable = (event) => { if (event.data.size > 0) chunksRef.current.push(event.data); };
      recorder.onstop = async () => {
        stream.getTracks().forEach((track) => track.stop());
        setRecording(false);
        const blob = new Blob(chunksRef.current, { type: recorder.mimeType || 'audio/webm' });
        if (blob.size < 1000) return;
        setTranscribing(true);
        try {
          const { text } = await transcribeAudio(blob, 'grabacion.webm');
          if (text) setDraft((current) => (current ? `${current} ${text}` : text));
        } catch (err) {
          setError(err instanceof Error ? err.message : 'La transcripci\u00f3n falló');
        } finally {
          setTranscribing(false);
        }
      };
      recorder.start();
      recorderRef.current = recorder;
      setRecording(true);
    } catch {
      setError('No se pudo acceder al micr\u00f3fono. Revisa los permisos del navegador.');
    }
  }

  async   function speakMessage(index: number) {
    const message = messages[index];
    if (!message || speakingIndex !== null || !message.content) return;
    setSpeakingIndex(index);
    const plain = message.content
      .replace(/```[\s\S]*?```/g, " (código omitido) ")
      .replace(/\[([^\]]+)\]\(([^)]+)\)/g, "$1")
      .replace(/^#{1,6}\s+/gm, "")
      .replace(/(\*\*|__)(.*?)\1/g, "$2")
      .replace(/(\*|_)(.*?)\1/g, "$2")
      .replace(/`([^`]+)`/g, "$1")
      .replace(/^---+$/gm, "")
      .replace(/\|/g, " ")
      .replace(/\s{2,}/g, " ")
      .trim();
    if (!plain) {
      setSpeakingIndex(null);
      return;
    }
    try {
      const audio = await speakText(plain);
      audio.onended = () => setSpeakingIndex(null);
      audio.onerror = () => setSpeakingIndex(null);
      void audio.play();
    } catch (err) {
      setSpeakingIndex(null);
      setError(err instanceof Error ? err.message : 'La síntesis de voz falló');
    }
  }

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
            {messages.length === 0 && <div className="chat-hero">
              <div className="hero-mark">OS</div>
              <h2>&#191;Por d&#243;nde empezamos?</h2>
              <p className="muted">Escrib&#237; tu objetivo abajo o eleg&#237; un atajo para empezar ahora mismo.</p>
              <div className="hero-cards">
                {SUGGESTION_CARDS.map((card) => <div className="hero-card" key={card.mode}>
                  <p className="hero-card-title">{card.title}<span className="chip">{card.mode}</span></p>
                  <ul>
                    {card.prompts.map((prompt) => <li key={prompt}><button type="button" onClick={() => setDraft(prompt)}>{prompt}</button></li>)}
                  </ul>
                </div>)}
              </div>
            </div>}
            {messages.map((message, index) => (
              <MessageItem
                key={`${message.role}-${index}`}
                message={message}
                index={index}
                isEditing={editingMessageIndex === index}
                editingDraft={editingMessageDraft}
                isCopied={copiedMessageIndex === index}
                onSpeak={speakMessage}
                speaking={speakingIndex === index}
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
            <button type="button" className={`mic-button${recording ? " recording" : ""}`} onClick={() => void toggleMic()} title={recording ? "Detener grabación" : "Hablar"} disabled={transcribing || isStreaming}>{transcribing ? "..." : recording ? "●" : <svg width="15" height="15" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.8" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true"><rect x="9" y="3" width="6" height="11" rx="3" /><path d="M5 11a7 7 0 0014 0" /><path d="M12 18v3" /></svg>}</button>
            <button type="button" className={`mode-button mode-${chatMode}`} onClick={cycleChatMode} title="Ciclar modo (Alt+M)">{chatMode.toUpperCase()}</button>
            <label className="upload-button">Adjuntar<input type="file" accept="text/plain,text/markdown,text/csv,application/pdf,image/png,image/jpeg,image/webp,image/gif" onChange={handleAttachmentUpload} /></label>
            <button disabled={isStreaming}>{isStreaming ? "Generando" : "Enviar"}</button>
          </form>
          {selectedAttachmentIds.length > 0 && <p className="muted">{selectedAttachmentIds.length} adjunto(s) se incluirán en el próximo mensaje.</p>}
        </section>
  );
}
