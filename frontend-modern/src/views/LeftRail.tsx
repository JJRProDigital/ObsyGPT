// Auto-extracted from App.tsx: presentational view over useApp() state.
import { HealthLine } from "../components/shared";
import { useState } from "react";
import { useApp } from "../state/context";

const DOCS_URL: string = (import.meta as { env?: Record<string, string | undefined> }).env?.VITE_DOCS_URL ?? "http://localhost:8010/";

export function LeftRail() {
  const [rowMenu, setRowMenu] = useState<{ id: number; top: number; right: number } | null>(null);
  const [folderMenu, setFolderMenu] = useState<{ id: number; top: number; right: number } | null>(null);
  function menuAnchor(event: React.MouseEvent) {
    const rect = (event.currentTarget as HTMLElement).getBoundingClientRect();
    return { top: Math.min(rect.bottom + 4, window.innerHeight - 280), right: window.innerWidth - rect.right };
  }
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
            {!leftSidebarCollapsed && <a className="nav-docs-link" href={DOCS_URL} target="_blank" rel="noreferrer" title="Documentación de ObsyGPT"><span aria-hidden="true">?</span>Ayuda / Docs</a>}
            {leftSidebarCollapsed && <a className="nav-docs-link" href={DOCS_URL} target="_blank" rel="noreferrer" title="Documentación de ObsyGPT">?</a>}
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
                  <button className="icon-button row-menu-trigger" aria-label="Opciones de carpeta" onClick={(event) => setFolderMenu(folderMenu?.id === folder.id ? null : { id: folder.id, ...menuAnchor(event) })}><svg width="16" height="16" viewBox="0 0 24 24" fill="currentColor" aria-hidden="true"><circle cx="12" cy="5" r="1.8"/><circle cx="12" cy="12" r="1.8"/><circle cx="12" cy="19" r="1.8"/></svg></button>
                  {folderMenu?.id === folder.id && <>
                    <div className="menu-backdrop" onClick={() => setFolderMenu(null)} />
                    <div className="row-menu" style={{ top: folderMenu.top, right: folderMenu.right }}>
                      <button onClick={() => { void renameFolder(folder); setFolderMenu(null); }}>Renombrar</button>
                      <div className="row-menu-sep" /><button className="danger" onClick={() => { void deleteFolder(folder); setFolderMenu(null); }}>Eliminar</button>
                    </div>
                  </>}
                </div>
                {expanded && folderConversations.map((conversation) => (
                  <div className="conversation-row" key={conversation.id}>
                    <button className={conversation.id === activeConversationId ? "active" : ""} onClick={() => { setActiveView("chat"); setActiveConversationId(conversation.id); }}>
                      {conversation.label ?? conversation.title}
                    </button>
                    <button className="icon-button row-menu-trigger" aria-label="Opciones" onClick={(event) => setRowMenu(rowMenu?.id === conversation.id ? null : { id: conversation.id, ...menuAnchor(event) })}><svg width="16" height="16" viewBox="0 0 24 24" fill="currentColor" aria-hidden="true"><circle cx="12" cy="5" r="1.8"/><circle cx="12" cy="12" r="1.8"/><circle cx="12" cy="19" r="1.8"/></svg></button>
                    {rowMenu?.id === conversation.id && <>
                      <div className="menu-backdrop" onClick={() => setRowMenu(null)} />
                      <div className="row-menu" style={{ top: rowMenu.top, right: rowMenu.right }}>
                        <button onClick={() => { renameConversation(conversation); setRowMenu(null); }}>Renombrar</button>
                        <p className="row-menu-section">Mover a carpeta</p>
                        <button className="move-option" onClick={() => { void moveConversation(conversation, null); setRowMenu(null); }}>Sin carpeta</button>
                        {folders.map((folder) => <button className="move-option" key={folder.id} onClick={() => { void moveConversation(conversation, folder.id); setRowMenu(null); }}>{folder.name}</button>)}
                        <div className="row-menu-sep" /><button className="danger" onClick={() => { void deleteConversation(conversation); setRowMenu(null); }}>Eliminar</button>
                      </div>
                    </>}
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
              <button className="icon-button row-menu-trigger" aria-label="Opciones" onClick={(event) => setRowMenu(rowMenu?.id === conversation.id ? null : { id: conversation.id, ...menuAnchor(event) })}><svg width="16" height="16" viewBox="0 0 24 24" fill="currentColor" aria-hidden="true"><circle cx="12" cy="5" r="1.8"/><circle cx="12" cy="12" r="1.8"/><circle cx="12" cy="19" r="1.8"/></svg></button>
                    {rowMenu?.id === conversation.id && <>
                      <div className="menu-backdrop" onClick={() => setRowMenu(null)} />
                      <div className="row-menu" style={{ top: rowMenu.top, right: rowMenu.right }}>
                        <button onClick={() => { renameConversation(conversation); setRowMenu(null); }}>Renombrar</button>
                        <p className="row-menu-section">Mover a carpeta</p>
                        <button className="move-option" onClick={() => { void moveConversation(conversation, null); setRowMenu(null); }}>Sin carpeta</button>
                        {folders.map((folder) => <button className="move-option" key={folder.id} onClick={() => { void moveConversation(conversation, folder.id); setRowMenu(null); }}>{folder.name}</button>)}
                        <div className="row-menu-sep" /><button className="danger" onClick={() => { void deleteConversation(conversation); setRowMenu(null); }}>Eliminar</button>
                      </div>
                    </>}
            </div>
          ))}
        </nav>}</div>}
        {!leftSidebarCollapsed && <div className="sidebar-account">
          <button className="user-menu-trigger" aria-expanded={userMenuOpen} aria-haspopup="menu" onClick={() => setUserMenuOpen((value) => !value)}>
            <strong>{session!.username}</strong>
            <span>{isAdmin ? "Admin" : "User"}</span>
          </button>
          {userMenuOpen && <div className="user-menu">
            <a className="user-menu-docs" href={DOCS_URL} target="_blank" rel="noreferrer" onClick={() => setUserMenuOpen(false)}>Documentación y ayuda</a>
            {isAdmin && <button onClick={() => { openSettings("agents"); setUserMenuOpen(false); }}>Configuración</button>}
            {isAdmin && <button onClick={() => { setSettingsTab("admin"); setSettingsSection("audit"); setActiveView("settings"); setUserMenuOpen(false); }}>Audit logs</button>}
            {isAdmin && <button onClick={() => { setActiveView("diagnostics"); setUserMenuOpen(false); }}>Diagnostics</button>}
            <button onClick={logout}>Cerrar sesión</button>
          </div>}
          <HealthLine health={health} />
          <p className="muted build-hash">build {(document.querySelector("script[type='module'][src]")?.getAttribute("src") ?? "").match(/index-([^.]+)\.js/)?.[1] ?? "?"}</p>
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
