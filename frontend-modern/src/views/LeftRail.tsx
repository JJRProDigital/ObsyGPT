// Auto-extracted from App.tsx: presentational view over useApp() state.
import { HealthLine } from "../components/shared";
import { useApp } from "../state/context";

export function LeftRail() {
  const { session, isAdmin, activeView, setActiveView, leftSidebarCollapsed, setLeftSidebarCollapsed, createConversation, activeTaskCount, memories, folders, conversations, expandedFolders, toggleFolderExpanded, renameFolder, deleteFolder, activeConversationId, setActiveConversationId, renameConversation, deleteConversation, moveConversation, createFolder, userMenuOpen, setUserMenuOpen, openSettings, setSettingsTab, setSettingsSection, logout, health, navButton } = useApp();
  return (
      <aside className="left-rail">
        <div className="sidebar-top-actions">
          <button className="icon-button" onClick={() => setLeftSidebarCollapsed((value) => !value)} aria-label="Toggle sidebar">{leftSidebarCollapsed ? "☰" : "‹"}</button>
          {!leftSidebarCollapsed && <button className="new-chat-button" onClick={() => { setActiveView("chat"); void createConversation(); }}>Nuevo chat</button>}
          {leftSidebarCollapsed && <button className="icon-button" onClick={() => { setActiveView("chat"); void createConversation(); }} aria-label="New chat">＋</button>}
        </div>
        {!leftSidebarCollapsed && <div className="sidebar-product"><span className="sidebar-product-mark">OS</span><span>ObsyGPT</span></div>}
        <nav className="primary-nav">
          <div className="nav-group">
            {!leftSidebarCollapsed && <p className="nav-group-label">Principal</p>}
            {navButton("chat", "Chat")}
          </div>
          <div className="nav-group">
            {!leftSidebarCollapsed && <p className="nav-group-label">Trabajo</p>}
            {navButton("tasks", "Tareas", "Ta", activeTaskCount)}
            {navButton("projects", "Proyectos", "Pr")}
            {navButton("trace", "Traza", "Tr")}
          </div>
          <div className="nav-group">
            {!leftSidebarCollapsed && <p className="nav-group-label">Conocimiento</p>}
            {navButton("memory", "Memoria", "Me", memories.length)}
            {navButton("skills", "Skills", "Sk")}
            {navButton("tools", "Herram.", "Hz")}
            {navButton("connectors", "Conect.", "Cx")}
          </div>
          <div className="nav-group">
            {!leftSidebarCollapsed && <p className="nav-group-label">Sistema</p>}
            {navButton("history", "Historial", "Hi")}
            {navButton("settings", "Ajustes", "Aj")}
            {isAdmin && navButton("monitoring", "Monitor", "Mo")}
          </div>
        </nav>
        {!leftSidebarCollapsed && <div className="conversation-list-block"><div className="sidebar-list-head"><p className="eyebrow">Conversaciones ({conversations.length})</p><button className="text-button new-folder-button" onClick={() => void createFolder()}>+ Carpeta</button></div>{conversations.length === 0 ? <p className="empty-sidebar-note">No hay conversaciones para {session!.username}.</p> : <nav>
          {folders.map((folder) => {
            const folderConversations = conversations.filter((conversation) => conversation.folder_id === folder.id);
            const expanded = expandedFolders.includes(folder.id);
            return (
              <div className="folder-group" key={folder.id}>
                <div className="folder-head">
                  <button className="folder-toggle" onClick={() => toggleFolderExpanded(folder.id)}>{expanded ? "▾" : "▸"} {folder.name} ({folderConversations.length})</button>
                  <button className="text-button" onClick={() => void renameFolder(folder)} type="button" title="Renombrar carpeta">✎</button>
                  <button className="text-button danger" onClick={() => void deleteFolder(folder)} type="button" title="Eliminar carpeta">×</button>
                </div>
                {expanded && folderConversations.map((conversation) => (
                  <div className="conversation-row" key={conversation.id}>
                    <button className={conversation.id === activeConversationId ? "active" : ""} onClick={() => { setActiveView("chat"); setActiveConversationId(conversation.id); }}>
                      {conversation.label ?? conversation.title}
                    </button>
                    <button className="text-button" onClick={() => renameConversation(conversation)} type="button" title="Renombrar chat">✎</button>
                    <button className="text-button danger" onClick={() => deleteConversation(conversation)} type="button" title="Borrar chat">×</button>
                    <select className="folder-select" value={conversation.folder_id ?? ""} onChange={(event) => { const value = event.target.value; void moveConversation(conversation, value ? Number(value) : null); }} title="Mover a carpeta">
                      <option value="">—</option>
                      {folders.map((folder) => <option value={folder.id} key={folder.id}>{folder.name}</option>)}
                    </select>
                  </div>
                ))}
              </div>
            );
          })}
          {folders.length > 0 && <p className="eyebrow folder-group-label">Sin carpeta</p>}
          {conversations.filter((conversation) => !conversation.folder_id).map((conversation) => (
            <div className="conversation-row" key={conversation.id}>
              <button className={conversation.id === activeConversationId ? "active" : ""} onClick={() => { setActiveView("chat"); setActiveConversationId(conversation.id); }}>
                {conversation.label ?? conversation.title}
              </button>
              <button className="text-button" onClick={() => renameConversation(conversation)} type="button" title="Renombrar chat">✎</button>
              <button className="text-button danger" onClick={() => deleteConversation(conversation)} type="button" title="Borrar chat">×</button>
              <select className="folder-select" value={conversation.folder_id ?? ""} onChange={(event) => { const value = event.target.value; void moveConversation(conversation, value ? Number(value) : null); }} title="Mover a carpeta">
                <option value="">—</option>
                {folders.map((folder) => <option value={folder.id} key={folder.id}>{folder.name}</option>)}
              </select>
            </div>
          ))}
        </nav>}</div>}
        {!leftSidebarCollapsed && <div className="sidebar-account">
          <button className="user-menu-trigger" aria-expanded={userMenuOpen} aria-haspopup="menu" onClick={() => setUserMenuOpen((value) => !value)}>
            <strong>{session!.username}</strong>
            <span>{isAdmin ? "Admin" : "User"}</span>
          </button>
          {userMenuOpen && <div className="user-menu">
            {isAdmin && <button onClick={() => { openSettings("agents"); setUserMenuOpen(false); }}>Configuración</button>}
            {isAdmin && <button onClick={() => { setSettingsTab("admin"); setSettingsSection("audit"); setActiveView("settings"); setUserMenuOpen(false); }}>Audit logs</button>}
            {isAdmin && <button onClick={() => { setActiveView("diagnostics"); setUserMenuOpen(false); }}>Diagnostics</button>}
            <button onClick={logout}>Cerrar sesión</button>
          </div>}
          <HealthLine health={health} />
        </div>}
        {leftSidebarCollapsed && <div className="collapsed-account">
          <button className="logout icon-button" onClick={() => setUserMenuOpen((value) => !value)} aria-label="User menu" aria-expanded={userMenuOpen} aria-haspopup="menu">{session!.username.slice(0, 1).toUpperCase()}</button>
          {userMenuOpen && <div className="user-menu collapsed-menu">
            {isAdmin && <button onClick={() => { setLeftSidebarCollapsed(false); openSettings("agents"); setUserMenuOpen(false); }}>Configuración</button>}
            {isAdmin && <button onClick={() => { setLeftSidebarCollapsed(false); setSettingsTab("admin"); setSettingsSection("audit"); setActiveView("settings"); setUserMenuOpen(false); }}>Audit logs</button>}
            {isAdmin && <button onClick={() => { setLeftSidebarCollapsed(false); setActiveView("diagnostics"); setUserMenuOpen(false); }}>Diagnostics</button>}
            <button onClick={logout}>Cerrar sesión</button>
          </div>}
        </div>}
      </aside>
  );
}
