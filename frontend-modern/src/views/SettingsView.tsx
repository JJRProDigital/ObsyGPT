// Auto-extracted from App.tsx: presentational view over useApp() state.
import { useCallback, useEffect, useState } from "react";
import { apiRequest } from "../api";
import { ConfigForm, ModelCheckResult } from "../components/shared";
import { useApp } from "../state/context";

const ICONS: Record<string, React.ReactElement> = {
  modelo: <><path d="M4 8h10M18 8h2M4 16h4M12 16h8" /><circle cx="16" cy="8" r="2" /><circle cx="10" cy="16" r="2" /></>,
  preferencias: <><circle cx="12" cy="8" r="3.5" /><path d="M5 20c1.2-3.2 3.8-5 7-5s5.8 1.8 7 5" /></>,
  seguridad: <><path d="M12 3l7 3v5c0 4.8-3.2 7.6-7 9.5C8.2 18.6 5 15.8 5 11V6z" /><path d="M9.5 11.5l2 2 3.5-4" /></>,
  sistema: <><rect x="7" y="7" width="10" height="10" rx="2" /><path d="M12 3v3M12 18v3M3 12h3M18 12h3M5.5 5.5l2 2M16.5 16.5l2 2M18.5 5.5l-2 2M7.5 16.5l-2 2" /></>,
  agentes: <><rect x="5" y="8" width="14" height="11" rx="3" /><path d="M12 8V4M9 4h6" /><circle cx="9.5" cy="13" r="1" /><circle cx="14.5" cy="13" r="1" /></>,
  triggers: <path d="M13 2L4.5 13.5H11L10 22l8.5-11.5H12z" />,
  datos: <><ellipse cx="12" cy="5.5" rx="7" ry="2.8" /><path d="M5 5.5v13c0 1.5 3.1 2.8 7 2.8s7-1.3 7-2.8v-13M5 12c0 1.5 3.1 2.8 7 2.8s7-1.3 7-2.8" /></>,
  admin: <><rect x="4" y="4" width="7" height="7" rx="1.5" /><rect x="13" y="4" width="7" height="7" rx="1.5" /><rect x="4" y="13" width="7" height="7" rx="1.5" /><rect x="13" y="13" width="7" height="7" rx="1.5" /></>,
  agents: <><rect x="5" y="8" width="14" height="11" rx="3" /><path d="M12 8V4M9 4h6" /><circle cx="9.5" cy="13" r="1" /><circle cx="14.5" cy="13" r="1" /></>,
  models: <><path d="M12 3l9 5-9 5-9-5z" /><path d="M3 13l9 5 9-5" /></>,
  workflows: <><circle cx="6" cy="6" r="2.5" /><circle cx="18" cy="18" r="2.5" /><path d="M6 8.5V15a3 3 0 003 3h6.5" /></>,
  mcps: <><path d="M9 7V3M15 7V3" /><rect x="6" y="7" width="12" height="8" rx="2" /><path d="M12 15v6" /></>,
  plugins: <><path d="M10 4h4v3a2 2 0 104 0h3v4h-3a2 2 0 100 4h3v4h-4a2 2 0 10-4 0H4v-4a2 2 0 100-4H4V8h3a2 2 0 103 0z" /></>,
  users: <><circle cx="9" cy="8.5" r="3" /><path d="M3.5 19c.9-2.8 3-4.3 5.5-4.3s4.6 1.5 5.5 4.3" /><circle cx="16.5" cy="9.5" r="2.4" /><path d="M16 14.7c2.2.2 3.9 1.6 4.6 3.8" /></>,
  audit: <><circle cx="12" cy="12" r="8.5" /><path d="M12 7v5l3.5 2" /></>,
};

function ChipIcon({ name }: { name: string }) {
  return (
    <svg className="chip-svg" viewBox="0 0 24 24" width="14" height="14" fill="none" stroke="currentColor" strokeWidth="1.8" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true">
      {ICONS[name] ?? <circle cx="12" cy="12" r="8" />}
    </svg>
  );
}

type EmbeddingsConfig = { mode: string; base_url: string; model: string; api_key_env: string };
type ReindexStatus = { running: boolean; processed: number; total: number; error: string | null };

function EmbeddingsSection({ isAdmin }: { isAdmin: boolean }) {
  const [config, setConfig] = useState<EmbeddingsConfig | null>(null);
  const [status, setStatus] = useState<ReindexStatus | null>(null);
  const [saving, setSaving] = useState(false);
  const [saved, setSaved] = useState(false);

  const load = useCallback(async () => {
    if (!isAdmin) return;
    try {
      const data = await apiRequest<{ embeddings: EmbeddingsConfig }>("/api/admin/settings/embeddings");
      setConfig(data.embeddings);
    } catch { }
    try {
      const data = await apiRequest<{ reindex: ReindexStatus }>("/api/admin/embeddings/reindex");
      setStatus(data.reindex);
    } catch { }
  }, [isAdmin]);

  useEffect(() => {
    load().catch(() => undefined);
  }, [load]);

  useEffect(() => {
    if (!status?.running) return;
    const interval = setInterval(() => {
      apiRequest<{ reindex: ReindexStatus }>("/api/admin/embeddings/reindex")
        .then((data) => setStatus(data.reindex))
        .catch(() => undefined);
    }, 2000);
    return () => clearInterval(interval);
  }, [status?.running]);

  if (!isAdmin) return <section className="panel"><h2>Embeddings (memoria semántica)</h2><p className="muted">Solo un administrador puede gestionar los embeddings.</p></section>;
  if (!config) return null;

  const save = async () => {
    setSaving(true);
    setSaved(false);
    try {
      const data = await apiRequest<{ embeddings: EmbeddingsConfig }>("/api/admin/settings/embeddings", { method: "PUT", body: JSON.stringify(config) });
      setConfig(data.embeddings);
      setSaved(true);
    } catch { } finally {
      setSaving(false);
    }
  };

  const reindex = async () => {
    try {
      const data = await apiRequest<{ reindex: ReindexStatus }>("/api/admin/embeddings/reindex", { method: "POST" });
      setStatus(data.reindex);
    } catch { }
  };

  return (
    <section className="panel">
      <h2>Embeddings (memoria semántica)</h2>
      <div className="config-form">
        <label>
          Modo
          <select value={config.mode || "local"} onChange={(event) => setConfig({ ...config, mode: event.target.value })}>
            <option value="local">Local (rápido, sin API key)</option>
            <option value="endpoint">Endpoint compatible con OpenAI</option>
          </select>
        </label>
        {config.mode === "endpoint" && (
          <>
            <label>
              Base URL
              <input value={config.base_url || ""} onChange={(event) => setConfig({ ...config, base_url: event.target.value })} placeholder="http://host:8000/v1" />
            </label>
            <label>
              Modelo
              <input value={config.model || ""} onChange={(event) => setConfig({ ...config, model: event.target.value })} placeholder="nombre-del-modelo" />
            </label>
            <label>
              Variable de entorno con la API key (opcional)
              <input value={config.api_key_env || ""} onChange={(event) => setConfig({ ...config, api_key_env: event.target.value })} placeholder="EMBEDDINGS_API_KEY" />
            </label>
          </>
        )}
        <div>
          <button type="button" onClick={() => { void save(); }} disabled={saving}>{saving ? "Guardando..." : "Guardar cambios"}</button>
          {saved && <span className="chip">Guardado</span>}
        </div>
        <div>
          <button type="button" onClick={() => { void reindex(); }} disabled={Boolean(status?.running)}>Reindexar memoria</button>
          {status?.running && <span className="chip">{status.processed}/{status.total} procesados</span>}
          {status && !status.running && status.error && <span className="chip">{status.error}</span>}
          {status && !status.running && !status.error && status.processed > 0 && <span className="chip">Último reindexado: {status.processed}/{status.total}</span>}
        </div>
      </div>
    </section>
  );
}

