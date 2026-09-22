// Auto-extracted from App.tsx: presentational view over useApp() state.

import { useApp } from "../state/context";

export function MemoryView() {
  const { addMemory, memoryDraft, setMemoryDraft, habitSuggestions, decideHabitSuggestion, memories, deleteMemory } = useApp();
  return (
<section className="panel full-panel">
          <h2>Memoria</h2>
          <form className="task-create" onSubmit={addMemory}>
            <input value={memoryDraft.content} onChange={(event) => setMemoryDraft({ ...memoryDraft, content: event.target.value })} placeholder="Anade algo que ObsyGPT debe recordar..." required />
            <select value={memoryDraft.kind} onChange={(event) => setMemoryDraft({ ...memoryDraft, kind: event.target.value })}><option value="memory">Memoria</option><option value="habit">Habito</option></select>
            <button type="submit">Anadir</button>
          </form>
          {habitSuggestions.length > 0 && <>
            <h3>HÃ¡bitos detectados ({habitSuggestions.length})</h3>
            {habitSuggestions.map((suggestion) => <div className="suggestion-row" key={suggestion.id}>
              <div className="suggestion-copy">
                <span>{suggestion.content}</span>
                {suggestion.evidence && <small className="muted">â€œ{suggestion.evidence}â€ Â· {suggestion.source === "heuristic" ? "patrÃ³n de uso" : "anÃ¡lisis IA"}</small>}
              </div>
              <div className="skill-actions">
                <button className="text-button" onClick={() => void decideHabitSuggestion(suggestion.id, "accept")}>Guardar</button>
                <button className="text-button danger" onClick={() => void decideHabitSuggestion(suggestion.id, "dismiss")}>Descartar</button>
              </div>
            </div>)}
          </>}
          {memories.length === 0 ? <p className="muted">Sin memorias guardadas. Lo que anadas aqui se inyecta en cada conversacion.</p> : <>
            <h3>Memorias</h3>
            {memories.filter((item) => item.kind === "memory").map((item) => <div className="attachment-row" key={item.id}><span>{item.content}</span><button className="text-button danger" onClick={() => deleteMemory(item.id)}>Borrar</button></div>)}
            <h3>Habitos</h3>
            {memories.filter((item) => item.kind === "habit").map((item) => <div className="attachment-row" key={item.id}><span>{item.content}</span><button className="text-button danger" onClick={() => deleteMemory(item.id)}>Borrar</button></div>)}
          </>}
        </section>
  );
}
