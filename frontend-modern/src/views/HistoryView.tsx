// Auto-extracted from App.tsx: presentational view over useApp() state.

import { useApp } from "../state/context";

export function HistoryView() {
  const { historySearch, setHistorySearch, conversations, activeConversationId, setActiveConversationId, setActiveView, renameConversation, deleteConversation } = useApp();
  return (
<section className="panel full-panel">
          <h2>Historial</h2>
          <div className="audit-filters"><input value={historySearch} onChange={(event) => setHistorySearch(event.target.value)} placeholder="Buscar conversaciones..." /></div>
          {conversations.filter((conversation) => (conversation.label ?? conversation.title).toLowerCase().includes(historySearch.toLowerCase())).length === 0 ? <p className="muted">Sin conversaciones que coincidan.</p> : conversations.filter((conversation) => (conversation.label ?? conversation.title).toLowerCase().includes(historySearch.toLowerCase())).map((conversation) => (
            <div className="conversation-row history-row" key={conversation.id}>
              <button className={conversation.id === activeConversationId ? "active" : ""} onClick={() => { setActiveConversationId(conversation.id); setActiveView("chat"); }}>{conversation.label ?? conversation.title}</button>
              <button className="text-button" onClick={() => renameConversation(conversation)} type="button">Renombrar</button>
              <button className="text-button danger" onClick={() => deleteConversation(conversation)} type="button">Borrar</button>
            </div>
          ))}
        </section>
  );
}