type ApiKeyRow = { id: number; name: string; prefix: string; created_at: string; last_used_at: string | null; revoked_at: string | null };

function ApiKeysSection({ formatDateTime }: { formatDateTime: (value: string) => string }) {
  const [keys, setKeys] = useState<ApiKeyRow[] | null>(null);
  const [name, setName] = useState("");
  const [creating, setCreating] = useState(false);
  const [createdKey, setCreatedKey] = useState<string | null>(null);
  const [copied, setCopied] = useState(false);
  const [actionError, setActionError] = useState<string | null>(null);

  const load = useCallback(async () => {
    try {
      const data = await apiRequest<{ api_keys: ApiKeyRow[] }>("/api/admin/api-keys");
      setKeys(data.api_keys);
    } catch { }
  }, []);

  useEffect(() => {
    load().catch(() => undefined);
  }, [load]);

  const create = async () => {
    const trimmed = name.trim();
    if (!trimmed) return;
    setCreating(true);
    setActionError(null);
    try {
      const data = await apiRequest<{ api_key: { key: string } }>("/api/admin/api-keys", { method: "POST", body: JSON.stringify({ name: trimmed }) });
      setCreatedKey(data.api_key.key);
      setCopied(false);
      setName("");
      await load();
    } catch {
      setActionError("No se pudo crear la clave.");
    } finally {
      setCreating(false);
    }
  };

  const revoke = async (key: ApiKeyRow) => {
    if (!window.confirm(`¿Revocar la clave "${key.name}"? Dejará de funcionar inmediatamente.`)) return;
    setActionError(null);
    try {
      await apiRequest<{ revoked: boolean }>(`/api/admin/api-keys/${key.id}/revoke`, { method: "POST" });
      await load();
    } catch {
      setActionError("No se pudo revocar la clave. Inténtalo de nuevo.");
    }
  };

  const copyCreated = async () => {
    if (!createdKey) return;
    try {
      await navigator.clipboard.writeText(createdKey);
      setCopied(true);
    } catch {
      const node = document.getElementById("api-key-plaintext");
      if (node) {
        const range = document.createRange();
        range.selectNodeContents(node);
        const selection = window.getSelection();
        if (selection) {
          selection.removeAllRanges();
          selection.addRange(range);
        }
      }
    }
  };

  return (
    <section className="panel">
      <h2>Claves de API</h2>
      <p className="muted">Claves personales para conectar herramientas compatibles con OpenAI (endpoint /v1). Solo se guarda un hash de cada clave: la clave completa se muestra únicamente al crearla.</p>
      <form className="config-form" onSubmit={(event) => { event.preventDefault(); void create(); }}>
        <label>
          Nombre
          <input value={name} onChange={(event) => setName(event.target.value)} placeholder="p. ej. Integración VS Code" required />
        </label>
        <div>
          <button type="submit" disabled={creating}>{creating ? "Creando..." : "Crear clave"}</button>
        </div>
      </form>
      {actionError && <p className="error" role="alert" style={{ marginTop: "10px" }}>{actionError}</p>}
      {createdKey && (
        <div style={{ margin: "6px 0 4px", padding: "10px 12px", borderRadius: "8px", border: "1px solid rgba(213, 176, 109, 0.45)", background: "rgba(213, 176, 109, 0.08)" }}>
          <code id="api-key-plaintext" style={{ fontFamily: "var(--mono)", fontSize: "0.82rem", overflowWrap: "anywhere", display: "block" }}>{createdKey}</code>
          <div className="chip-row" style={{ marginTop: "8px" }}>
            <button type="button" onClick={() => { void copyCreated(); }}>{copied ? "Copiado" : "Copiar"}</button>
            <button type="button" className="text-button" onClick={() => { setCreatedKey(null); setCopied(false); }}>Ocultar</button>
          </div>
          <p className="muted" style={{ margin: "8px 0 0" }}>Guárdala ahora: no volverá a mostrarse.</p>
        </div>
      )}
      {keys === null ? <p className="muted">Cargando claves...</p> : keys.length === 0 ? <p className="muted">Todavía no tienes claves.</p> : keys.map((key) => (
        <div className="attachment-row" key={key.id}>
          <span className="suggestion-copy">
            <b>{key.name}</b>
            <small className="muted" style={{ fontFamily: "var(--mono)" }}>ogpt-{key.prefix}****</small>
            <small className="muted">Creada: {formatDateTime(key.created_at)}{key.last_used_at ? ` · Último uso: ${formatDateTime(key.last_used_at)}` : " · Sin uso registrado"}</small>
          </span>
          {key.revoked_at && <span className="chip muted-chip">Revocada</span>}
          {!key.revoked_at && <button type="button" className="text-button" onClick={() => { void revoke(key); }}>Revocar</button>}
        </div>
      ))}
    </section>
  );
}

export function SettingsView() {
  const { settingsTabDefs, settingsTab, setSettingsTab, adminSections, settingsSection, setSettingsSection, isAdmin, settingsSearch, setSettingsSearch, activeModel, activeProvider, settingsResults, metadata, selectedAgent, activateModel, createProvider, saveProviderKey, providerDraft, setProviderDraft, providerKeyDrafts, setProviderKeyDrafts, detectingProvider, detectProviderModels, detectedModels, toggleProvider, setPreferences, savePreferences, preferences, saveWorkspace, workspaceDraft, setWorkspaceDraft, workspaceInfo, toolDefinitions, saveGuardrails, guardrailDraft, setGuardrailDraft, tasksSettings, setTasksSettings, saveTasksSettings, resetHabits, createAgent, agentDraft, setAgentDraft, editAgent, agentEditId, agentEditDraft, setAgentEditDraft, saveAgentEdit, toggleAgent, toggleAgentAgentic, skillAgents, toggleAgentSkill, agentTools, toggleAgentTool, toggleAgentMcp, agentFallbacks, fallbackDraft, setFallbackDraft, addAgentFallback, removeAgentFallback, createModel, modelDraft, setModelDraft, toggleModel, deleteModel, checkModel, modelCheckResult, createWorkflow, workflowDraft, setWorkflowDraft, toggleWorkflow, createMcpServer, mcpDraft, setMcpDraft, validateMcpServer, mcpValidation, runMcpServer, mcpRunDraft, setMcpRunDraft, mcpRunResult, mcpInspection, inspectingMcp, inspectMcpServer, deleteMcpServer, toggleMcpServer, pluginMessage, addPluginMarketplace, marketplaceDraft, setMarketplaceDraft, pluginMarketplaces, pluginBusy, refreshPluginMarketplace, removePluginMarketplace, pluginCatalog, missingConnectorsFor, installPluginEntry, uninstallPluginEntry, updateUserRole, adminCreateUser, userCreateDraft, setUserCreateDraft, auditLogs, auditFilters, setAuditFilters, refreshWorkspace, auditLogLimit, setAuditLogLimit, formatAuditMetadata, formatDateTime, setAgentEditId, telegramBotUsername, telegramVerifying, verifyAgentTelegram,
  triggers, triggerDraft, setTriggerDraft, createTrigger, toggleTrigger, removeTrigger, settingsSubTab, settingsSubTabs, setSettingsSubTab, workflowEditId, setWorkflowEditId, workflowEditDraft, setWorkflowEditDraft, startWorkflowEdit, saveWorkflowEdit, deleteWorkflow } = useApp();
  return (
<section className="settings-layout settings-modern">
          <div className="settings-topbar">
            <div className="settings-chips">
              {settingsTabDefs.filter((tab) => tab.id !== "admin" && (tab.id !== "agentes" || isAdmin)).map((tab) => (
                <button key={tab.id} className={settingsTab === tab.id ? "chip active" : "chip"} onClick={() => { setSettingsTab(tab.id); setSettingsSubTab(""); }}><ChipIcon name={tab.id} />{tab.label}</button>
              ))}
              {isAdmin && adminSections.map((section) => (
                <button key={section.id} className={settingsTab === "admin" && settingsSection === section.id ? "chip active" : "chip"} onClick={() => { setSettingsTab("admin"); setSettingsSection(section.id); setSettingsSubTab(""); }}><ChipIcon name={section.id} />{section.label}</button>
              ))}
            </div>
          </div>
          <div className="settings-content">
            <div className="settings-heading">
              <div className="settings-heading-row">
                <input className="settings-search" value={settingsSearch} onChange={(event) => setSettingsSearch(event.target.value)} placeholder="Buscar en ajustes..." />
              </div>
              <div className="active-model-card">
                <div className="ac-main"><b>{activeModel?.display_name ?? activeModel?.model_name ?? "Sin modelo activo"}</b><small>{activeProvider?.name ?? "Elige un proveedor y activa un modelo para empezar."}</small></div>
                <span className={`ac-badge ${activeModel?.enabled && activeProvider?.enabled ? "on" : "off"}`}>{activeModel?.enabled && activeProvider?.enabled ? "activo" : "sin activar"}</span>
              </div>
            </div>
            {(settingsSubTabs[settingsTab]?.length ?? 0) > 0 && <div className="settings-subtabs">{settingsSubTabs[settingsTab].map((group) => <button key={group.id} type="button" className={settingsSubTab === group.id ? "active" : ""} onClick={() => setSettingsSubTab(group.id)}>{group.label}</button>)}</div>}
            {settingsSearch.trim() !== "" && <section className="panel"><h2>Resultados</h2>{settingsResults.length === 0 ? <p className="muted">Ningún ajuste coincide con esa búsqueda.</p> : settingsResults.map((item) => <button type="button" className="settings-result" key={item.label} onClick={() => { setSettingsTab(item.tab); if (item.section) setSettingsSection(item.section); setSettingsSubTab(item.sub ?? ""); setSettingsSearch(""); }}>{item.label}<small>{settingsTabDefs.find((tab) => tab.id === item.tab)?.label}</small></button>)}</section>}
            {settingsSearch.trim() === "" && settingsTab === "modelo" && (settingsSubTab === "" || settingsSubTab === "activar") && <section className="panel"><h2>Proveedor y modelo</h2><p className="muted">Selecciona proveedor, detecta modelos y activa uno para el agente por defecto.</p><div className="modelo-controls">
              <select value={String(selectedAgent?.provider_id ?? "")} onChange={(event) => { const providerId = Number(event.target.value); const firstModel = metadata.models.find((model) => model.enabled && model.provider_id === providerId); if (isAdmin && providerId && firstModel) { void activateModel(providerId, firstModel.id); } }}><option value="">Proveedor...</option>{metadata.providers.filter((provider) => provider.enabled).map((provider) => <option value={provider.id} key={provider.id}>{provider.name}</option>)}</select>
              <select value={String(selectedAgent?.model_id ?? "")} onChange={(event) => { const modelId = Number(event.target.value); const providerId = selectedAgent?.provider_id ?? metadata.providers.find((provider) => provider.enabled)?.id; if (isAdmin && modelId && providerId) { void activateModel(providerId, modelId); } }}><option value="">Modelo...</option>{metadata.models.filter((model) => model.enabled && model.provider_id === (selectedAgent?.provider_id ?? -1)).map((model) => <option value={model.id} key={model.id}>{model.display_name}</option>)}</select>
            </div>{!isAdmin && <p className="muted">Solo un admin puede activar modelos.</p>}</section>}
            {settingsSearch.trim() === "" && settingsTab === "modelo" && (settingsSubTab === "" || settingsSubTab === "proveedores") && <section className="panel"><h2>Proveedores guardados</h2>{isAdmin && <ConfigForm onSubmit={createProvider} submitLabel="Añadir provider"><input value={providerDraft.name} onChange={(event) => setProviderDraft({ ...providerDraft, name: event.target.value })} placeholder="Provider name" required /><select value={providerDraft.provider_type} onChange={(event) => setProviderDraft({ ...providerDraft, provider_type: event.target.value })}>{metadata.providerDefinitions.map((definition) => <option value={definition.provider_type} key={definition.provider_type}>{definition.display_name}</option>)}</select><input value={providerDraft.base_url} onChange={(event) => setProviderDraft({ ...providerDraft, base_url: event.target.value })} placeholder="Base URL" /><input type="password" value={providerDraft.api_key} onChange={(event) => setProviderDraft({ ...providerDraft, api_key: event.target.value })} placeholder="API key (opcional, se guarda cifrada)" autoComplete="new-password" /><input value={providerDraft.api_key_env} onChange={(event) => setProviderDraft({ ...providerDraft, api_key_env: event.target.value })} placeholder="API key env var (alternativa)" /><label><input type="checkbox" checked={providerDraft.enabled} onChange={(event) => setProviderDraft({ ...providerDraft, enabled: event.target.checked })} /> Enabled</label></ConfigForm>}{metadata.providers.map((provider) => <div className="provider-row-block" key={provider.id}><label className="attachment-row"><span>{provider.name} ({provider.provider_type})</span>{provider.api_key_set && <span className="chip">Clave guardada</span>}{isAdmin && <button type="button" className="text-button" disabled={detectingProvider !== null} onClick={() => detectProviderModels(provider.id)}>{detectingProvider === provider.id ? "Detectando..." : "Detectar modelos"}</button>}{isAdmin && <input type="checkbox" checked={provider.enabled} onChange={(event) => toggleProvider(provider, event.target.checked)} />}</label>{isAdmin && <div className="provider-key-row"><input type="password" value={providerKeyDrafts[provider.id] ?? ""} onChange={(event) => setProviderKeyDrafts({ ...providerKeyDrafts, [provider.id]: event.target.value })} placeholder={provider.api_key_set ? "Reemplazar clave guardada" : "Pegar API key (se guarda cifrada)"} autoComplete="new-password" /><button type="button" className="text-button" disabled={!(providerKeyDrafts[provider.id] ?? "").trim()} onClick={() => void saveProviderKey(provider)}>Guardar clave</button></div>}{detectedModels[provider.id] && <div className="detect-results">{detectedModels[provider.id].slice(0, 12).map((model) => <span className={`chip ${model.already_registered ? "muted-chip" : ""}`} key={model.model_name}>{model.model_name}{model.already_registered ? " · registrado" : ""}</span>)}</div>}</div>)}</section>}

            {settingsSearch.trim() === "" && settingsTab === "modelo" && settingsSubTab === "embeddings" && <EmbeddingsSection isAdmin={isAdmin} />}

            {settingsSearch.trim() === "" && settingsTab === "preferencias" && <><section className="panel"><h2>Instrucciones para ObsyGPT</h2><p className="muted">ObsyGPT tendrá esto en cuenta en todos los chats siempre que no entren en conflicto con lo que pidas en la conversación. No se aplicará a las tareas en segundo plano ni a los workflows.</p>
            <div className="instructions-block">
              <textarea className="instructions-textarea" rows={6} value={preferences?.instructions ?? ""} onChange={(event) => setPreferences((current) => (current ? { ...current, instructions: event.target.value } : current))} onBlur={() => void savePreferences({ instructions: preferences?.instructions ?? "" })} placeholder="Ej.: responde siempre en español, sé breve y directo, cita las fuentes con enlaces, usa tablas para comparativas..." />
              <div className="instructions-meta"><span className="muted">Se guarda al salir del campo</span><span className="muted">{(preferences?.instructions ?? "").length}/4000</span></div>
            </div></section>
            <section className="panel"><h2>Personal</h2><div className="swrow"><span className="st"><b>Tu nombre</b><small>ObsyGPT lo usa para dirigirse a ti y personalizar el contexto.</small></span><input value={preferences?.display_name ?? ""} onChange={(event) => setPreferences((current) => (current ? { ...current, display_name: event.target.value } : current))} onBlur={() => void savePreferences({ display_name: preferences?.display_name ?? "" })} placeholder="Tu nombre" /></div><div className="swrow"><span className="st"><b>Color de acento</b><small>Tiñe bordes, chips y botones de toda la interfaz.</small></span><select value={preferences?.accent ?? "gold"} onChange={(event) => void savePreferences({ accent: event.target.value })}><option value="gold">Oro</option><option value="teal">Teal</option><option value="violet">Violeta</option><option value="magenta">Magenta</option><option value="ice">Hielo</option></select></div></section>
            <section className="panel"><h2>Espacio de trabajo</h2><p className="muted">Carpeta donde el agente crea archivos y ejecuta comandos. Las rutas relativas aterrizan aqui.</p><form className="task-create" onSubmit={saveWorkspace}><input value={workspaceDraft} onChange={(event) => setWorkspaceDraft(event.target.value)} placeholder="C:\ruta\absoluta\del\proyecto" /><button type="submit" disabled={workspaceDraft === (workspaceInfo?.workspace ?? "")}>Guardar</button></form>{workspaceInfo && <><p className="muted">Activo: <code>{workspaceInfo.workspace}</code>{workspaceInfo.workspace !== workspaceInfo.default ? <> · por defecto: <code>{workspaceInfo.default}</code></> : null}</p>{workspaceInfo.recent.length > 0 && <div className="chip-row">{workspaceInfo.recent.map((recent) => <button type="button" className="chip" key={recent} onClick={() => setWorkspaceDraft(recent)}>{recent}</button>)}</div>}</>}</section>
            <section className="panel"><h2>Atajos</h2><div className="swrow"><span className="st"><b>Cambiar de modo (Act / Plan / Think)</b></span><span className="kbd">Alt</span><span className="kbd">M</span></div><div className="swrow"><span className="st"><b>Paleta de skills en el chat</b></span><span className="kbd">/</span></div></section></>}

            {settingsSearch.trim() === "" && settingsTab === "seguridad" && (settingsSubTab === "" || settingsSubTab === "permisos") && <section className="panel"><h2>Permisos por herramienta</h2><p className="muted">Definen qué puede hacer el agente sin preguntarte: las seguras se ejecutan solas, las sensibles piden aprobacion salvo que las bloquees o las permitas siempre. Permisos por agente en Administracion, Agents.</p><div className="policy-list">{toolDefinitions.map((tool) => { const policy = preferences?.tool_policies?.[tool.name] ?? (tool.permission === "sensitive" ? "ask" : "allow"); const v1Enabled = preferences?.tool_v1_access?.[tool.name] ?? (policy !== "ask" && tool.permission === "safe"); return <div className="policy-row" key={tool.name}><span className="st"><b>{tool.name}</b><small>{tool.permission === "safe" ? "Segura" : "Sensible"}</small></span><select value={policy} onChange={(event) => void savePreferences({ tool_policies: { ...(preferences?.tool_policies ?? {}), [tool.name]: event.target.value } })}><option value="allow">Permitir siempre</option><option value="ask">Preguntar antes</option><option value="block">Bloqueado</option></select>{tool.permission === "safe" && <label className="v1-toggle" title="Permite que el agente use esta herramienta cuando lo llaman por la API /v1"><input type="checkbox" checked={v1Enabled} onChange={(event) => void savePreferences({ tool_v1_access: { ...(preferences?.tool_v1_access ?? {}), [tool.name]: event.target.checked } })} /> V1</label>}</div>; })}</div></section>}
            {settingsSearch.trim() === "" && settingsTab === "seguridad" && (settingsSubTab === "" || settingsSubTab === "limites") && <section className="panel"><h2>Límites de ejecución</h2>{!isAdmin ? <p className="muted">Admin role required.</p> : <ConfigForm onSubmit={saveGuardrails} submitLabel="Guardar límites"><label>NÚM. ITERACIONES MÁX.<input type="number" min="1" value={guardrailDraft.max_iterations ?? ""} onChange={(event) => setGuardrailDraft({ ...guardrailDraft, max_iterations: event.target.value ? Number(event.target.value) : undefined })} /></label><label>LLAMADAS A HERRAMIENTAS MÁX.<input type="number" min="1" value={guardrailDraft.max_tool_calls ?? ""} onChange={(event) => setGuardrailDraft({ ...guardrailDraft, max_tool_calls: event.target.value ? Number(event.target.value) : undefined })} /></label><label>DURACIÓN MÁXIMA (SEG.)<input type="number" min="1" value={guardrailDraft.max_duration_seconds ?? ""} onChange={(event) => setGuardrailDraft({ ...guardrailDraft, max_duration_seconds: event.target.value ? Number(event.target.value) : undefined })} /></label><label>REPETICIONES DE UNA ACCIÓN = BUCLE<input type="number" min="2" value={guardrailDraft.loop_repeat_limit ?? ""} onChange={(event) => setGuardrailDraft({ ...guardrailDraft, loop_repeat_limit: event.target.value ? Number(event.target.value) : undefined })} /></label></ConfigForm>}<p className="muted">Al alcanzar un límite la ejecución se detiene y queda explicada en el chat.</p></section>}

            {settingsSearch.trim() === "" && settingsTab === "seguridad" && settingsSubTab === "api" && <ApiKeysSection formatDateTime={formatDateTime} />}

            {settingsSearch.trim() === "" && settingsTab === "sistema" && (settingsSubTab === "" || settingsSubTab === "memoria") && <section className="panel"><h2>Memoria</h2><div className="swrow"><span className="st"><b>Recuerdos por conversación (1-100)</b><small>Cuánta memoria persistente entra en cada mensaje.</small></span><input type="number" min="1" max="100" value={preferences?.memory_max ?? 30} onChange={(event) => setPreferences((current) => (current ? { ...current, memory_max: Number(event.target.value) || 30 } : current))} onBlur={() => void savePreferences({ memory_max: preferences?.memory_max ?? 30 })} /></div></section>}
            {settingsSearch.trim() === "" && settingsTab === "sistema" && (settingsSubTab === "" || settingsSubTab === "tareas") && <section className="panel"><h2>Tareas en segundo plano</h2>{!isAdmin ? <p className="muted">Admin role required.</p> : <><div className="swrow"><span className="st"><b>Tareas simultáneas (1-4)</b><small>Cuántas tareas puede ejecutar a la vez.</small></span><select value={String(tasksSettings.max_concurrent_tasks)} onChange={(event) => setTasksSettings({ ...tasksSettings, max_concurrent_tasks: Number(event.target.value) })}><option value="1">1</option><option value="2">2</option><option value="3">3</option><option value="4">4</option></select></div><div className="swrow"><span className="st"><b>Recuperar tareas interrumpidas al arrancar</b><small>Se reanudan solas con reintentos acotados.</small></span><label className="switch-row"><input type="checkbox" checked={tasksSettings.auto_resume_tasks} onChange={(event) => setTasksSettings({ ...tasksSettings, auto_resume_tasks: event.target.checked })} /> Activado</label></div><button onClick={() => void saveTasksSettings()}>Guardar</button></>}</section>}

            {settingsSearch.trim() === "" && settingsTab === "triggers" && (settingsSubTab === "" || settingsSubTab === "lista") && <section className="panel"><h2>Triggers (proactividad)</h2><p className="muted">Los triggers despiertan a un agente sin que le escribas: cada cierto tiempo, cuando cambia una web o feed, o vía webhook. El agente corre en modo lectura (solo tools seguras) salvo que desactives el candado.</p>{triggers.length === 0 && <p className="muted">Todavía no tienes triggers.</p>}{triggers.map((trigger) => <div className="trigger-row" key={trigger.id}><div><b>{trigger.name}</b> <span className="muted">· {trigger.trigger_type} · agente #{trigger.agent_id}{trigger.config?.time_of_day ? ` · brief diario ${trigger.config.time_of_day}` : ""}{trigger.notify_channel === "telegram" ? ` · avisa por Telegram (${trigger.notify_chat_id})` : ""}{trigger.last_fired_at ? ` · último disparo: ${new Date(trigger.last_fired_at).toLocaleString()}` : " · sin disparos"}</span><small className="muted block">{trigger.goal_template.length > 160 ? `${trigger.goal_template.slice(0, 160)}...` : trigger.goal_template}{trigger.trigger_type === "webhook" && trigger.webhook_secret && <span className="block">Webhook: POST /api/triggers/{trigger.id}/fire — header X-Trigger-Secret: <code>{trigger.webhook_secret}</code></span>}</small></div><div className="skill-actions"><label className="switch-row"><input type="checkbox" checked={trigger.enabled} onChange={(event) => void toggleTrigger(trigger, event.target.checked)} /> {trigger.enabled ? "Activo" : "Pausado"}</label><button type="button" className="text-button" onClick={() => void removeTrigger(trigger.id)}>Eliminar</button></div></div>)}</section>}
            {settingsSearch.trim() === "" && settingsTab === "triggers" && (settingsSubTab === "" || settingsSubTab === "nuevo") && <section className="panel"><h2>Nuevo trigger</h2><form className="config-form" onSubmit={(event) => void createTrigger(event)}><input value={triggerDraft.name} onChange={(event) => setTriggerDraft({ ...triggerDraft, name: event.target.value })} placeholder="Nombre del trigger" required /><select value={triggerDraft.agent_id} onChange={(event) => setTriggerDraft({ ...triggerDraft, agent_id: event.target.value })} required><option value="">Agente...</option>{metadata.agents.filter((agent) => agent.enabled).map((agent) => <option value={agent.id} key={agent.id}>{agent.name}</option>)}</select><select value={triggerDraft.trigger_type} onChange={(event) => setTriggerDraft({ ...triggerDraft, trigger_type: event.target.value as typeof triggerDraft.trigger_type })}><option value="interval">Intervalo fijo</option><option value="change_detection">Vigilar cambio (URL/RSS)</option><option value="webhook">Webhook (lo dispara un sistema externo)</option></select>{triggerDraft.trigger_type !== "webhook" && <label>{triggerDraft.time_of_day ? "Intervalo (minutos) — anulado por la hora fija" : "Intervalo (minutos)"}<input type="number" min="1" max="10080" value={triggerDraft.interval_minutes} disabled={Boolean(triggerDraft.time_of_day)} onChange={(event) => setTriggerDraft({ ...triggerDraft, interval_minutes: event.target.value })} /></label>}{triggerDraft.trigger_type === "interval" && <label>Hora(s) fija(s) diaria(s) (opcional): dispara a esas horas en vez de por intervalo. Separa varias con comas: 08:00, 14:00, 20:00<input type="text" value={triggerDraft.time_of_day} placeholder="08:00 o 08:00, 14:00, 20:00" onChange={(event) => setTriggerDraft({ ...triggerDraft, time_of_day: event.target.value })} /></label>}{triggerDraft.trigger_type === "change_detection" && <><select value={triggerDraft.source_type} onChange={(event) => setTriggerDraft({ ...triggerDraft, source_type: event.target.value as "url" | "rss" })}><option value="rss">Feed RSS</option><option value="url">Página web</option></select><input value={triggerDraft.source_url} onChange={(event) => setTriggerDraft({ ...triggerDraft, source_url: event.target.value })} placeholder="https://..." required /></>}<textarea className="full-width" rows={4} value={triggerDraft.goal_template} onChange={(event) => setTriggerDraft({ ...triggerDraft, goal_template: event.target.value })} placeholder="Qué debe hacer el agente cuando se dispare (ej: 'Resume las novedades y avísame cuáles importan')" required /><div className="skill-actions full-width"><select value={triggerDraft.notify_channel} onChange={(event) => setTriggerDraft({ ...triggerDraft, notify_channel: event.target.value as "" | "telegram" })}><option value="">Sin notificación (solo UI)</option><option value="telegram">Avisar por Telegram</option></select>{triggerDraft.notify_channel === "telegram" && <input value={triggerDraft.notify_chat_id} onChange={(event) => setTriggerDraft({ ...triggerDraft, notify_chat_id: event.target.value })} placeholder="Chat ID de Telegram" />}</div><label className="switch-row"><input type="checkbox" checked={triggerDraft.readonly} onChange={(event) => setTriggerDraft({ ...triggerDraft, readonly: event.target.checked })} /> Modo lectura (solo tools seguras) — recomendado</label><div className="skill-actions full-width"><button type="submit">Crear trigger</button></div></form></section>}

            {settingsSearch.trim() === "" && settingsTab === "agentes" && <section className="panel"><h2>Agentes</h2><p className="muted">Cada agente define proveedor, modelo, skills, tools y fallbacks. Despliega uno para editarlo.</p>{!isAdmin && <p className="muted">Admin role required.</p>}{isAdmin && <details className="agent-create-block"><summary>Crear agent</summary><ConfigForm onSubmit={createAgent} submitLabel="Crear agent"><input value={agentDraft.name} onChange={(event) => setAgentDraft({ ...agentDraft, name: event.target.value })} placeholder="Agent name" required /><textarea value={agentDraft.system_prompt} onChange={(event) => setAgentDraft({ ...agentDraft, system_prompt: event.target.value })} placeholder="System prompt" required /><input value={agentDraft.description} onChange={(event) => setAgentDraft({ ...agentDraft, description: event.target.value })} placeholder="Description" /><select value={agentDraft.provider_id} onChange={(event) => setAgentDraft({ ...agentDraft, provider_id: event.target.value })}><option value="">No provider override</option>{metadata.providers.map((provider) => <option value={provider.id} key={provider.id}>{provider.name}</option>)}</select><select value={agentDraft.model_id} onChange={(event) => setAgentDraft({ ...agentDraft, model_id: event.target.value })}><option value="">No model override</option>{metadata.models.map((model) => <option value={model.id} key={model.id}>{model.display_name}</option>)}</select><label><input type="checkbox" checked={agentDraft.internet_enabled} onChange={(event) => setAgentDraft({ ...agentDraft, internet_enabled: event.target.checked })} /> Internet (skills web)</label><label><input type="checkbox" checked={agentDraft.multimodal_enabled} onChange={(event) => setAgentDraft({ ...agentDraft, multimodal_enabled: event.target.checked })} /> Multimodal</label><label><input type="checkbox" checked={agentDraft.agentic_mode} onChange={(event) => setAgentDraft({ ...agentDraft, agentic_mode: event.target.checked })} /> Agentic (tools)</label></ConfigForm></details>}{metadata.agents.map((agent) => { const agentProvider = agent.provider_id ? metadata.providers.find((provider) => provider.id === agent.provider_id) : null; const agentModel = agent.model_id ? metadata.models.find((model) => model.id === agent.model_id) : null; return <details className="agent-block" key={agent.id}><summary><strong>{agent.name}</strong>{agent.agentic_mode && <span className="chip agentic-chip">agentic</span>}<span className="agent-meta">{[agentProvider?.name, agentModel?.display_name ?? agentModel?.model_name].filter(Boolean).join(" · ") || "Sin provider/modelo"}</span>{isAdmin && <input type="checkbox" className="agent-enabled" checked={agent.enabled} title={agent.enabled ? "Activado" : "Desactivado"} onClick={(event) => event.stopPropagation()} onChange={(event) => toggleAgent(agent, event.target.checked)} />}</summary><div className="agent-block-body">{isAdmin && <label className="switch-row"><input type="checkbox" checked={Boolean(agent.agentic_mode)} onChange={(event) => toggleAgentAgentic(agent, event.target.checked)} /> Modo agentic</label>}{isAdmin && (agentEditId === agent.id ? <form className="config-form agent-edit-form" onSubmit={(event) => void saveAgentEdit(agent, event)}><label className="full-width">Nombre<input value={agentEditDraft.name} onChange={(event) => setAgentEditDraft({ ...agentEditDraft, name: event.target.value })} placeholder="Nombre del agente" required /></label><label className="full-width">Descripción<input value={agentEditDraft.description} onChange={(event) => setAgentEditDraft({ ...agentEditDraft, description: event.target.value })} placeholder="Descripción" /></label><textarea className="full-width" rows={6} value={agentEditDraft.system_prompt} onChange={(event) => setAgentEditDraft({ ...agentEditDraft, system_prompt: event.target.value })} placeholder="System prompt: personalidad, reglas y estilo de las respuestas" required /><label>Proveedor<select value={agentEditDraft.provider_id} onChange={(event) => setAgentEditDraft({ ...agentEditDraft, provider_id: event.target.value, model_id: "" })}><option value="">Sin provider</option>{metadata.providers.map((provider) => <option value={provider.id} key={provider.id}>{provider.name}</option>)}</select></label><label>Modelo<select value={agentEditDraft.model_id} onChange={(event) => setAgentEditDraft({ ...agentEditDraft, model_id: event.target.value })}><option value="">Sin modelo</option>{metadata.models.filter((model) => !agentEditDraft.provider_id || model.provider_id === Number(agentEditDraft.provider_id)).map((model) => <option value={model.id} key={model.id}>{model.display_name}</option>)}</select></label><label>TEMPERATURA<input type="number" step="0.1" min="0" max="2" value={agentEditDraft.temperature} onChange={(event) => setAgentEditDraft({ ...agentEditDraft, temperature: event.target.value })} /></label><label><input type="checkbox" checked={agentEditDraft.internet_enabled} onChange={(event) => setAgentEditDraft({ ...agentEditDraft, internet_enabled: event.target.checked })} /> Internet (skills web)</label><label><input type="checkbox" checked={agentEditDraft.multimodal_enabled} onChange={(event) => setAgentEditDraft({ ...agentEditDraft, multimodal_enabled: event.target.checked })} /> Multimodal</label><div className="skill-actions full-width telegram-block"><label><input type="checkbox" checked={agentEditDraft.telegram_enabled} onChange={(event) => setAgentEditDraft({ ...agentEditDraft, telegram_enabled: event.target.checked })} /> Telegram (bot propio del agente)</label><label>Token del bot (de @BotFather)<input type="password" autoComplete="new-password" value={agentEditDraft.telegram_bot_token} onChange={(event) => setAgentEditDraft({ ...agentEditDraft, telegram_bot_token: event.target.value })} placeholder={agent.telegram_bot_token_set ? "Token guardado — dejar vacío para conservarlo" : "Token del bot (de @BotFather)"} /></label><label>Allowlist (telegram_id:usuario)<input value={agentEditDraft.telegram_allowlist} onChange={(event) => setAgentEditDraft({ ...agentEditDraft, telegram_allowlist: event.target.value })} placeholder="Allowlist: 123456789:usuario_obsygpt, 987654321:otro_usuario" /></label><div className="skill-actions"><button type="button" className="text-button" disabled={telegramVerifying !== null} onClick={() => void verifyAgentTelegram(agent.id)}>{telegramVerifying === agent.id ? "Verificando..." : "Probar token"}</button>{telegramBotUsername && telegramVerifying === null && agentEditId === agent.id && <span className="muted">Bot conectado: @{telegramBotUsername}</span>}</div></div><div className="skill-actions full-width"><button type="submit">Guardar cambios</button><button type="button" className="text-button" onClick={() => setAgentEditId(null)}>Cancelar</button></div></form> : <div className="skill-actions"><button className="text-button" onClick={() => editAgent(agent)}>Editar nombre, prompt y modelo</button></div>)}<div className="agent-caps"><div><strong>Skills</strong>{metadata.skills.map((skill) => { const checked = metadata.agentSkills.some((assignment) => assignment.agent_id === agent.id && assignment.skill_id === skill.id); return <label key={skill.id}><input type="checkbox" checked={checked} disabled={!isAdmin} onChange={(event) => toggleAgentSkill(agent.id, skill.id, event.target.checked)} /> {skill.name}</label>; })}</div><div><strong>MCPs</strong>{metadata.mcpServers.length === 0 ? <span className="muted">No MCP servers registered.</span> : metadata.mcpServers.map((server) => { const checked = metadata.agentMcps.some((assignment) => assignment.agent_id === agent.id && assignment.mcp_server_id === server.id); return <label key={server.id}><input type="checkbox" checked={checked} disabled={!isAdmin} onChange={(event) => toggleAgentMcp(agent.id, server.id, event.target.checked)} /> {server.name}</label>; })}</div><div><strong>Tools</strong>{toolDefinitions.length === 0 ? <span className="muted">No tools registered.</span> : toolDefinitions.map((tool) => { const toolChecked = agentTools.some((assignment) => assignment.agent_id === agent.id && assignment.tool_name === tool.name && assignment.allowed); return <label key={tool.name}><input type="checkbox" checked={toolChecked} disabled={!isAdmin || !agent.agentic_mode} onChange={(event) => toggleAgentTool(agent.id, tool.name, event.target.checked)} /> {tool.name} ({tool.permission})</label>; })}</div></div><div className="detect-block"><strong>Fallbacks</strong>{agentFallbacks.filter((item) => item.agent_id === agent.id).length === 0 ? <span className="muted">Sin cadena de fallback.</span> : <div className="chip-row">{agentFallbacks.filter((item) => item.agent_id === agent.id).sort((a, b) => a.priority - b.priority).map((fallback) => <span className="chip" key={`${fallback.provider_id}-${fallback.model_id}`}>{fallback.model_display_name} <button type="button" className="text-button danger" disabled={!isAdmin} onClick={() => removeAgentFallback(agent.id, fallback)}>x</button></span>)}</div>}{isAdmin && <span className="fallback-add"><select value={fallbackDraft[agent.id]?.provider_id ?? ""} onChange={(event) => setFallbackDraft((current) => ({ ...current, [agent.id]: { provider_id: event.target.value, model_id: "" } }))}><option value="">Provider</option>{metadata.providers.filter((provider) => provider.enabled).map((provider) => <option value={provider.id} key={provider.id}>{provider.name}</option>)}</select><select value={fallbackDraft[agent.id]?.model_id ?? ""} onChange={(event) => setFallbackDraft((current) => ({ ...current, [agent.id]: { ...current[agent.id], model_id: event.target.value } }))}><option value="">Model</option>{metadata.models.filter((model) => model.enabled && model.provider_id === Number(fallbackDraft[agent.id]?.provider_id)).map((model) => <option value={model.id} key={model.id}>{model.display_name}</option>)}</select><button type="button" className="text-button" disabled={!fallbackDraft[agent.id]?.provider_id || !fallbackDraft[agent.id]?.model_id} onClick={() => addAgentFallback(agent.id)}>Añadir</button></span>}</div></div></details>; })}</section>}

            {settingsSearch.trim() === "" && settingsTab === "modelo" && settingsSubTab === "modelos" && <section className="panel"><h2>Models</h2>{isAdmin && <ConfigForm onSubmit={createModel} submitLabel="Añadir model"><select value={modelDraft.provider_id} onChange={(event) => setModelDraft({ ...modelDraft, provider_id: event.target.value })} required><option value="">Provider</option>{metadata.providers.map((provider) => <option value={provider.id} key={provider.id}>{provider.name}</option>)}</select><input value={modelDraft.model_name} onChange={(event) => setModelDraft({ ...modelDraft, model_name: event.target.value })} placeholder="Model ID" required /><input value={modelDraft.display_name} onChange={(event) => setModelDraft({ ...modelDraft, display_name: event.target.value })} placeholder="Display name" required /><input value={modelDraft.context_window} onChange={(event) => setModelDraft({ ...modelDraft, context_window: event.target.value })} placeholder="Context window" type="number" min="1" /><label><input type="checkbox" checked={modelDraft.supports_vision} onChange={(event) => setModelDraft({ ...modelDraft, supports_vision: event.target.checked })} /> Vision</label><label><input type="checkbox" checked={modelDraft.supports_audio} onChange={(event) => setModelDraft({ ...modelDraft, supports_audio: event.target.checked })} /> Audio</label><label><input type="checkbox" checked={modelDraft.supports_tools} onChange={(event) => setModelDraft({ ...modelDraft, supports_tools: event.target.checked })} /> Tools</label><label><input type="checkbox" checked={modelDraft.supports_json} onChange={(event) => setModelDraft({ ...modelDraft, supports_json: event.target.checked })} /> JSON</label><label><input type="checkbox" checked={modelDraft.enabled} onChange={(event) => setModelDraft({ ...modelDraft, enabled: event.target.checked })} /> Enabled</label></ConfigForm>}{metadata.models.map((model) => <span className="attachment-row muted" key={model.id}><span>{model.display_name}</span>{isAdmin && <button className="text-button" type="button" onClick={() => checkModel(model)}>Check</button>}{isAdmin && <button className="text-button danger" type="button" onClick={() => deleteModel(model)}>Borrar</button>}{isAdmin && <input type="checkbox" checked={model.enabled} onChange={(event) => toggleModel(model, event.target.checked)} />}</span>)}{modelCheckResult && <ModelCheckResult result={modelCheckResult} />}</section>}

            {settingsSearch.trim() === "" && settingsTab === "datos" && <><section className="panel"><h2>Hábitos aprendidos</h2><p className="muted">Patrones que ObsyGPT detecta en tus chats (análisis IA y frecuencias de uso) y que tú apruebas, más los que añadas a mano desde Memoria. Los aprobados se inyectan en todas las conversaciones. Nada sale de tu equipo.</p><button className="deny-button" onClick={() => void resetHabits()}>Reiniciar hábitos aprendidos</button></section>
            <section className="panel"><h2>Carpeta de datos</h2><p className="muted">Configuración, memoria, skills y tareas viven en la base de datos y en <code>{workspaceInfo?.default ?? "workspace/"}</code>.</p></section></>}

            {settingsSearch.trim() === "" && settingsTab === "admin" && <>


                        

            {settingsSection === "workflows" && <section className="panel"><h2>Workflows</h2><p className="muted">Un workflow encadena agentes para responder una misma consulta. <b>Single agent</b>: un solo agente. <b>Sequential</b>: uno tras otro, cada uno ve la salida del anterior. <b>Reviewer</b>: uno escribe y otro revisa. <b>Supervisor</b>: un coordinador reparte el trabajo. <b>Parallel</b>: todos responden a la vez y se combinan. <b>Debate</b>: debaten entre ellos y un juez decide.</p>{isAdmin && <ConfigForm onSubmit={createWorkflow} submitLabel="Crear workflow"><label>Nombre<input value={workflowDraft.name} onChange={(event) => setWorkflowDraft({ ...workflowDraft, name: event.target.value })} placeholder="Nombre del workflow" required /></label><label>Tipo<select value={workflowDraft.workflow_type} onChange={(event) => setWorkflowDraft({ ...workflowDraft, workflow_type: event.target.value })}><option value="single_agent">Single agent</option><option value="sequential">Sequential</option><option value="reviewer">Reviewer</option><option value="supervisor">Supervisor</option><option value="parallel">Parallel</option><option value="debate">Debate</option></select></label><label className="full-width">Agentes (el orden de selecci&#243;n define los pasos)<select multiple value={workflowDraft.agent_ids.map(String)} onChange={(event) => setWorkflowDraft({ ...workflowDraft, agent_ids: Array.from(event.currentTarget.selectedOptions).map((option) => Number(option.value)) })}>{metadata.agents.map((agent) => <option value={agent.id} key={agent.id}>{agent.name}</option>)}</select></label></ConfigForm>}{metadata.workflows.length === 0 && <p className="muted">Todav&#237;a no hay workflows.</p>}{metadata.workflows.map((workflow) => { const steps = metadata.workflowSteps.filter((step) => step.workflow_id === workflow.id).sort((a, b) => a.step_order - b.step_order); return <div className="provider-row-block" key={workflow.id}><label className="attachment-row"><span><b>{workflow.name}</b> <span className="muted">· {workflow.workflow_type} · {steps.length} paso{steps.length === 1 ? "" : "s"}</span></span><span className="skill-actions">{isAdmin && <button type="button" className="text-button" onClick={() => startWorkflowEdit(workflow)}>Editar</button>}{isAdmin && <button type="button" className="text-button danger" onClick={() => void deleteWorkflow(workflow)}>Borrar</button>}{isAdmin && <input type="checkbox" checked={workflow.enabled} onChange={(event) => toggleWorkflow(workflow, event.target.checked)} />}</span></label><div className="detect-results">{steps.length === 0 ? <span className="chip muted-chip">sin pasos — editalo para agregar agentes</span> : steps.map((step, index) => { const agent = metadata.agents.find((item) => item.id === step.agent_id); return <span className="chip" key={`${workflow.id}-${step.step_order}`}>{index + 1}. {agent?.name ?? "agente eliminado"}</span>; })}</div>{workflowEditId === workflow.id && <form className="config-form" onSubmit={(event) => void saveWorkflowEdit(workflow, event)}><label>Nombre<input value={workflowEditDraft.name} onChange={(event) => setWorkflowEditDraft({ ...workflowEditDraft, name: event.target.value })} required /></label><label>Tipo<select value={workflowEditDraft.workflow_type} onChange={(event) => setWorkflowEditDraft({ ...workflowEditDraft, workflow_type: event.target.value })}><option value="single_agent">Single agent</option><option value="sequential">Sequential</option><option value="reviewer">Reviewer</option><option value="supervisor">Supervisor</option><option value="parallel">Parallel</option><option value="debate">Debate</option></select></label><label className="full-width">Agentes (el orden de selecci&#243;n define los pasos)<select multiple value={workflowEditDraft.agent_ids.map(String)} onChange={(event) => setWorkflowEditDraft({ ...workflowEditDraft, agent_ids: Array.from(event.currentTarget.selectedOptions).map((option) => Number(option.value)) })}>{metadata.agents.map((agent) => <option value={agent.id} key={agent.id}>{agent.name}</option>)}</select></label><label className="full-width"><input type="checkbox" checked={workflowEditDraft.enabled} onChange={(event) => setWorkflowEditDraft({ ...workflowEditDraft, enabled: event.target.checked })} /> Activo</label><div className="skill-actions full-width"><button type="submit">Guardar cambios</button><button type="button" className="text-button" onClick={() => setWorkflowEditId(null)}>Cancelar</button></div></form>}</div>; })}</section>}

            {settingsSection === "mcps" && <section className="panel"><h2>MCPs</h2>{isAdmin && <ConfigForm onSubmit={createMcpServer} submitLabel="Registrar MCP"><input value={mcpDraft.name} onChange={(event) => setMcpDraft({ ...mcpDraft, name: event.target.value })} placeholder="MCP name" required /><input value={mcpDraft.description} onChange={(event) => setMcpDraft({ ...mcpDraft, description: event.target.value })} placeholder="Description" /><select value={mcpDraft.connection_type} onChange={(event) => setMcpDraft({ ...mcpDraft, connection_type: event.target.value })}><option value="command">Command</option><option value="url">URL</option></select>{mcpDraft.connection_type === "command" ? <input value={mcpDraft.command} onChange={(event) => setMcpDraft({ ...mcpDraft, command: event.target.value })} placeholder="Command" required /> : <input value={mcpDraft.url} onChange={(event) => setMcpDraft({ ...mcpDraft, url: event.target.value })} placeholder="URL" required />}<select value={mcpDraft.tool_permission} onChange={(event) => setMcpDraft({ ...mcpDraft, tool_permission: event.target.value })} title="Las tools safe pueden ejecutarse headless (triggers, briefs) sin aprobación. Solo para MCPs de solo lectura."><option value="sensitive">Sensible (pide aprobación siempre)</option><option value="safe">Segura (solo lectura: usable en briefs)</option></select><label><input type="checkbox" checked={mcpDraft.enabled} onChange={(event) => setMcpDraft({ ...mcpDraft, enabled: event.target.checked })} /> Enabled</label><button type="button" onClick={validateMcpServer}>Validate MCP</button></ConfigForm>}{mcpValidation && <pre className="skill-result">{mcpValidation}</pre>}{isAdmin && <ConfigForm onSubmit={runMcpServer} submitLabel="Run MCP method"><select value={mcpRunDraft.server_id} onChange={(event) => setMcpRunDraft({ ...mcpRunDraft, server_id: event.target.value })} required><option value="">Select enabled MCP</option>{metadata.mcpServers.filter((server) => server.enabled).map((server) => <option value={server.id} key={server.id}>{server.name}</option>)}</select><input value={mcpRunDraft.method} onChange={(event) => setMcpRunDraft({ ...mcpRunDraft, method: event.target.value })} placeholder="tools/list" required /><textarea value={mcpRunDraft.params} onChange={(event) => setMcpRunDraft({ ...mcpRunDraft, params: event.target.value })} placeholder='{"name":"tool"}' /></ConfigForm>}{mcpRunResult && <pre className="skill-result">{mcpRunResult}</pre>}{metadata.mcpServers.length ? metadata.mcpServers.map((server) => <div className="provider-row-block" key={server.id}><label className="attachment-row"><span>{server.name} ({server.connection_type}){server.tool_permission === "safe" ? " · safe" : ""}</span>{isAdmin && <button type="button" className="text-button" disabled={inspectingMcp !== null} onClick={() => inspectMcpServer(server)}>{inspectingMcp === server.id ? "Inspeccionando..." : "Inspeccionar"}</button>}{isAdmin && <button type="button" className="text-button danger" onClick={() => deleteMcpServer(server)}>Borrar</button>}{isAdmin && <input type="checkbox" checked={server.enabled} onChange={(event) => toggleMcpServer(server, event.target.checked)} />}</label>{mcpInspection?.serverId === server.id && <div className="detect-results">{mcpInspection.tools.length === 0 ? <span className="chip muted-chip">sin tools descubiertas</span> : mcpInspection.tools.slice(0, 12).map((tool) => <span className="chip" key={tool.name} title={tool.description ?? ""}>{tool.name}</span>)}</div>}</div>) : <p className="muted">No MCP servers registered.</p>}</section>}

{settingsSection === "plugins" && <section className="panel"><h2>Plugins</h2><p className="muted">Packs que agrupan skills, MCPs y sub-agentes. Catalogo local en plugins/ del repo o marketplaces git (https publico).</p>{pluginMessage && <p className="muted">{pluginMessage}</p>}{isAdmin && <ConfigForm onSubmit={addPluginMarketplace} submitLabel="Añadir marketplace"><input value={marketplaceDraft} onChange={(event) => setMarketplaceDraft(event.target.value)} placeholder="https://github.com/owner/plugins-repo" required /></ConfigForm>}{pluginMarketplaces.length > 0 && <div>{pluginMarketplaces.map((marketplace) => <div className="attachment-row" key={marketplace.name}><span>{marketplace.name} · {marketplace.url}</span><button type="button" className="text-button" disabled={pluginBusy === "market:" + marketplace.name} onClick={() => void refreshPluginMarketplace(marketplace.name)}>Actualizar</button><button type="button" className="text-button danger" disabled={pluginBusy === "market:" + marketplace.name} onClick={() => void removePluginMarketplace(marketplace.name)}>Eliminar</button></div>)}</div>}{pluginCatalog.length === 0 ? <p className="muted">No hay plugins en el catalogo.</p> : <div className="skill-grid">{pluginCatalog.map((entry) => <article className="skill-card" key={entry.slug + ":" + entry.source}><div className="skill-card-head"><div><strong>{entry.name}</strong><span>v{entry.version} · {entry.source === "local" ? "local" : "marketplace"}</span></div></div><p>{entry.description}</p><div className="chip-row"><span className="chip">skills: {entry.components.skills}</span><span className="chip">mcps: {entry.components.mcps}</span><span className="chip">agents: {entry.components.agents}</span>{entry.connectors.map((connector) => <span className={missingConnectorsFor(entry).includes(connector) ? "chip muted-chip" : "chip"} key={connector}>{connector}{missingConnectorsFor(entry).includes(connector) ? " · sin conectar" : ""}</span>)}</div>{entry.installed && missingConnectorsFor(entry).length > 0 && <p className="muted">Conectores requeridos sin cuenta: {missingConnectorsFor(entry).join(", ")} (vista Conectores).</p>}{isAdmin && <div className="skill-actions">{entry.installed ? <button className="text-button danger" disabled={pluginBusy === entry.slug} onClick={() => void uninstallPluginEntry(entry)}>{pluginBusy === entry.slug ? "..." : "Desinstalar"}</button> : <button className="text-button" disabled={pluginBusy === entry.slug} onClick={() => void installPluginEntry(entry)}>{pluginBusy === entry.slug ? "Instalando..." : "Instalar"}</button>}</div>}</article>)}</div>}</section>}

            {settingsSection === "users" && <section className="panel"><h2>Users</h2>{isAdmin && <ConfigForm onSubmit={adminCreateUser} submitLabel="Crear usuario"><input value={userCreateDraft.username} onChange={(event) => setUserCreateDraft({ ...userCreateDraft, username: event.target.value })} placeholder="Usuario" required /><input value={userCreateDraft.email} onChange={(event) => setUserCreateDraft({ ...userCreateDraft, email: event.target.value })} placeholder="Email" type="email" required /><input type="password" value={userCreateDraft.password} onChange={(event) => setUserCreateDraft({ ...userCreateDraft, password: event.target.value })} placeholder="Contraseña (mín. 8, letras y números)" required autoComplete="new-password" /><select value={userCreateDraft.role} onChange={(event) => setUserCreateDraft({ ...userCreateDraft, role: event.target.value as "admin" | "user" })}><option value="user">User</option><option value="admin">Admin</option></select></ConfigForm>}{!isAdmin ? <p className="muted">Admin role required.</p> : metadata.users.length === 0 ? <p className="muted">No users found.</p> : metadata.users.map((user) => <label className="attachment-row" key={user.id}><span>{user.username} ({user.email})</span><select value={user.role} onChange={(event) => updateUserRole(user.id, event.target.value as "admin" | "user") }><option value="user">User</option><option value="admin">Admin</option></select></label>)}</section>}
            {settingsSection === "audit" && <section className="panel"><h2>Audit Logs</h2><div className="audit-filters"><input value={auditFilters.action} onChange={(event) => setAuditFilters({ ...auditFilters, action: event.target.value })} placeholder="Filter action" /><select value={auditFilters.target_type} onChange={(event) => setAuditFilters({ ...auditFilters, target_type: event.target.value })}><option value="">All targets</option><option value="user">user</option><option value="provider">provider</option><option value="model">model</option><option value="agent">agent</option><option value="workflow">workflow</option><option value="mcp_server">mcp_server</option><option value="skill">skill</option></select><button className="text-button" onClick={() => void refreshWorkspace()}>Apply</button></div>{auditLogs.length === 0 ? <p className="muted">No audit events yet.</p> : <>{auditLogs.slice(0, auditLogLimit).map((log) => <div className="tool-call" key={log.id}><div className="audit-row-head"><strong>{log.action}</strong><span>{formatDateTime(log.created_at)}</span></div><span>{log.actor_username ?? "system"} {"->"} {log.target_type} #{log.target_id ?? "n/a"}</span><small>{formatAuditMetadata(log.metadata)}</small></div>)}{auditLogLimit < auditLogs.length && <button className="text-button" onClick={() => setAuditLogLimit((limit) => Math.min(limit + 8, auditLogs.length))}>Show more audit logs</button>}</>}</section>}
            </>}
          </div>
        </section>
  );
}
