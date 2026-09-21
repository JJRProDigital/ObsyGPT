import { FormEvent, KeyboardEvent as ReactKeyboardEvent, ReactNode, useEffect, useState } from "react";
import { apiRequest, streamApprovalResume, streamMessage, uploadAttachment, type ActivityEvent } from "./api";

type User = { id: number; username: string; role?: "admin" | "user" };
type SessionResponse = { logged_in: boolean; user: User | null };
type HealthResponse = { status: string; database?: string };
type ModelCheckResponse = { ready?: boolean; enabled?: boolean; provider_enabled?: boolean; api_key_configured?: boolean; api_key_env?: string; model_name?: string; provider?: string; [key: string]: unknown };
type DiagnosticsResponse = { counts: Record<string, number>; providers: Array<{ id: number; name: string; ready: boolean; enabled: boolean; configured_models: number; api_key_configured: boolean }> };
type AuditLog = { id: number; actor_username: string | null; action: string; target_type: string; target_id: number | null; metadata: Record<string, unknown>; created_at: string };
  type Conversation = { id: number; title: string; label?: string; created_at: string; folder_id?: number | null };
  type ChatFolder = { id: number; name: string; conversation_count: number };
  type Message = { role: "user" | "assistant"; content: string; created_at?: string; id?: number };
type Provider = { id: number; name: string; provider_type: string; base_url: string | null; api_key_env: string | null; enabled: boolean };
type Model = { id: number; display_name: string; model_name: string; provider_id: number; supports_text: boolean; supports_streaming: boolean; supports_vision: boolean; supports_audio: boolean; supports_tools: boolean; supports_json: boolean; context_window: number | null; enabled: boolean };
type Agent = { id: number; name: string; description: string; system_prompt?: string; provider_id: number | null; model_id: number | null; temperature: string | number; internet_enabled: boolean; multimodal_enabled: boolean; agentic_mode?: boolean; enabled: boolean };
type AgentTool = { agent_id: number; tool_name: string; allowed: boolean };
type ToolDefinition = { name: string; description: string; parameters: string; permission: "safe" | "sensitive" };
type PendingApproval = { id: number; agent_run_id: number; conversation_id: number; tool_name: string; args: Record<string, unknown>; created_at: string };
type DetectedModel = { model_name: string; display_name: string; already_registered: boolean };
type AgentFallback = { agent_id: number; provider_id: number; model_id: number; priority: number; provider_name: string; model_display_name: string };
type Task = { id: number; goal: string; mode: string; status: string; scheduled_at: string | null; attempts: number; agent_id: number | null; project_id: number | null; recurrence: string | null; last_occurrence_at?: string | null; result: string; error: string; created_at: string; updated_at: string };
type TaskEvent = { id: number; event_type: string; title: string; content: string; created_at: string };
type TaskApproval = { id: number; task_id: number; tool_name: string; args: Record<string, unknown>; created_at: string };
type MemoryItem = { id: number; kind: string; content: string; project_id?: number | null; created_at: string; updated_at: string };
type HabitSuggestion = { id: number; content: string; evidence: string; source: string; created_at: string };
type WorkspaceInfo = { workspace: string; recent: string[]; default: string };
type Preferences = { display_name: string; accent: string; memory_max: number; tool_policies: Record<string, string>; instructions: string };
type GuardrailSettings = { max_iterations?: number; max_tool_calls?: number; max_duration_seconds?: number; max_tool_output_chars?: number; max_total_chars?: number; loop_repeat_limit?: number };
type TasksSettings = { max_concurrent_tasks: number; auto_resume_tasks: boolean };
type Project = { id: number; name: string; description: string; instructions: string; folder_path?: string | null; archived?: boolean; conversation_count?: number; attachment_count?: number; active_task_count?: number; created_at: string; updated_at: string };
type ProjectDetail = Project & { conversations: Array<{ id: number; title: string; created_at: string }>; attachments: Attachment[] };
type ProjectTab = "chats" | "tareas" | "conocimiento" | "instrucciones" | "memoria" | "archivos";
type ProjectFileEntry = { name: string; is_dir: boolean; size: number; modified: string };
type ProjectFilesResponse = { folder: string | null; subpath: string; parent: string | null; entries: ProjectFileEntry[] };
type Skill = { id: number; name: string; description: string; argument_hint: string; triggers: Array<"user" | "model">; body: string; resources: string; skill_md: string; enabled: boolean };
  type McpServer = { id: number; name: string; description: string; connection_type: string; command: string | null; url: string | null; enabled: boolean };
  type CatalogConnector = { slug: string; name: string; description: string; token_label: string; token_help: string; tool_names: string[]; account: { id: number; display_name: string; status: string } | null };
  type PluginCatalogEntry = { slug: string; name: string; version: string; description: string; source: string; marketplace_name: string | null; installed: boolean; connectors: string[]; components: { skills: number; mcps: number; agents: number } };
  type PluginMarketplace = { name: string; url: string };
type AgentSkill = { agent_id: number; skill_id: number };
type AgentMcp = { agent_id: number; mcp_server_id: number };
type ProviderDefinition = { provider_type: string; display_name: string; default_base_url: string | null; api_key_env: string | null; supports_vision: boolean; supports_tools: boolean; supports_audio: boolean; supports_json: boolean };
type Workflow = { id: number; name: string; workflow_type: string; enabled: boolean };
type WorkflowStep = { workflow_id: number; agent_id: number; step_order: number; step_name: string };
type AdminUser = { id: number; username: string; email: string; role: "admin" | "user"; created_at: string };
  type AgentRun = { id: number; status: string; final_response: string | null; created_at: string; completed_at: string | null; parent_run_id?: number | null };
type AgentEvent = { id: number; event_type: string; title: string; content: string; created_at: string };
type Attachment = { id: number; file_name: string; mime_type: string; size_bytes: number };
type Source = { id: number; agent_run_id: number; url: string; title: string; snippet: string; created_at: string };
type ToolCall = { id: number; agent_run_id: number; skill_name: string; input_summary: string; output_summary: string; status: string; created_at: string };
  type AppView = "chat" | "tasks" | "projects" | "memory" | "skills" | "tools" | "connectors" | "history" | "trace" | "settings" | "monitoring" | "diagnostics";
  type MetricsResponse = {
    days: number;
    summary: { runs: number; completed: number; failed: number; other: number; active_users: number; avg_duration_seconds: number };
    runs_per_day: Array<{ day: string; completed: number; failed: number; other: number }>;
    tool_calls_per_day: Array<{ day: string; total: number; failed: number }>;
    top_tools: Array<{ name: string; calls: number; failed: number }>;
    tool_categories: { connectors: number; mcp: number; builtin: number };
    mcp_calls: Array<{ name: string; calls: number; failed: number }>;
    provider_fallbacks: number;
    agent_activity: Array<{ agent: string; runs: number; failed: number }>;
  };
type SettingsTab = "modelo" | "preferencias" | "seguridad" | "agente" | "datos" | "admin";
  type AdminSection = "agents" | "models" | "workflows" | "mcps" | "plugins" | "users" | "audit";
type SettingsSection = AdminSection;
type SkillTab = "library" | "editor" | "generator";
type SkillDraftResponse = { name: string; description: string; argument_hint: string; triggers: Array<"user" | "model">; body: string; resources: string; instructions: string; checklist: string[] };

const emptyMetadata = {
  providers: [] as Provider[],
  providerDefinitions: [] as ProviderDefinition[],
  models: [] as Model[],
  agents: [] as Agent[],
  skills: [] as Skill[],
  mcpServers: [] as McpServer[],
  agentSkills: [] as AgentSkill[],
  agentMcps: [] as AgentMcp[],
  workflows: [] as Workflow[],
  workflowSteps: [] as WorkflowStep[],
  users: [] as AdminUser[]
};

export default function App() {
  const [session, setSession] = useState<User | null>(null);
  const [authMode, setAuthMode] = useState<"login" | "register">("login");
  const [username, setUsername] = useState("");
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [confirmPassword, setConfirmPassword] = useState("");
  const [conversations, setConversations] = useState<Conversation[]>([]);
  const [folders, setFolders] = useState<ChatFolder[]>([]);
  const [expandedFolders, setExpandedFolders] = useState<number[]>([]);
  const [editingMessageIndex, setEditingMessageIndex] = useState<number | null>(null);
  const [editingMessageDraft, setEditingMessageDraft] = useState("");
  const [copiedMessageIndex, setCopiedMessageIndex] = useState<number | null>(null);
  const [activeConversationId, setActiveConversationId] = useState<number | null>(null);
  const [messages, setMessages] = useState<Message[]>([]);
  const [draft, setDraft] = useState("");
  const [metadata, setMetadata] = useState(emptyMetadata);
  const [runs, setRuns] = useState<AgentRun[]>([]);
  const [events, setEvents] = useState<AgentEvent[]>([]);
  const [sources, setSources] = useState<Source[]>([]);
  const [toolCalls, setToolCalls] = useState<ToolCall[]>([]);
  const [attachments, setAttachments] = useState<Attachment[]>([]);
  const [selectedAttachmentIds, setSelectedAttachmentIds] = useState<number[]>([]);
  const [error, setError] = useState("");
  const [isStreaming, setIsStreaming] = useState(false);
  const [liveActivity, setLiveActivity] = useState<{ label: string; detail?: string; iteration?: number; chars?: number; startedAt: number; lastAt: number } | null>(null);
  const [nowTick, setNowTick] = useState(Date.now());
  const [providerDraft, setProviderDraft] = useState({ name: "", provider_type: "openai", base_url: "", api_key_env: "", enabled: false });
  const [modelDraft, setModelDraft] = useState({ provider_id: "", model_name: "", display_name: "", context_window: "", supports_vision: false, supports_audio: false, supports_tools: false, supports_json: false, enabled: true });
  const [agentDraft, setAgentDraft] = useState({ name: "", description: "", system_prompt: "", provider_id: "", model_id: "", internet_enabled: false, multimodal_enabled: false, agentic_mode: true });
  const [agentEditId, setAgentEditId] = useState<number | null>(null);
  const [agentEditDraft, setAgentEditDraft] = useState({ name: "", description: "", system_prompt: "", provider_id: "", model_id: "", temperature: "0.7", internet_enabled: false, multimodal_enabled: false });
  const [skillDraft, setSkillDraft] = useState({ name: "", description: "", argument_hint: "", triggers: ["user"] as Array<"user" | "model">, body: "# Instrucciones principales\n1. Describe el flujo de trabajo de la skill.\n\n## Restricciones\n* No ejecutes acciones destructivas sin confirmacion explicita.", resources: "", enabled: true });
  const [editingSkillId, setEditingSkillId] = useState<number | null>(null);
  const [skillTab, setSkillTab] = useState<SkillTab>("library");
  const [skillSearch, setSkillSearch] = useState("");
  const [skillGeneratorPrompt, setSkillGeneratorPrompt] = useState("");
  const [generatedSkill, setGeneratedSkill] = useState<SkillDraftResponse | null>(null);
  const [mcpDraft, setMcpDraft] = useState({ name: "", description: "", connection_type: "command", command: "", url: "", enabled: false });
  const [workflowDraft, setWorkflowDraft] = useState({ name: "", workflow_type: "sequential", agent_ids: [] as number[] });
  const [selectedWorkflowId, setSelectedWorkflowId] = useState("");
  const [selectedAgentId, setSelectedAgentId] = useState("");
  const [internetUrl, setInternetUrl] = useState("");
  const [skillResult, setSkillResult] = useState("");
  const [mcpValidation, setMcpValidation] = useState("");
  const [catalogConnectors, setCatalogConnectors] = useState<CatalogConnector[]>([]);
  const [pluginCatalog, setPluginCatalog] = useState<PluginCatalogEntry[]>([]);
  const [pluginMarketplaces, setPluginMarketplaces] = useState<PluginMarketplace[]>([]);
  const [marketplaceDraft, setMarketplaceDraft] = useState("");
  const [pluginBusy, setPluginBusy] = useState<string | null>(null);
  const [pluginMessage, setPluginMessage] = useState("");
  const [connectorTokenDrafts, setConnectorTokenDrafts] = useState<Record<string, string>>({});
  const [connectorBusy, setConnectorBusy] = useState<string | null>(null);
  const [connectorMessage, setConnectorMessage] = useState("");
  const [mcpInspection, setMcpInspection] = useState<{ serverId: number; tools: Array<{ name: string; description?: string }> } | null>(null);
  const [inspectingMcp, setInspectingMcp] = useState<number | null>(null);
  const [mcpRunDraft, setMcpRunDraft] = useState({ server_id: "", method: "tools/list", params: "{}" });
  const [mcpRunResult, setMcpRunResult] = useState("");
  const [health, setHealth] = useState<HealthResponse | null>(null);
  const [modelCheckResult, setModelCheckResult] = useState<ModelCheckResponse | null>(null);
  const [diagnostics, setDiagnostics] = useState<DiagnosticsResponse | null>(null);
  const [metrics, setMetrics] = useState<MetricsResponse | null>(null);
  const [metricsDays, setMetricsDays] = useState(14);
  const [auditLogs, setAuditLogs] = useState<AuditLog[]>([]);
  const [auditLogLimit, setAuditLogLimit] = useState(8);
  const [auditFilters, setAuditFilters] = useState({ action: "", target_type: "" });
  const [agentTools, setAgentTools] = useState<AgentTool[]>([]);
  const [toolDefinitions, setToolDefinitions] = useState<ToolDefinition[]>([]);
  const [agentFallbacks, setAgentFallbacks] = useState<AgentFallback[]>([]);
  const [pendingApprovals, setPendingApprovals] = useState<PendingApproval[]>([]);
  const [resumingApprovalId, setResumingApprovalId] = useState<number | null>(null);
  const [detectedModels, setDetectedModels] = useState<Record<number, DetectedModel[]>>({});
  const [detectingProvider, setDetectingProvider] = useState<number | null>(null);
  const [fallbackDraft, setFallbackDraft] = useState<Record<number, { provider_id: string; model_id: string }>>({});
  const [chatMode, setChatMode] = useState<"act" | "plan" | "think">("act");
  const [paletteIndex, setPaletteIndex] = useState(0);
  const [activeView, setActiveView] = useState<AppView>("chat");
  const [settingsSection, setSettingsSection] = useState<SettingsSection>("agents");
  const [settingsTab, setSettingsTab] = useState<SettingsTab>("modelo");
  const [settingsSearch, setSettingsSearch] = useState("");
  const [tasks, setTasks] = useState<Task[]>([]);
  const [taskDraft, setTaskDraft] = useState({ goal: "", mode: "act", scheduled_at: "", recurrence: "" });
  const [expandedTaskId, setExpandedTaskId] = useState<number | null>(null);
  const [taskEvents, setTaskEvents] = useState<Record<number, TaskEvent[]>>({});
  const [taskApprovals, setTaskApprovals] = useState<Record<number, TaskApproval[]>>({});
  const [memories, setMemories] = useState<MemoryItem[]>([]);
  const [habitSuggestions, setHabitSuggestions] = useState<HabitSuggestion[]>([]);
  const [memoryDraft, setMemoryDraft] = useState({ content: "", kind: "memory" });
  const [workspaceInfo, setWorkspaceInfo] = useState<WorkspaceInfo | null>(null);
  const [workspaceDraft, setWorkspaceDraft] = useState("");
  const [preferences, setPreferences] = useState<Preferences | null>(null);
  const [guardrailDraft, setGuardrailDraft] = useState<GuardrailSettings>({});
  const [tasksSettings, setTasksSettings] = useState<TasksSettings>({ max_concurrent_tasks: 1, auto_resume_tasks: true });
  const [historySearch, setHistorySearch] = useState("");
  const [projects, setProjects] = useState<Project[]>([]);
  const [projectDetail, setProjectDetail] = useState<ProjectDetail | null>(null);
  const [projectDraft, setProjectDraft] = useState({ name: "", description: "", instructions: "", folder_path: "" });
  const [projectInstructionsDraft, setProjectInstructionsDraft] = useState("");
  const [projectTab, setProjectTab] = useState<ProjectTab>("chats");
  const [projectFiles, setProjectFiles] = useState<ProjectFilesResponse>({ folder: null, subpath: "", parent: null, entries: [] });
  const [projectTasks, setProjectTasks] = useState<Task[]>([]);
  const [projectMemories, setProjectMemories] = useState<MemoryItem[]>([]);
  const [projectTaskDraft, setProjectTaskDraft] = useState({ goal: "", mode: "act", scheduled_at: "", recurrence: "" });
  const [projectMemoryDraft, setProjectMemoryDraft] = useState("");
  const [activeProjectName, setActiveProjectName] = useState<string | null>(null);
  const [leftSidebarCollapsed, setLeftSidebarCollapsed] = useState(false);
  const [rightSidebarOpen, setRightSidebarOpen] = useState(false);
  const [userMenuOpen, setUserMenuOpen] = useState(false);

  useEffect(() => {
    void refreshHealth();
    refreshSession().catch((err: Error) => setError(err.message));
  }, []);

  useEffect(() => {
    if (!session) return;
    void refreshWorkspace();
  }, [session]);

  useEffect(() => {
    if (!activeConversationId) return;
    void refreshMessages(activeConversationId);
    void refreshRuns(activeConversationId);
    void refreshActiveProject(activeConversationId);
  }, [activeConversationId]);

  async function refreshActiveProject(conversationId: number) {
    try {
      const data = await apiRequest<{ project: { name: string } | null }>(`/api/projects/for-conversation/${conversationId}`);
      setActiveProjectName(data.project?.name ?? null);
    } catch {
      setActiveProjectName(null);
    }
  }

  useEffect(() => {
    if (!session || !activeConversationId || activeView !== "chat") return;
    void refreshHabitSuggestions();
    const interval = window.setInterval(() => { void refreshApprovals(activeConversationId); void refreshHabitSuggestions(); }, 4000);
    return () => window.clearInterval(interval);
  }, [session, activeConversationId, activeView]);

  useEffect(() => {
    if (!projectDetail || projectTab !== "archivos") return;
    void refreshProjectFiles(projectDetail.id);
  }, [projectDetail?.id, projectTab]);

  useEffect(() => {
    if (!session || activeView !== "tasks") return;
    void refreshTasks();
    const interval = window.setInterval(() => { void refreshTasks(); }, 5000);
    return () => window.clearInterval(interval);
  }, [session, activeView]);

  useEffect(() => {
    if (!session) return;
    void refreshTasks();
    void refreshMemories();
    void refreshProjects();
    const interval = window.setInterval(() => { void refreshTasks(); }, 15000);
    return () => window.clearInterval(interval);
  }, [session]);

  useEffect(() => {
    if (!liveActivity) return;
    const interval = window.setInterval(() => setNowTick(Date.now()), 1000);
    return () => window.clearInterval(interval);
  }, [liveActivity !== null]);


  useEffect(() => {
    if (!session || (activeView !== "memory" && activeView !== "settings")) return;
    void refreshMemories();
    void refreshHabitSuggestions();
  }, [session, activeView]);

  useEffect(() => {
    if (!session || activeView !== "settings") return;
    void refreshWorkspaceInfo();
    void refreshPreferences();
  }, [session, activeView]);

  useEffect(() => {
    if (!session || session.role !== "admin" || activeView !== "settings" || settingsTab !== "seguridad") return;
    void refreshGuardrailSettings();
    void refreshTasksSettings();
  }, [session, activeView, settingsTab]);

  useEffect(() => {
    if (!session || session.role !== "admin" || activeView !== "monitoring") return;
    void loadMetrics(metricsDays);
  }, [session, activeView]);

  useEffect(() => {
    if (!session || session.role !== "admin" || activeView !== "settings" || settingsTab !== "admin" || settingsSection !== "plugins") return;
    void refreshPlugins();
  }, [session, activeView, settingsTab, settingsSection]);

  useEffect(() => {
    const accent = preferences?.accent ?? "gold";
    const presets: Record<string, string> = { gold: "#D5B06D", teal: "#7FBFB4", violet: "#9B8CDB", magenta: "#C77DAB", ice: "#9FC2D0" };
    document.documentElement.style.setProperty("--accent", presets[accent] ?? presets.gold);
  }, [preferences?.accent]);

  async function refreshTasks() {
    try {
      const data = await apiRequest<{ tasks: Task[] }>("/api/tasks");
      setTasks(data.tasks);
      const awaiting = data.tasks.filter((task) => task.status === "awaiting_approval");
      for (const task of awaiting) {
        try {
          const approvals = await apiRequest<{ approvals: TaskApproval[] }>(`/api/tasks/approvals/pending?task_id=${task.id}`);
          setTaskApprovals((current) => ({ ...current, [task.id]: approvals.approvals }));
        } catch { /* sin aprobaciones */ }
      }
    } catch { /* silencio: la vista reintenta */ }
  }

  async function createTask(event: FormEvent) {
    event.preventDefault();
    if (!taskDraft.goal.trim()) return;
    setError("");
    try {
      await apiRequest("/api/tasks", {
        method: "POST",
        body: JSON.stringify({
          goal: taskDraft.goal,
          mode: taskDraft.mode,
          scheduled_at: taskDraft.scheduled_at || null,
          recurrence: taskDraft.recurrence || null
        })
      });
      setTaskDraft({ goal: "", mode: "act", scheduled_at: "", recurrence: "" });
      await refreshTasks();
    } catch (err) {
      setError(err instanceof Error ? err.message : "Task creation failed");
    }
  }

  async function taskAction(taskId: number, action: "pause" | "resume" | "cancel") {
    setError("");
    try {
      await apiRequest(`/api/tasks/${taskId}/${action}`, { method: "POST" });
      await refreshTasks();
    } catch (err) {
      setError(err instanceof Error ? err.message : `Task ${action} failed`);
    }
  }

  async function removeTask(taskId: number) {
    if (!window.confirm("Eliminar esta tarea y su historial?")) return;
    await apiRequest(`/api/tasks/${taskId}`, { method: "DELETE" });
    await refreshTasks();
  }

  async function toggleTaskEvents(taskId: number) {
    if (expandedTaskId === taskId) {
      setExpandedTaskId(null);
      return;
    }
    setExpandedTaskId(taskId);
    if (!taskEvents[taskId]) {
      try {
        const data = await apiRequest<{ events: TaskEvent[] }>(`/api/tasks/${taskId}/events`);
        setTaskEvents((current) => ({ ...current, [taskId]: data.events }));
      } catch { /* sin eventos */ }
    }
  }

  async function decideTaskApproval(approval: TaskApproval, approved: boolean) {
    setError("");
    try {
      await apiRequest(`/api/tasks/approvals/${approval.id}/${approved ? "approve" : "deny"}`, { method: "POST" });
      setTaskApprovals((current) => ({ ...current, [approval.task_id]: (current[approval.task_id] ?? []).filter((item) => item.id !== approval.id) }));
      await refreshTasks();
    } catch (err) {
      setError(err instanceof Error ? err.message : "Approval decision failed");
    }
  }

  async function refreshMemories() {
    try {
      const data = await apiRequest<{ memories: MemoryItem[] }>("/api/memory");
      setMemories(data.memories);
    } catch { /* sin memorias */ }
  }

  async function refreshHabitSuggestions() {
    try {
      const data = await apiRequest<{ suggestions: HabitSuggestion[] }>("/api/memory/habits/suggestions");
      setHabitSuggestions(data.suggestions);
    } catch { /* sin sugerencias */ }
  }

  async function decideHabitSuggestion(suggestionId: number, decision: "accept" | "dismiss") {
    setHabitSuggestions((current) => current.filter((item) => item.id !== suggestionId));
    try {
      await apiRequest(`/api/memory/habits/suggestions/${suggestionId}/${decision}`, { method: "POST" });
      await refreshMemories();
    } catch (err) {
      setError(err instanceof Error ? err.message : "Habit suggestion failed");
      await refreshHabitSuggestions();
    }
  }

  async function addMemory(event: FormEvent) {
    event.preventDefault();
    if (!memoryDraft.content.trim()) return;
    await apiRequest("/api/memory", { method: "POST", body: JSON.stringify(memoryDraft) });
    setMemoryDraft({ content: "", kind: memoryDraft.kind });
    await refreshMemories();
  }

  async function deleteMemory(id: number) {
    await apiRequest(`/api/memory/${id}`, { method: "DELETE" });
    await refreshMemories();
  }

  async function resetHabits() {
    if (!window.confirm("Borrar todos los habitos aprendidos?")) return;
    await apiRequest("/api/memory/habits/all", { method: "DELETE" });
    await refreshMemories();
  }

  async function refreshWorkspaceInfo() {
    try {
      const data = await apiRequest<WorkspaceInfo>("/api/workspace");
      setWorkspaceInfo(data);
      setWorkspaceDraft((current) => (current ? current : data.workspace));
    } catch { /* sin workspace */ }
  }

  async function saveWorkspace(event?: FormEvent) {
    event?.preventDefault();
    setError("");
    try {
      const data = await apiRequest<WorkspaceInfo>("/api/workspace", { method: "PUT", body: JSON.stringify({ path: workspaceDraft }) });
      setWorkspaceInfo(data);
      setError("");
    } catch (err) {
      setError(err instanceof Error ? err.message : "Workspace update failed");
    }
  }

  async function refreshPreferences() {
    try {
      const data = await apiRequest<{ preferences: Preferences }>("/api/workspace/preferences");
      setPreferences(data.preferences);
    } catch { /* sin preferencias */ }
  }

  async function savePreferences(updates: Partial<Preferences>) {
    setError("");
    try {
      const data = await apiRequest<{ preferences: Preferences }>("/api/workspace/preferences", { method: "PUT", body: JSON.stringify(updates) });
      setPreferences(data.preferences);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Preferences update failed");
    }
  }

  async function refreshGuardrailSettings() {
    try {
      const data = await apiRequest<{ guardrails: GuardrailSettings }>("/api/admin/settings/guardrails");
      setGuardrailDraft(data.guardrails);
    } catch { /* sin guardrails */ }
  }

  async function saveGuardrails(event: FormEvent) {
    event.preventDefault();
    await apiRequest("/api/admin/settings/guardrails", { method: "PUT", body: JSON.stringify(guardrailDraft) });
  }

  async function refreshTasksSettings() {
    try {
      const data = await apiRequest<{ tasks: TasksSettings }>("/api/admin/settings/tasks");
      setTasksSettings(data.tasks);
    } catch { /* sin settings */ }
  }

  async function saveTasksSettings() {
    try {
      const data = await apiRequest<{ tasks: TasksSettings }>("/api/admin/settings/tasks", { method: "PUT", body: JSON.stringify(tasksSettings) });
      setTasksSettings(data.tasks);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Tasks settings update failed");
    }
  }

  async function refreshProjects() {
    try {
      const data = await apiRequest<{ projects: Project[] }>("/api/projects");
      setProjects(data.projects);
    } catch { /* sin proyectos */ }
  }

  async function createProject(event: FormEvent) {
    event.preventDefault();
    if (!projectDraft.name.trim()) return;
    setError("");
    try {
      const data = await apiRequest<{ project: Project }>("/api/projects", { method: "POST", body: JSON.stringify({ ...projectDraft, folder_path: projectDraft.folder_path || null }) });
      setProjectDraft({ name: "", description: "", instructions: "", folder_path: "" });
      await refreshProjects();
      await openProjectDetail(data.project.id);
      setProjectTab("instrucciones");
    } catch (err) {
      setError(err instanceof Error ? err.message : "Project creation failed");
    }
  }

  async function openProjectDetail(projectId: number) {
    setError("");
    try {
      const data = await apiRequest<{ project: ProjectDetail }>(`/api/projects/${projectId}`);
      setProjectDetail(data.project);
      setProjectInstructionsDraft(data.project.instructions);
      await refreshProjectTasks(projectId);
      await refreshProjectMemories(projectId);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Project load failed");
    }
  }

  async function refreshProjectTasks(projectId: number) {
    try {
      const data = await apiRequest<{ tasks: Task[] }>(`/api/tasks?project_id=${projectId}`);
      setProjectTasks(data.tasks);
    } catch { setProjectTasks([]); }
  }

  async function refreshProjectMemories(projectId: number) {
    try {
      const data = await apiRequest<{ memories: MemoryItem[] }>(`/api/memory?project_id=${projectId}`);
      setProjectMemories(data.memories);
    } catch { setProjectMemories([]); }
  }

  async function createProjectChat(projectId: number) {
    const data = await apiRequest<{ conversation: { id: number } }>(`/api/projects/${projectId}/chats`, { method: "POST" });
    await refreshProjects();
    await refreshWorkspace();
    setActiveConversationId(data.conversation.id);
    setActiveView("chat");
  }

  async function createProjectTask(projectId: number, event: FormEvent) {
    event.preventDefault();
    if (!projectTaskDraft.goal.trim()) return;
    setError("");
    try {
      await apiRequest("/api/tasks", {
        method: "POST",
        body: JSON.stringify({ goal: projectTaskDraft.goal, mode: projectTaskDraft.mode, scheduled_at: projectTaskDraft.scheduled_at || null, project_id: projectId, recurrence: projectTaskDraft.recurrence || null })
      });
      setProjectTaskDraft({ goal: "", mode: "act", scheduled_at: "", recurrence: "" });
      await refreshProjectTasks(projectId);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Task creation failed");
    }
  }

  async function projectTaskAction(projectId: number, taskId: number, action: "pause" | "resume" | "cancel") {
    await apiRequest(`/api/tasks/${taskId}/${action}`, { method: "POST" });
    await refreshProjectTasks(projectId);
  }

  async function uploadProjectKnowledge(projectId: number, event: FormEvent<HTMLInputElement>) {
    const file = event.currentTarget.files?.[0];
    if (!file) return;
    const body = new FormData();
    body.append("file", file);
    setError("");
    try {
      await fetch(`/api/projects/${projectId}/knowledge`, { method: "POST", credentials: "include", body });
      await openProjectDetail(projectId);
      await refreshProjects();
    } catch (err) {
      setError(err instanceof Error ? err.message : "Knowledge upload failed");
    } finally {
      event.currentTarget.value = "";
    }
  }

  async function addProjectMemory(projectId: number, event: FormEvent) {
    event.preventDefault();
    if (!projectMemoryDraft.trim()) return;
    await apiRequest("/api/memory", { method: "POST", body: JSON.stringify({ content: projectMemoryDraft, kind: "memory", project_id: projectId }) });
    setProjectMemoryDraft("");
    await refreshProjectMemories(projectId);
  }

  async function deleteProjectMemory(projectId: number, memoryId: number) {
    await apiRequest(`/api/memory/${memoryId}`, { method: "DELETE" });
    await refreshProjectMemories(projectId);
  }

  async function archiveProject(projectId: number, archived: boolean) {
    if (archived && !window.confirm("Archivar este proyecto? Desaparecera de la lista activa sin borrar datos.")) return;
    await apiRequest(`/api/projects/${projectId}`, { method: "PATCH", body: JSON.stringify({ archived }) });
    setProjectDetail(null);
    await refreshProjects();
  }

  async function saveProjectInstructions() {
    if (!projectDetail) return;
    setError("");
    try {
      await apiRequest(`/api/projects/${projectDetail.id}`, { method: "PATCH", body: JSON.stringify({ instructions: projectInstructionsDraft }) });
      await openProjectDetail(projectDetail.id);
      await refreshProjects();
    } catch (err) {
      setError(err instanceof Error ? err.message : "Project update failed");
    }
  }

  async function refreshProjectFiles(projectId: number, subpath = "") {
    try {
      const query = subpath ? `?subpath=${encodeURIComponent(subpath)}` : "";
      const data = await apiRequest<ProjectFilesResponse>(`/api/projects/${projectId}/files${query}`);
      setProjectFiles(data);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Project files load failed");
    }
  }

  async function deleteProjectFile(projectId: number, path: string, name: string, subpath: string) {
    if (!window.confirm(`Eliminar "${name}"? No se puede deshacer.`)) return;
    setError("");
    try {
      await apiRequest(`/api/projects/${projectId}/files?path=${encodeURIComponent(path)}`, { method: "DELETE" });
      await refreshProjectFiles(projectId, subpath);
    } catch (err) {
      setError(err instanceof Error ? err.message : "File delete failed");
    }
  }

  async function enableProjectWorkspace(projectId: number) {
    setError("");
    try {
      const data = await apiRequest<{ project: ProjectDetail; workspace: string }>(`/api/projects/${projectId}/workspace`, { method: "POST" });
      setProjectDetail(data.project);
      setProjectInstructionsDraft(data.project.instructions);
      await refreshProjectFiles(projectId);
      await refreshProjects();
    } catch (err) {
      setError(err instanceof Error ? err.message : "Project workspace creation failed");
    }
  }

  async function unlinkProjectWorkspace(projectId: number) {
    if (!window.confirm("Desvincular la carpeta del proyecto? Los archivos no se borran, pero los chats y tareas volveran a usar el workspace global.")) return;
    setError("");
    try {
      const data = await apiRequest<{ project: ProjectDetail }>(`/api/projects/${projectId}/workspace`, { method: "DELETE" });
      setProjectDetail(data.project);
      setProjectFiles({ folder: null, subpath: "", parent: null, entries: [] });
      await refreshProjects();
    } catch (err) {
      setError(err instanceof Error ? err.message : "Project workspace unlink failed");
    }
  }

  async function removeProject(projectId: number) {
    const project = projects.find((item) => item.id === projectId);
    const folderWarning = project?.folder_path ? "\n\nSu carpeta independiente y TODOS sus archivos se eliminarán del disco." : "";
    if (!window.confirm(`Eliminar este proyecto? Las conversaciones no se borran, solo se desagrupan.${folderWarning}`)) return;
    await apiRequest(`/api/projects/${projectId}`, { method: "DELETE" });
    setProjectDetail(null);
    await refreshProjects();
  }

  async function projectLinkConversation(projectId: number, conversationId: number, link: boolean) {
    await apiRequest(`/api/projects/${projectId}/conversations/${conversationId}`, { method: link ? "POST" : "DELETE" });
    await openProjectDetail(projectId);
    await refreshProjects();
  }

  async function projectLinkAttachment(projectId: number, attachmentId: number, link: boolean) {
    await apiRequest(`/api/projects/${projectId}/attachments/${attachmentId}`, { method: link ? "POST" : "DELETE" });
    await openProjectDetail(projectId);
    await refreshProjects();
  }

  async function activateModel(providerId: number, modelId: number) {    const defaultAgent = metadata.agents[0];
    if (!defaultAgent) {
      setError("No hay agente por defecto.");
      return;
    }
    setError("");
    try {
      await apiRequest(`/api/admin/agents/${defaultAgent.id}`, {
        method: "PATCH",
        body: JSON.stringify({
          name: defaultAgent.name,
          description: defaultAgent.description,
          system_prompt: defaultAgent.system_prompt ?? `You are ${defaultAgent.name}, a helpful ObsyGPT assistant.`,
          provider_id: providerId,
          model_id: modelId,
          temperature: Number(defaultAgent.temperature ?? 0.7),
          internet_enabled: defaultAgent.internet_enabled,
          multimodal_enabled: defaultAgent.multimodal_enabled,
          agentic_mode: Boolean(defaultAgent.agentic_mode),
          enabled: defaultAgent.enabled
        })
      });
      await refreshWorkspace();
    } catch (err) {
      setError(err instanceof Error ? err.message : "Model activation failed");
    }
  }

  async function refreshApprovals(conversationId: number) {
    try {
      const data = await apiRequest<{ approvals: PendingApproval[] }>(`/api/approvals/pending?conversation_id=${conversationId}`);
      setPendingApprovals(data.approvals);
    } catch {
      setPendingApprovals([]);
    }
  }

  async function resumeApproval(approval: PendingApproval, approved: boolean) {
    if (!activeConversationId || resumingApprovalId !== null) return;
    setResumingApprovalId(approval.id);
    setError("");
    setPendingApprovals((current) => current.filter((item) => item.id !== approval.id));
    setMessages((current) => [...current, { role: "assistant", content: "" }]);
    setLiveActivity({ label: approved ? "Ejecutando herramienta aprobada…" : "Cancelando herramienta…", startedAt: Date.now(), lastAt: Date.now() });

    try {
      await streamApprovalResume(approval.id, approved, (token) => {
        setMessages((current) => {
          const next = [...current];
          const last = next[next.length - 1];
          next[next.length - 1] = { ...last, content: last.content + token };
          return next;
        });
      }, applyLiveActivity);
      await refreshRuns(activeConversationId);
    } catch (err) {
      const message = err instanceof Error ? err.message : "Approval resume failed";
      setError(message);
      setMessages((current) => {
        const next = [...current];
        const last = next[next.length - 1];
        next[next.length - 1] = { ...last, content: message };
        return next;
      });
    } finally {
      setResumingApprovalId(null);
      setLiveActivity(null);
      void refreshApprovals(activeConversationId);
    }
  }

  async function refreshSession() {
    const data = await apiRequest<SessionResponse>("/api/session");
    setSession(data.logged_in ? data.user : null);
  }

  async function refreshHealth() {
    try {
      setHealth(await apiRequest<HealthResponse>("/api/health"));
    } catch (err) {
      setHealth({ status: err instanceof Error ? err.message : "unreachable" });
    }
  }

  async function refreshWorkspace() {
    const [conversationData, providers, providerDefinitions, models, agents, skills, mcpServers, agentSkills, agentMcps, workflows, users, agentToolsData, toolDefinitionsData, agentFallbacksData, connectorsData, foldersData] = await Promise.all([
      apiRequest<{ conversations: Conversation[] }>("/api/conversations"),
      apiRequest<{ providers: Provider[] }>("/api/admin/providers"),
      apiRequest<{ provider_definitions: ProviderDefinition[] }>("/api/admin/provider-definitions"),
      apiRequest<{ models: Model[] }>("/api/admin/models"),
      apiRequest<{ agents: Agent[] }>("/api/admin/agents"),
      apiRequest<{ skills: Skill[] }>("/api/admin/skills"),
      apiRequest<{ mcp_servers: McpServer[] }>("/api/admin/mcp-servers"),
      apiRequest<{ agent_skills: AgentSkill[] }>("/api/admin/agent-skills"),
      apiRequest<{ agent_mcps: AgentMcp[] }>("/api/admin/agent-mcps"),
      apiRequest<{ workflows: Workflow[]; workflow_steps: WorkflowStep[] }>("/api/admin/workflows"),
      session?.role === "admin" ? apiRequest<{ users: AdminUser[] }>("/api/admin/users") : Promise.resolve({ users: [] }),
      apiRequest<{ agent_tools: AgentTool[] }>("/api/admin/agent-tools"),
      apiRequest<{ tools: ToolDefinition[] }>("/api/agent/tools"),
      apiRequest<{ agent_fallbacks: AgentFallback[] }>("/api/admin/agent-fallbacks"),
      apiRequest<{ connectors: CatalogConnector[] }>("/api/connectors"),
      apiRequest<{ folders: ChatFolder[] }>("/api/folders")
    ]);

    let nextConversations = conversationData.conversations;
    if (nextConversations.length === 0) {
      const created = await apiRequest<{ conversation: Conversation }>("/api/conversations", { method: "POST" });
      nextConversations = [created.conversation];
    }

    setConversations(nextConversations);
    setActiveConversationId((current) => current ?? nextConversations[0]?.id ?? null);
    setAgentTools(agentToolsData.agent_tools);
    setToolDefinitions(toolDefinitionsData.tools);
    setAgentFallbacks(agentFallbacksData.agent_fallbacks);
    setCatalogConnectors(connectorsData.connectors);
    setFolders(foldersData.folders);
    setMetadata({
      providers: providers.providers,
      providerDefinitions: providerDefinitions.provider_definitions,
      models: models.models,
      agents: agents.agents,
      skills: skills.skills,
      mcpServers: mcpServers.mcp_servers,
      agentSkills: agentSkills.agent_skills,
      agentMcps: agentMcps.agent_mcps,
      workflows: workflows.workflows,
      workflowSteps: workflows.workflow_steps,
      users: users.users
    });
    if (session?.role === "admin") {
      const [diagnosticsData, auditData] = await Promise.all([
        apiRequest<DiagnosticsResponse>("/api/admin/diagnostics"),
        apiRequest<{ audit_logs: AuditLog[] }>(auditLogPath())
      ]);
      setDiagnostics(diagnosticsData);
      setAuditLogs(auditData.audit_logs);
      setAuditLogLimit(8);
    } else {
      setDiagnostics(null);
      setAuditLogs([]);
      setAuditLogLimit(8);
    }
    await refreshAttachments();
  }

  async function loadMetrics(days: number) {
    const data = await apiRequest<MetricsResponse>(`/api/admin/metrics?days=${days}`);
    setMetrics(data);
  }

  async function refreshPlugins() {
    const data = await apiRequest<{ plugins: PluginCatalogEntry[]; marketplaces: PluginMarketplace[] }>("/api/admin/plugins");
    setPluginCatalog(data.plugins);
    setPluginMarketplaces(data.marketplaces);
  }

  async function installPluginEntry(entry: PluginCatalogEntry) {
    setPluginBusy(entry.slug);
    setPluginMessage("");
    try {
      await apiRequest("/api/admin/plugins/install", {
        method: "POST",
        body: JSON.stringify({ source: entry.source, slug: entry.slug, marketplace_name: entry.marketplace_name })
      });
      setPluginMessage(`${entry.name} instalado.`);
      await refreshWorkspace();
      await refreshPlugins();
    } catch (error) {
      setPluginMessage(`Fallo la instalacion: ${error instanceof Error ? error.message : "error"}`);
    } finally {
      setPluginBusy(null);
    }
  }

  async function uninstallPluginEntry(entry: PluginCatalogEntry) {
    setPluginBusy(entry.slug);
    setPluginMessage("");
    try {
      await apiRequest(`/api/admin/plugins/${entry.slug}`, { method: "DELETE" });
      setPluginMessage(`${entry.name} desinstalado.`);
      await refreshWorkspace();
      await refreshPlugins();
    } catch (error) {
      setPluginMessage(`Fallo la desinstalacion: ${error instanceof Error ? error.message : "error"}`);
    } finally {
      setPluginBusy(null);
    }
  }

  async function addPluginMarketplace(event: FormEvent) {
    event.preventDefault();
    if (!marketplaceDraft.trim()) return;
    setPluginMessage("");
    try {
      await apiRequest("/api/admin/plugin-marketplaces", { method: "POST", body: JSON.stringify({ url: marketplaceDraft.trim() }) });
      setMarketplaceDraft("");
      await refreshPlugins();
    } catch (error) {
      setPluginMessage(`No se pudo anadir el marketplace: ${error instanceof Error ? error.message : "error"}`);
    }
  }

  async function refreshPluginMarketplace(name: string) {
    setPluginBusy(`market:${name}`);
    try {
      await apiRequest(`/api/admin/plugin-marketplaces/${name}/refresh`, { method: "POST" });
      await refreshPlugins();
      setPluginMessage(`Marketplace ${name} actualizado.`);
    } catch (error) {
      setPluginMessage(`Fallo la actualizacion: ${error instanceof Error ? error.message : "error"}`);
    } finally {
      setPluginBusy(null);
    }
  }

  async function removePluginMarketplace(name: string) {
    setPluginBusy(`market:${name}`);
    try {
      await apiRequest(`/api/admin/plugin-marketplaces/${name}`, { method: "DELETE" });
      await refreshPlugins();
    } finally {
      setPluginBusy(null);
    }
  }

  async function refreshAttachments() {
    const data = await apiRequest<{ attachments: Attachment[] }>("/api/attachments");
    setAttachments(data.attachments);
  }

  async function deleteAttachment(attachment: Attachment) {
    if (!window.confirm(`Borrar "${attachment.file_name}"? Se elimina el archivo y su texto extraído. Los chats que ya lo usaron no cambian.`)) return;
    setError("");
    try {
      await apiRequest(`/api/attachments/${attachment.id}`, { method: "DELETE" });
      setSelectedAttachmentIds((current) => current.filter((id) => id !== attachment.id));
      await refreshAttachments();
      if (projectDetail) await openProjectDetail(projectDetail.id);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Attachment delete failed");
    }
  }

  async function refreshMessages(conversationId: number) {
    const data = await apiRequest<{ messages: Message[] }>(`/api/conversations/${conversationId}/messages`);
    setMessages(data.messages);
  }

  async function refreshRuns(conversationId: number) {
    const data = await apiRequest<{ agent_runs: AgentRun[] }>(`/api/admin/agent-runs/${conversationId}`);
    setRuns(data.agent_runs);
    if (data.agent_runs[0]) {
      const [eventData, sourceData, toolCallData] = await Promise.all([
        apiRequest<{ agent_events: AgentEvent[] }>(`/api/admin/agent-events/${data.agent_runs[0].id}`),
        apiRequest<{ sources: Source[] }>(`/api/admin/sources/${data.agent_runs[0].id}`),
        apiRequest<{ tool_calls: ToolCall[] }>(`/api/admin/tool-calls/${data.agent_runs[0].id}`)
      ]);
      setEvents(eventData.agent_events);
      setSources(sourceData.sources);
      setToolCalls(toolCallData.tool_calls);
    } else {
      setEvents([]);
      setSources([]);
      setToolCalls([]);
    }
  }

  async function handleAuth(event: FormEvent) {
    event.preventDefault();
    setError("");
    const path = authMode === "login" ? "/api/login" : "/api/register";
    const body = authMode === "login" ? { username, password } : { username, email, password, confirm_password: confirmPassword };
    const data = await apiRequest<{ user: User }>(path, { method: "POST", body: JSON.stringify(body) });
    setSession(data.user);
  }

  async function createConversation() {
    const data = await apiRequest<{ conversation: Conversation }>("/api/conversations", { method: "POST" });
    setConversations((current) => [data.conversation, ...current]);
    setActiveConversationId(data.conversation.id);
  }

  async function deleteConversation(conversation: Conversation) {
    if (!window.confirm(`Delete "${conversation.label ?? conversation.title}"?`)) return;

    await apiRequest(`/api/conversations/${conversation.id}`, { method: "DELETE" });
    setConversations((current) => {
      const next = current.filter((item) => item.id !== conversation.id);
      if (activeConversationId === conversation.id) {
        setActiveConversationId(next[0]?.id ?? null);
        setMessages([]);
        setRuns([]);
        setEvents([]);
        setSources([]);
        setToolCalls([]);
      }
      return next;
    });
    if (conversations.length === 1) {
      await createConversation();
    }
  }

  async function renameConversation(conversation: Conversation) {
    const title = window.prompt("Conversation title", conversation.title)?.trim().slice(0, 120);
    if (!title) return;
    const data = await apiRequest<{ conversation: Conversation }>(`/api/conversations/${conversation.id}`, {
      method: "PATCH",
      body: JSON.stringify({ title })
    });
    setConversations((current) => current.map((item) => item.id === conversation.id ? { ...item, ...data.conversation, label: data.conversation.title } : item));
  }

  async function copyMessageText(text: string, index: number) {
    try {
      await navigator.clipboard.writeText(text);
    } catch {
      const area = document.createElement("textarea");
      area.value = text;
      document.body.appendChild(area);
      area.select();
      document.execCommand("copy");
      document.body.removeChild(area);
    }
    setCopiedMessageIndex(index);
    window.setTimeout(() => setCopiedMessageIndex(null), 1500);
  }

  function startEditMessage(index: number, content: string) {
    setEditingMessageIndex(index);
    setEditingMessageDraft(content);
  }

  async function saveEditMessage(index: number) {
    const message = messages[index];
    const content = editingMessageDraft.trim();
    if (!message || !content || !activeConversationId) return;
    if (message.id) {
      await apiRequest(`/api/conversations/${activeConversationId}/messages/${message.id}`, {
        method: "PATCH",
        body: JSON.stringify({ content })
      });
    }
    setMessages((current) => current.map((item, itemIndex) => itemIndex === index ? { ...item, content } : item));
    setEditingMessageIndex(null);
    setEditingMessageDraft("");
  }

  async function createFolder() {
    const name = window.prompt("Nombre de la carpeta")?.trim().slice(0, 100);
    if (!name) return;
    const data = await apiRequest<{ folder: ChatFolder }>("/api/folders", { method: "POST", body: JSON.stringify({ name }) });
    setFolders((current) => [...current, data.folder]);
  }

  async function renameFolder(folder: ChatFolder) {
    const name = window.prompt("Nombre de la carpeta", folder.name)?.trim().slice(0, 100);
    if (!name || name === folder.name) return;
    await apiRequest(`/api/folders/${folder.id}`, { method: "PATCH", body: JSON.stringify({ name }) });
    setFolders((current) => current.map((item) => item.id === folder.id ? { ...item, name } : item));
  }

  async function deleteFolder(folder: ChatFolder) {
    if (!window.confirm(`Eliminar la carpeta "${folder.name}"? Los chats pasaran a "Sin carpeta".`)) return;
    await apiRequest(`/api/folders/${folder.id}`, { method: "DELETE" });
    setFolders((current) => current.filter((item) => item.id !== folder.id));
    setConversations((current) => current.map((item) => item.folder_id === folder.id ? { ...item, folder_id: null } : item));
  }

  async function moveConversation(conversation: Conversation, folderId: number | null) {
    await apiRequest(`/api/conversations/${conversation.id}/folder`, { method: "PUT", body: JSON.stringify({ folder_id: folderId }) });
    setConversations((current) => current.map((item) => item.id === conversation.id ? { ...item, folder_id: folderId } : item));
    setFolders((current) => current.map((folder) => {
      const wasIn = conversation.folder_id === folder.id;
      const nowIn = folderId === folder.id;
      if (wasIn === nowIn) return folder;
      return { ...folder, conversation_count: folder.conversation_count + (nowIn ? 1 : -1) };
    }));
  }

  function toggleFolderExpanded(folderId: number) {
    setExpandedFolders((current) => current.includes(folderId) ? current.filter((id) => id !== folderId) : [...current, folderId]);
  }

  function applyLiveActivity(event: ActivityEvent) {
    setLiveActivity((current) => {
      const base = current ?? { label: "Iniciando…", startedAt: Date.now(), lastAt: Date.now() };
      const next = { ...base, iteration: event.iteration ?? base.iteration, chars: event.chars ?? base.chars, lastAt: Date.now() };
      if (event.kind === "thinking") next.label = `Pensando (iteración ${event.iteration ?? base.iteration ?? "?"})…`;
      else if (event.kind === "iteration") next.label = `Iteración ${event.iteration ?? "?"}`;
      else if (event.kind === "response") next.label = base.label === "Iniciando…" ? "Redactando respuesta…" : base.label;
      else if (event.kind === "tool" && event.phase === "start") next.label = `Ejecutando ${event.name}…`;
      else if (event.kind === "tool" && event.phase === "done") next.label = `${event.name} terminó`;
      else if (event.kind === "repair") next.label = "Reparando formato de tool call…";
      else if (event.kind === "retry") { next.label = "Reintentando conexión…"; next.detail = event.detail; }
      else if (event.kind === "fallback") { next.label = "Cambio a modelo de respaldo…"; next.detail = event.detail; }
      return next;
    });
  }

  async function sendMessage(event: FormEvent) {
    event.preventDefault();
    if (!activeConversationId || !draft.trim() || isStreaming) return;

    const userMessage = draft.trim();
    setDraft("");
    setMessages((current) => [...current, { role: "user", content: userMessage }, { role: "assistant", content: "" }]);
    setIsStreaming(true);
    setError("");
    setLiveActivity({ label: "Iniciando…", startedAt: Date.now(), lastAt: Date.now() });

    try {
      await streamMessage(
        activeConversationId,
        userMessage,
        {
          agent_id: selectedAgentId ? Number(selectedAgentId) : null,
          workflow_id: selectedWorkflowId ? Number(selectedWorkflowId) : null,
          attachment_ids: selectedAttachmentIds,
          mode: chatMode
        },
        (token) => {
        setMessages((current) => {
          const next = [...current];
          const last = next[next.length - 1];
          next[next.length - 1] = { ...last, content: last.content + token };
          return next;
        });
      },
        applyLiveActivity
      );
      await refreshRuns(activeConversationId);
      setSelectedAttachmentIds([]);
      void refreshApprovals(activeConversationId);
    } catch (err) {
      const message = err instanceof Error ? err.message : "Message failed";
      setError(message);
      setMessages((current) => {
        const next = [...current];
        next[next.length - 1] = { ...next[next.length - 1], role: "assistant", content: message };
        return next;
      });
    } finally {
      setIsStreaming(false);
      setLiveActivity(null);
    }
  }

  async function logout() {
    await apiRequest("/api/logout", { method: "POST" });
    setSession(null);
    setConversations([]);
    setActiveConversationId(null);
    setMessages([]);
    setMetadata(emptyMetadata);
    setRuns([]);
    setEvents([]);
    setSources([]);
    setToolCalls([]);
    setAttachments([]);
    setSelectedAttachmentIds([]);
    setSelectedWorkflowId("");
    setSelectedAgentId("");
    setInternetUrl("");
    setSkillResult("");
    setMcpValidation("");
    setMcpRunDraft({ server_id: "", method: "tools/list", params: "{}" });
    setMcpRunResult("");
    setHabitSuggestions([]);
    setError("");
  }

  async function handleAttachmentUpload(event: FormEvent<HTMLInputElement>) {
    const file = event.currentTarget.files?.[0];
    if (!file) return;
    setError("");

    try {
      const uploaded = await uploadAttachment(file);
      setAttachments((current) => [uploaded.attachment, ...current]);
      setSelectedAttachmentIds((current) => [uploaded.attachment.id, ...current]);
      setMessages((current) => [
        ...current,
        {
          role: "assistant",
          content: `Attached ${uploaded.attachment.file_name}\n${uploaded.artifact.content}`
        }
      ]);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Upload failed");
    } finally {
      event.currentTarget.value = "";
    }
  }

  async function createProvider(event: FormEvent) {
    event.preventDefault();
    await apiRequest("/api/admin/providers", {
      method: "POST",
      body: JSON.stringify({
        ...providerDraft,
        base_url: providerDraft.base_url || null,
        api_key_env: providerDraft.api_key_env || null
      })
    });
    setProviderDraft({ name: "", provider_type: "openai", base_url: "", api_key_env: "", enabled: false });
    await refreshWorkspace();
  }

  async function createModel(event: FormEvent) {
    event.preventDefault();
    await apiRequest("/api/admin/models", {
      method: "POST",
      body: JSON.stringify({
        provider_id: Number(modelDraft.provider_id),
        model_name: modelDraft.model_name,
        display_name: modelDraft.display_name,
        supports_text: true,
        supports_streaming: true,
        supports_vision: modelDraft.supports_vision,
        supports_audio: modelDraft.supports_audio,
        supports_tools: modelDraft.supports_tools,
        supports_json: modelDraft.supports_json,
        context_window: modelDraft.context_window ? Number(modelDraft.context_window) : null,
        enabled: modelDraft.enabled
      })
    });
    setModelDraft({ provider_id: "", model_name: "", display_name: "", context_window: "", supports_vision: false, supports_audio: false, supports_tools: false, supports_json: false, enabled: true });
    await refreshWorkspace();
  }

  async function createAgent(event: FormEvent) {
    event.preventDefault();
    await apiRequest("/api/admin/agents", {
      method: "POST",
      body: JSON.stringify({
        ...agentDraft,
        provider_id: agentDraft.provider_id ? Number(agentDraft.provider_id) : null,
        model_id: agentDraft.model_id ? Number(agentDraft.model_id) : null,
        temperature: 0.7,
        enabled: true
      })
    });
    setAgentDraft({ name: "", description: "", system_prompt: "", provider_id: "", model_id: "", internet_enabled: false, multimodal_enabled: false, agentic_mode: true });
    await refreshWorkspace();
  }

  async function toggleAgentSkill(agentId: number, skillId: number, enabled: boolean) {
    await apiRequest(`/api/admin/agents/${agentId}/skills/${skillId}`, { method: enabled ? "POST" : "DELETE" });
    await refreshWorkspace();
  }

  function editAgent(agent: Agent) {
    setAgentEditId(agent.id);
    setAgentEditDraft({
      name: agent.name,
      description: agent.description,
      system_prompt: agent.system_prompt ?? `You are ${agent.name}, a helpful ObsyGPT assistant.`,
      provider_id: agent.provider_id ? String(agent.provider_id) : "",
      model_id: agent.model_id ? String(agent.model_id) : "",
      temperature: String(agent.temperature ?? 0.7),
      internet_enabled: agent.internet_enabled,
      multimodal_enabled: agent.multimodal_enabled
    });
  }

  async function saveAgentEdit(agent: Agent, event: FormEvent) {
    event.preventDefault();
    setError("");
    try {
      await apiRequest(`/api/admin/agents/${agent.id}`, {
        method: "PATCH",
        body: JSON.stringify({
          name: agentEditDraft.name,
          description: agentEditDraft.description,
          system_prompt: agentEditDraft.system_prompt,
          provider_id: agentEditDraft.provider_id ? Number(agentEditDraft.provider_id) : null,
          model_id: agentEditDraft.model_id ? Number(agentEditDraft.model_id) : null,
          temperature: Number(agentEditDraft.temperature) || 0.7,
          internet_enabled: agentEditDraft.internet_enabled,
          multimodal_enabled: agentEditDraft.multimodal_enabled,
          agentic_mode: agent.agentic_mode,
          enabled: agent.enabled
        })
      });
      setAgentEditId(null);
      await refreshWorkspace();
    } catch (err) {
      setError(err instanceof Error ? err.message : "Agent update failed");
    }
  }

  async function toggleAgentAgentic(agent: Agent, agenticMode: boolean) {
    await apiRequest(`/api/admin/agents/${agent.id}`, {
      method: "PATCH",
      body: JSON.stringify({
        name: agent.name,
        description: agent.description,
        system_prompt: agent.system_prompt ?? `You are ${agent.name}, a helpful ObsyGPT assistant.`,
        provider_id: agent.provider_id,
        model_id: agent.model_id,
        temperature: Number(agent.temperature ?? 0.7),
        internet_enabled: agent.internet_enabled,
        multimodal_enabled: agent.multimodal_enabled,
        agentic_mode: agenticMode,
        enabled: agent.enabled
      })
    });
    await refreshWorkspace();
  }

  async function toggleAgentTool(agentId: number, toolName: string, enabled: boolean) {
    const current = agentTools.filter((item) => item.agent_id === agentId && item.allowed).map((item) => item.tool_name);
    const next = enabled ? Array.from(new Set([...current, toolName])) : current.filter((name) => name !== toolName);
    await apiRequest(`/api/admin/agents/${agentId}/tools`, { method: "PUT", body: JSON.stringify({ tools: next }) });
    await refreshWorkspace();
  }

  async function detectProviderModels(providerId: number) {
    setDetectingProvider(providerId);
    setError("");
    try {
      const data = await apiRequest<{ models: DetectedModel[] }>(`/api/admin/providers/${providerId}/detect-models`, { method: "POST" });
      setDetectedModels((current) => ({ ...current, [providerId]: data.models }));
    } catch (err) {
      setError(err instanceof Error ? err.message : "Model detection failed");
    } finally {
      setDetectingProvider(null);
    }
  }

  async function addAgentFallback(agentId: number) {
    const draft = fallbackDraft[agentId];
    if (!draft?.provider_id || !draft?.model_id) return;
    const current = agentFallbacks
      .filter((item) => item.agent_id === agentId)
      .sort((a, b) => a.priority - b.priority)
      .map((item) => ({ provider_id: item.provider_id, model_id: item.model_id }));
    const next = [...current, { provider_id: Number(draft.provider_id), model_id: Number(draft.model_id) }];
    await apiRequest(`/api/admin/agents/${agentId}/fallbacks`, { method: "PUT", body: JSON.stringify({ fallbacks: next }) });
    setFallbackDraft((current) => ({ ...current, [agentId]: { provider_id: "", model_id: "" } }));
    await refreshWorkspace();
  }

  async function removeAgentFallback(agentId: number, fallback: AgentFallback) {
    const next = agentFallbacks
      .filter((item) => item.agent_id === agentId && !(item.provider_id === fallback.provider_id && item.model_id === fallback.model_id))
      .sort((a, b) => a.priority - b.priority)
      .map((item) => ({ provider_id: item.provider_id, model_id: item.model_id }));
    await apiRequest(`/api/admin/agents/${agentId}/fallbacks`, { method: "PUT", body: JSON.stringify({ fallbacks: next }) });
    await refreshWorkspace();
  }

  async function toggleAgentMcp(agentId: number, mcpServerId: number, enabled: boolean) {
    await apiRequest(`/api/admin/agents/${agentId}/mcps/${mcpServerId}`, { method: enabled ? "POST" : "DELETE" });
    await refreshWorkspace();
  }

  async function createSkill(event: FormEvent) {
    event.preventDefault();
    const path = editingSkillId ? `/api/admin/skills/${editingSkillId}` : "/api/admin/skills";
    await apiRequest(path, { method: editingSkillId ? "PATCH" : "POST", body: JSON.stringify(skillDraft) });
    resetSkillEditor();
    setEditingSkillId(null);
    setSkillTab("library");
    await refreshWorkspace();
  }

  function editSkill(skill: Skill) {
    setSkillDraft({ name: skill.name, description: skill.description, argument_hint: skill.argument_hint, triggers: skill.triggers, body: skill.body, resources: skill.resources, enabled: skill.enabled });
    setEditingSkillId(skill.id);
    setSkillTab("editor");
  }

  function resetSkillEditor() {
    setSkillDraft({ name: "", description: "", argument_hint: "", triggers: ["user"], body: "# Instrucciones principales\n1. Describe el flujo de trabajo de la skill.\n\n## Restricciones\n* No ejecutes acciones destructivas sin confirmacion explicita.", resources: "", enabled: true });
    setEditingSkillId(null);
  }

  async function toggleSkill(skill: Skill, enabled: boolean) {
    await apiRequest(`/api/admin/skills/${skill.id}`, { method: "PATCH", body: JSON.stringify({ name: skill.name, description: skill.description, argument_hint: skill.argument_hint, triggers: skill.triggers, body: skill.body, resources: skill.resources, enabled }) });
    await refreshWorkspace();
  }

  async function deleteSkill(skill: Skill) {
    if (!window.confirm(`Borrar skill "${skill.name}"? Se quitará también de los agentes asignados.`)) return;
    await apiRequest(`/api/admin/skills/${skill.id}`, { method: "DELETE" });
    if (editingSkillId === skill.id) resetSkillEditor();
    await refreshWorkspace();
  }

  async function generateSkillDraft(event: FormEvent) {
    event.preventDefault();
    const data = await apiRequest<{ draft: SkillDraftResponse }>("/api/admin/skills/generate", {
      method: "POST",
      body: JSON.stringify({ prompt: skillGeneratorPrompt })
    });
    setGeneratedSkill(data.draft);
  }

  function useGeneratedSkill() {
    if (!generatedSkill) return;
    setSkillDraft({ name: generatedSkill.name, description: generatedSkill.description, argument_hint: generatedSkill.argument_hint, triggers: generatedSkill.triggers, body: generatedSkill.body, resources: generatedSkill.resources, enabled: true });
    setEditingSkillId(null);
    setSkillTab("editor");
  }

  async function createMcpServer(event: FormEvent) {
    event.preventDefault();
    await apiRequest("/api/admin/mcp-servers", {
      method: "POST",
      body: JSON.stringify({
        ...mcpDraft,
        command: mcpDraft.command || null,
        url: mcpDraft.url || null
      })
    });
    setMcpDraft({ name: "", description: "", connection_type: "command", command: "", url: "", enabled: false });
    await refreshWorkspace();
  }

  async function validateMcpServer() {
    const data = await apiRequest<{ validation: { valid: boolean; connection_type: string; command_args?: string[]; url?: string } }>("/api/admin/mcp-servers/validate", {
      method: "POST",
      body: JSON.stringify({
        ...mcpDraft,
        command: mcpDraft.command || null,
        url: mcpDraft.url || null
      })
    });
    setMcpValidation(JSON.stringify(data.validation, null, 2));
  }

  async function runMcpServer(event: FormEvent) {
    event.preventDefault();
    if (!mcpRunDraft.server_id) return;
    let params: Record<string, unknown>;
    try {
      params = JSON.parse(mcpRunDraft.params || "{}");
    } catch {
      setMcpRunResult("Invalid JSON params.");
      return;
    }

    const data = await apiRequest<{ response: unknown }>(`/api/admin/mcp-servers/${mcpRunDraft.server_id}/run`, {
      method: "POST",
      body: JSON.stringify({ method: mcpRunDraft.method, params })
    });
    setMcpRunResult(JSON.stringify(data.response, null, 2));
  }

  async function toggleMcpServer(server: McpServer, enabled: boolean) {
    await apiRequest(`/api/admin/mcp-servers/${server.id}`, {
      method: "PATCH",
      body: JSON.stringify({
        name: server.name,
        description: server.description,
        connection_type: server.connection_type,
        command: server.command,
        url: server.url,
        enabled
      })
    });
    await refreshWorkspace();
  }

  async function inspectMcpServer(server: McpServer) {
    setInspectingMcp(server.id);
    try {
      const data = await apiRequest<{ tools: Array<{ name: string; description?: string }> }>(`/api/admin/mcp-servers/${server.id}/inspect`, { method: "POST" });
      setMcpInspection({ serverId: server.id, tools: data.tools });
    } catch (error) {
      setMcpInspection(null);
      setMcpRunResult(`Inspección de ${server.name} fallida: ${error instanceof Error ? error.message : "error"}`);
    } finally {
      setInspectingMcp(null);
    }
  }

  async function deleteMcpServer(server: McpServer) {
    await apiRequest(`/api/admin/mcp-servers/${server.id}`, { method: "DELETE" });
    if (mcpInspection?.serverId === server.id) setMcpInspection(null);
    await refreshWorkspace();
  }

  async function connectConnector(slug: string) {
    const token = connectorTokenDrafts[slug]?.trim();
    if (!token) return;
    setConnectorBusy(slug);
    setConnectorMessage("");
    try {
      const data = await apiRequest<{ verification: { detail: string } }>(`/api/connectors/${slug}/accounts`, {
        method: "POST",
        body: JSON.stringify({ token })
      });
      setConnectorMessage(`Conectado: ${data.verification.detail}`);
      setConnectorTokenDrafts((current) => ({ ...current, [slug]: "" }));
      await refreshWorkspace();
    } catch (error) {
      setConnectorMessage(`No se pudo conectar: ${error instanceof Error ? error.message : "error"}`);
    } finally {
      setConnectorBusy(null);
    }
  }

  async function disconnectConnector(connector: CatalogConnector) {
    if (!connector.account) return;
    setConnectorBusy(connector.slug);
    try {
      await apiRequest(`/api/connectors/accounts/${connector.account.id}`, { method: "DELETE" });
      setConnectorMessage(`${connector.name} desconectado.`);
      await refreshWorkspace();
    } finally {
      setConnectorBusy(null);
    }
  }

  async function testConnectorAccount(connector: CatalogConnector) {
    if (!connector.account) return;
    setConnectorBusy(connector.slug);
    try {
      const data = await apiRequest<{ ok: boolean; detail: string }>(`/api/connectors/accounts/${connector.account.id}/test`, { method: "POST" });
      setConnectorMessage(`${connector.name}: ${data.ok ? "token válido" : "token inválido"} · ${data.detail}`);
    } catch (error) {
      setConnectorMessage(`Fallo el test: ${error instanceof Error ? error.message : "error"}`);
    } finally {
      setConnectorBusy(null);
    }
  }

  async function toggleWorkflow(workflow: Workflow, enabled: boolean) {
    const agentIds = metadata.workflowSteps
      .filter((step) => step.workflow_id === workflow.id)
      .sort((a, b) => a.step_order - b.step_order)
      .map((step) => step.agent_id);

    await apiRequest(`/api/admin/workflows/${workflow.id}`, {
      method: "PATCH",
      body: JSON.stringify({
        name: workflow.name,
        workflow_type: workflow.workflow_type,
        agent_ids: agentIds,
        enabled
      })
    });
    await refreshWorkspace();
  }

  async function toggleAgent(agent: Agent, enabled: boolean) {
    await apiRequest(`/api/admin/agents/${agent.id}`, {
      method: "PATCH",
      body: JSON.stringify({
        name: agent.name,
        description: agent.description,
        system_prompt: agent.system_prompt || `You are ${agent.name}.`,
        provider_id: agent.provider_id,
        model_id: agent.model_id,
        temperature: Number(agent.temperature),
        internet_enabled: agent.internet_enabled,
        multimodal_enabled: agent.multimodal_enabled,
        enabled
      })
    });
    await refreshWorkspace();
  }

  async function toggleProvider(provider: Provider, enabled: boolean) {
    await apiRequest(`/api/admin/providers/${provider.id}`, {
      method: "PATCH",
      body: JSON.stringify({
        name: provider.name,
        provider_type: provider.provider_type,
        base_url: provider.base_url,
        api_key_env: provider.api_key_env,
        enabled
      })
    });
    await refreshWorkspace();
  }

  async function toggleModel(model: Model, enabled: boolean) {
    await apiRequest(`/api/admin/models/${model.id}`, {
      method: "PATCH",
      body: JSON.stringify({
        provider_id: model.provider_id,
        model_name: model.model_name,
        display_name: model.display_name,
        supports_text: model.supports_text,
        supports_streaming: model.supports_streaming,
        supports_vision: model.supports_vision,
        supports_audio: model.supports_audio,
        supports_tools: model.supports_tools,
        supports_json: model.supports_json,
        context_window: model.context_window,
        enabled
      })
    });
    await refreshWorkspace();
  }

  async function deleteModel(model: Model) {
    await apiRequest(`/api/admin/models/${model.id}`, { method: "DELETE" });
    await refreshWorkspace();
  }

  async function checkModel(model: Model) {
    const data = await apiRequest<ModelCheckResponse>(`/api/admin/models/${model.id}/check`, { method: "POST" });
    setModelCheckResult(data);
  }

  async function runReadUrl(event: FormEvent) {
    event.preventDefault();
    const data = await apiRequest<{ result: { title: string; content: string; url: string } }>("/api/admin/skills/run", {
      method: "POST",
      body: JSON.stringify({ skill_name: "read_url", payload: { url: internetUrl } })
    });
    setSkillResult(`${data.result.title}\n${data.result.url}\n\n${data.result.content.slice(0, 900)}`);
  }

  async function createWorkflow(event: FormEvent) {
    event.preventDefault();
    await apiRequest("/api/admin/workflows", {
      method: "POST",
      body: JSON.stringify({ ...workflowDraft, enabled: true })
    });
    setWorkflowDraft({ name: "", workflow_type: "sequential", agent_ids: [] });
    await refreshWorkspace();
  }

  async function updateUserRole(userId: number, role: "admin" | "user") {
    await apiRequest(`/api/admin/users/${userId}/role`, {
      method: "PATCH",
      body: JSON.stringify({ role })
    });
    await refreshSession();
    try {
      await refreshWorkspace();
    } catch (err) {
      setError(err instanceof Error ? err.message : "Workspace refresh failed");
    }
  }

  function formatAuditMetadata(metadata: Record<string, unknown>) {
    const entries = Object.entries(metadata).filter(([, value]) => value !== null && value !== undefined);
    if (entries.length === 0) return "No metadata";
    return entries.map(([key, value]) => `${key}: ${typeof value === "object" ? JSON.stringify(value) : String(value)}`).join(" | ");
  }

  function formatDateTime(value: string) {
    return new Date(value).toLocaleString();
  }

  function auditLogPath() {
    const params = new URLSearchParams({ limit: "50" });
    if (auditFilters.action.trim()) params.set("action", auditFilters.action.trim());
    if (auditFilters.target_type) params.set("target_type", auditFilters.target_type);
    return `/api/admin/audit-logs?${params.toString()}`;
  }

  const selectedAgent = selectedAgentId ? metadata.agents.find((agent) => agent.id === Number(selectedAgentId)) : metadata.agents[0];
  const selectedWorkflow = selectedWorkflowId ? metadata.workflows.find((workflow) => workflow.id === Number(selectedWorkflowId)) : null;
  const activeProvider = selectedAgent?.provider_id ? metadata.providers.find((provider) => provider.id === selectedAgent.provider_id) : null;
  const activeModel = selectedAgent?.model_id ? metadata.models.find((model) => model.id === selectedAgent.model_id) : null;
  const activeSkillIds = selectedAgent ? metadata.agentSkills.filter((assignment) => assignment.agent_id === selectedAgent.id).map((assignment) => assignment.skill_id) : [];
  const activeMcpIds = selectedAgent ? metadata.agentMcps.filter((assignment) => assignment.agent_id === selectedAgent.id).map((assignment) => assignment.mcp_server_id) : [];
  const activeSkills = metadata.skills.filter((skill) => activeSkillIds.includes(skill.id));
  const activeMcps = metadata.mcpServers.filter((server) => activeMcpIds.includes(server.id));
  const approximateTokens = Math.ceil(messages.reduce((total, message) => total + message.content.length, 0) / 4);
  const settingsTabDefs: Array<{ id: SettingsTab; label: string }> = [
    { id: "modelo", label: "Modelo" },
    { id: "preferencias", label: "Preferencias" },
    { id: "seguridad", label: "Seguridad" },
    { id: "agente", label: "Agente" },
    { id: "datos", label: "Datos" },
    { id: "admin", label: "Administración" }
  ];
  const adminSections: Array<{ id: AdminSection; label: string }> = [
    { id: "agents", label: "Agentes" },
    { id: "models", label: "Modelos" },
    { id: "workflows", label: "Workflows" },
    { id: "mcps", label: "MCPs" },
    { id: "plugins", label: "Plugins" },
    { id: "users", label: "Usuarios" },
    { id: "audit", label: "Auditoría" }
  ];
  const settingsIndex: Array<{ label: string; keywords: string; tab: SettingsTab; section?: AdminSection }> = [
    { label: "Activar modelo", keywords: "modelo provider proveedor detectar activar api cambiar", tab: "modelo" },
    { label: "Proveedores guardados", keywords: "provider proveedor base url api key url endpoint", tab: "modelo" },
    { label: "Instrucciones personales", keywords: "instrucciones personales prompt global todos los chats estilo tono", tab: "preferencias" },
    { label: "Tu nombre", keywords: "personal nombre identidad display", tab: "preferencias" },
    { label: "Color de acento", keywords: "apariencia color tema acento interfaz oro teal violeta", tab: "preferencias" },
    { label: "Espacio de trabajo", keywords: "workspace carpeta ruta archivos comandos proyecto", tab: "preferencias" },
    { label: "Atajos de teclado", keywords: "atajos alt modo skills paleta teclado", tab: "preferencias" },
    { label: "Permisos por herramienta", keywords: "permisos herramientas permitir preguntar bloquear seguridad terminal ejecutar", tab: "seguridad" },
    { label: "Límites de ejecución", keywords: "limites iteraciones herramientas duracion bucle guardrails pasos", tab: "seguridad" },
    { label: "Memoria", keywords: "memoria recuerdos contexto inyeccion", tab: "agente" },
    { label: "Tareas en segundo plano", keywords: "tareas simultaneas concurrencia recuperacion background", tab: "agente" },
    { label: "Hábitos aprendidos", keywords: "habitos aprendizaje reset reiniciar datos", tab: "datos" },
    { label: "Agentes", keywords: "agentes agentic tools fallbacks skills permisos prompts agents", tab: "admin", section: "agents" },
    { label: "Modelos", keywords: "modelos crear habilitar vision json models", tab: "admin", section: "models" },
    { label: "Workflows", keywords: "workflows flujos secuencial debate supervisor paralelo", tab: "admin", section: "workflows" },
    { label: "MCPs", keywords: "mcp servidores herramientas externas command url", tab: "admin", section: "mcps" },
    { label: "Usuarios", keywords: "usuarios roles admin permisos cuentas users", tab: "admin", section: "users" },
    { label: "Auditoría", keywords: "audit auditoria logs cambios trazas eventos", tab: "admin", section: "audit" }
  ];
  const settingsResults = settingsSearch.trim()
    ? settingsIndex.filter((item) => `${item.label} ${item.keywords}`.toLowerCase().includes(settingsSearch.trim().toLowerCase()))
    : [];
  const filteredSkills = metadata.skills.filter((skill) => `${skill.name} ${skill.description}`.toLowerCase().includes(skillSearch.toLowerCase()));

  const missingConnectorsFor = (entry: PluginCatalogEntry) => entry.connectors.filter((connector) => !catalogConnectors.some((catalog) => catalog.slug === connector && catalog.account));
  const paletteQuery = draft.startsWith("/") && !draft.includes(" ") ? draft.slice(1).toLowerCase() : null;
  const paletteSkills = paletteQuery === null ? [] : metadata.skills.filter((skill) => skill.enabled && skill.name.toLowerCase().includes(paletteQuery)).slice(0, 6);
  const paletteOpen = paletteQuery !== null && paletteSkills.length > 0;
  const activeTaskCount = tasks.filter((task) => ["pending", "scheduled", "running", "awaiting_approval"].includes(task.status)).length;

  function cycleChatMode() {
    setChatMode((current) => (current === "act" ? "plan" : current === "plan" ? "think" : "act"));
  }

  function selectPaletteSkill(skillName: string) {
    setDraft(`/${skillName} `);
    setPaletteIndex(0);
  }

  function handleComposerKeyDown(event: ReactKeyboardEvent<HTMLTextAreaElement>) {
    if (event.altKey && (event.key === "m" || event.key === "M")) {
      event.preventDefault();
      cycleChatMode();
      return;
    }
    if (paletteOpen) {
      if (event.key === "Escape") {
        event.preventDefault();
        setDraft("");
        setPaletteIndex(0);
        return;
      }
      if (event.key === "ArrowDown") {
        event.preventDefault();
        setPaletteIndex((current) => (current + 1) % paletteSkills.length);
        return;
      }
      if (event.key === "ArrowUp") {
        event.preventDefault();
        setPaletteIndex((current) => (current - 1 + paletteSkills.length) % paletteSkills.length);
        return;
      }
      if (event.key === "Enter" || event.key === "Tab") {
        event.preventDefault();
        selectPaletteSkill(paletteSkills[Math.min(paletteIndex, paletteSkills.length - 1)].name);
        return;
      }
    }
  }

  function skillAgents(skillId: number) {
    const agentIds = metadata.agentSkills.filter((assignment) => assignment.skill_id === skillId).map((assignment) => assignment.agent_id);
    return metadata.agents.filter((agent) => agentIds.includes(agent.id));
  }

  function openSettings(section: SettingsSection) {
    setSettingsTab("admin");
    setSettingsSection(section);
    setActiveView("settings");
  }

  function navButton(view: AppView, label: string, short?: string, badge?: number) {
    return <button className={activeView === view ? "active" : ""} onClick={() => setActiveView(view)}>{leftSidebarCollapsed ? (short ?? label.slice(0, 2)) : label}{badge !== undefined && badge > 0 && <span className="nav-badge">{badge > 99 ? "99+" : badge}</span>}</button>;
  }

  if (!session) {
    return (
      <main className="auth-screen">
        <section className="auth-card">
          <p className="eyebrow">Obsessive Solutions</p>
          <h1>Detalle obsesivo para agentes excepcionales.</h1>
          <p className="auth-copy">Entra a ObsyGPT para orquestar proveedores, agentes, skills, MCPs y trazas con precisión quirúrgica.</p>
          <HealthLine health={health} />
          <form onSubmit={handleAuth} className="auth-form">
            <input value={username} onChange={(event) => setUsername(event.target.value)} placeholder="Username" required />
            {authMode === "register" && <input value={email} onChange={(event) => setEmail(event.target.value)} placeholder="Email" type="email" required />}
            <input value={password} onChange={(event) => setPassword(event.target.value)} placeholder="Password" type="password" required />
            {authMode === "register" && <p className="muted">Password must be at least 8 characters and include letters and numbers.</p>}
            {authMode === "register" && <input value={confirmPassword} onChange={(event) => setConfirmPassword(event.target.value)} placeholder="Confirm password" type="password" required />}
          {error && <p className="error">{error}</p>}
            <button>{authMode === "login" ? "Entrar" : "Crear acceso"}</button>
          </form>
          <button className="text-button" onClick={() => setAuthMode(authMode === "login" ? "register" : "login")}>{authMode === "login" ? "¿Sin cuenta? Crear acceso" : "Ya tengo acceso"}</button>
        </section>
      </main>
    );
  }

  const isAdmin = session.role === "admin";

  return (
    <main className={`workspace-shell ${leftSidebarCollapsed ? "nav-collapsed" : ""} ${rightSidebarOpen ? "" : "right-collapsed"}`}>
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
        {!leftSidebarCollapsed && <div className="conversation-list-block"><div className="sidebar-list-head"><p className="eyebrow">Conversaciones ({conversations.length})</p><button className="text-button new-folder-button" onClick={() => void createFolder()}>+ Carpeta</button></div>{conversations.length === 0 ? <p className="empty-sidebar-note">No hay conversaciones para {session.username}.</p> : <nav>
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
          <button className="user-menu-trigger" onClick={() => setUserMenuOpen((value) => !value)}>
            <strong>{session.username}</strong>
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
          <button className="logout icon-button" onClick={() => setUserMenuOpen((value) => !value)} aria-label="User menu">{session.username.slice(0, 1).toUpperCase()}</button>
          {userMenuOpen && <div className="user-menu collapsed-menu">
            {isAdmin && <button onClick={() => { setLeftSidebarCollapsed(false); openSettings("agents"); setUserMenuOpen(false); }}>Configuración</button>}
            {isAdmin && <button onClick={() => { setLeftSidebarCollapsed(false); setSettingsTab("admin"); setSettingsSection("audit"); setActiveView("settings"); setUserMenuOpen(false); }}>Audit logs</button>}
            {isAdmin && <button onClick={() => { setLeftSidebarCollapsed(false); setActiveView("diagnostics"); setUserMenuOpen(false); }}>Diagnostics</button>}
            <button onClick={logout}>Cerrar sesión</button>
          </div>}
        </div>}
      </aside>

      <section className="main-stage">
        <header className="top-bar">
          <div>
            <p className="eyebrow">Obsessive Solutions</p>
            <h1>{activeView === "chat" ? (selectedAgent?.name ?? "ObsyGPT") : activeView === "tasks" ? "Tareas" : activeView === "projects" ? "Proyectos" : activeView === "memory" ? "Memoria" : activeView === "skills" ? "Skills" : activeView === "tools" ? "Herramientas" : activeView === "connectors" ? "Conectores" : activeView === "history" ? "Historial" : activeView === "settings" ? "Ajustes" : activeView === "trace" ? "Traza de runs" : activeView === "monitoring" ? "Monitoring" : "Diagnostics"}</h1>
          </div>
          <button className="details-button" onClick={() => setRightSidebarOpen((value) => !value)}>{rightSidebarOpen ? "Ocultar actividad" : "Actividad"}</button>
        </header>

        {activeView === "chat" && <section className="chat-column">
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
          <div className="message-stack">
            {messages.length === 0 && <div className="empty-state">¿Qué resolvemos hoy?</div>}
            {messages.map((message, index) => (
              <article className={`message ${message.role}${message.role === "assistant" ? " md-message" : ""}`} key={`${message.role}-${index}`}>
                {editingMessageIndex === index
                  ? <div className="message-edit">
                      <textarea value={editingMessageDraft} onChange={(event) => setEditingMessageDraft(event.target.value)} rows={4} autoFocus />
                      <div className="message-edit-actions">
                        <button type="button" onClick={() => void saveEditMessage(index)}>Guardar</button>
                        <button type="button" className="text-button" onClick={() => { setEditingMessageIndex(null); setEditingMessageDraft(""); }}>Cancelar</button>
                      </div>
                    </div>
                  : <>
                      <div className="message-body">{message.role === "assistant" ? renderMarkdown(message.content || "Pensando...") : message.content}</div>
                      <div className="message-actions">
                        <button type="button" className="text-button" onClick={() => void copyMessageText(message.content, index)} title="Copiar">{copiedMessageIndex === index ? "✓" : "⧉"}</button>
                        {message.role === "user" && <button type="button" className="text-button" onClick={() => startEditMessage(index, message.content)} title="Editar">✎</button>}
                      </div>
                    </>}
              </article>
            ))}
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
          {error && <p className="error">{error}</p>}
          <div className="runtime-context-bar">
            <span><strong>Provider</strong>{activeProvider?.name ?? "Default"}</span>
            <span><strong>Model</strong>{activeModel?.display_name ?? activeModel?.model_name ?? "Default"}</span>
            <span><strong>Agent</strong>{selectedAgent?.name ?? "Default"}</span>
            {activeProjectName && <span><strong>Proyecto</strong>{activeProjectName}</span>}
            <span><strong>Workflow</strong>{selectedWorkflow?.name ?? "None"}</span>
            <span><strong>Tokens</strong>{approximateTokens.toLocaleString()}</span>
          </div>
          {liveActivity && (() => {
            const elapsed = Math.max(0, Math.floor((nowTick - liveActivity.startedAt) / 1000));
            const stale = Math.floor((nowTick - liveActivity.lastAt) / 1000);
            const mm = String(Math.floor(elapsed / 60)).padStart(2, "0");
            const ss = String(elapsed % 60).padStart(2, "0");
            const tokens = Math.round((liveActivity.chars ?? 0) / 4);
            return (
              <div className={`live-activity${stale > 45 ? " stale" : ""}`} role="status">
                <span className="live-dot" aria-hidden="true" />
                <span className="live-elapsed">⏱ {mm}:{ss}</span>
                {liveActivity.iteration !== undefined && <span className="live-iter">iter {liveActivity.iteration}</span>}
                {tokens > 0 && <span className="live-tokens">~{tokens.toLocaleString()} tokens</span>}
                <span className="live-label">{liveActivity.label}{liveActivity.detail ? ` (${liveActivity.detail})` : ""}</span>
                {stale > 45 && <span className="live-stale">sin señal nueva hace {stale}s</span>}
              </div>
            );
          })()}
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
        </section>}

        {activeView === "tasks" && <section className="panel full-panel tasks-view">
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
            {task.result && <p className="task-result">{task.result.slice(0, 400)}</p>}
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
        </section>}

        {activeView === "projects" && <section className="panel full-panel projects-view">
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
                {task.result && <p className="task-result">{task.result.slice(0, 300)}</p>}
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
        </section>}

        {activeView === "memory" && <section className="panel full-panel">
          <h2>Memoria</h2>
          <form className="task-create" onSubmit={addMemory}>
            <input value={memoryDraft.content} onChange={(event) => setMemoryDraft({ ...memoryDraft, content: event.target.value })} placeholder="Anade algo que ObsyGPT debe recordar..." required />
            <select value={memoryDraft.kind} onChange={(event) => setMemoryDraft({ ...memoryDraft, kind: event.target.value })}><option value="memory">Memoria</option><option value="habit">Habito</option></select>
            <button type="submit">Anadir</button>
          </form>
          {habitSuggestions.length > 0 && <>
            <h3>Hábitos detectados ({habitSuggestions.length})</h3>
            {habitSuggestions.map((suggestion) => <div className="suggestion-row" key={suggestion.id}>
              <div className="suggestion-copy">
                <span>{suggestion.content}</span>
                {suggestion.evidence && <small className="muted">“{suggestion.evidence}” · {suggestion.source === "heuristic" ? "patrón de uso" : "análisis IA"}</small>}
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
        </section>}

        {activeView === "tools" && <section className="panel full-panel">
          <h2>Herramientas</h2>
          <p className="muted">Herramientas disponibles para los agentes. Permisos por agente en Ajustes, Administracion, Agents; politicas personales en Ajustes, Seguridad.</p>
          <div className="skill-grid">{toolDefinitions.map((tool) => <article className="skill-card" key={tool.name}>
            <div className="skill-card-head"><div><strong>{tool.name}</strong><span>{tool.permission === "safe" ? "segura" : "sensible: requiere aprobacion"}</span></div></div>
            <p>{tool.description}</p>
            <pre className="skill-md-preview">{tool.parameters}</pre>
          </article>)}</div>
        </section>}

        {activeView === "connectors" && <section className="panel full-panel">
          <h2>Conectores</h2>
          <p className="muted">Conecta tus cuentas para que los agentes puedan usarlas. Los tokens se guardan cifrados y las herramientas sensibles piden aprobación. Actívalas por agente en Ajustes, Administración, Agents.</p>
          {connectorMessage && <p className="muted">{connectorMessage}</p>}
          <div className="skill-grid">{catalogConnectors.map((connector) => <article className="skill-card" key={connector.slug}>
            <div className="skill-card-head"><div><strong>{connector.name}</strong><span>{connector.account ? `Conectado · ${connector.account.display_name || connector.account.status}` : "Sin conectar"}</span></div></div>
            <p>{connector.description}</p>
            <div className="chip-row">{connector.tool_names.map((toolName) => <span className="chip" key={toolName}>{toolName}</span>)}</div>
            {connector.account ? <div className="skill-actions">
              <button className="text-button" disabled={connectorBusy === connector.slug} onClick={() => void testConnectorAccount(connector)}>{connectorBusy === connector.slug ? "Probando..." : "Probar token"}</button>
              <button className="text-button danger" disabled={connectorBusy === connector.slug} onClick={() => void disconnectConnector(connector)}>Desconectar</button>
            </div> : <form className="task-create" onSubmit={(event) => { event.preventDefault(); void connectConnector(connector.slug); }}>
              <input type="password" value={connectorTokenDrafts[connector.slug] ?? ""} onChange={(event) => setConnectorTokenDrafts((current) => ({ ...current, [connector.slug]: event.target.value }))} placeholder={connector.token_label} required />
              <button type="submit" disabled={connectorBusy === connector.slug}>{connectorBusy === connector.slug ? "Conectando..." : "Conectar"}</button>
            </form>}
            <details className="card-details"><summary>Cómo obtener el token</summary><p className="muted">{connector.token_help}</p></details>
          </article>)}</div>
        </section>}

        {activeView === "history" && <section className="panel full-panel">
          <h2>Historial</h2>
          <div className="audit-filters"><input value={historySearch} onChange={(event) => setHistorySearch(event.target.value)} placeholder="Buscar conversaciones..." /></div>
          {conversations.filter((conversation) => (conversation.label ?? conversation.title).toLowerCase().includes(historySearch.toLowerCase())).length === 0 ? <p className="muted">Sin conversaciones que coincidan.</p> : conversations.filter((conversation) => (conversation.label ?? conversation.title).toLowerCase().includes(historySearch.toLowerCase())).map((conversation) => (
            <div className="conversation-row history-row" key={conversation.id}>
              <button className={conversation.id === activeConversationId ? "active" : ""} onClick={() => { setActiveConversationId(conversation.id); setActiveView("chat"); }}>{conversation.label ?? conversation.title}</button>
              <button className="text-button" onClick={() => renameConversation(conversation)} type="button">Renombrar</button>
              <button className="text-button danger" onClick={() => deleteConversation(conversation)} type="button">Borrar</button>
            </div>
          ))}
        </section>}

        {activeView === "trace" && <section className="panel full-panel"><h2>Traza de runs</h2>{runs.length === 0 ? <p className="muted">Sin runs registrados en esta conversacion.</p> : runs.map((run) => <div className="trace-run" key={run.id}><div className="trace-run-head"><strong>{run.parent_run_id ? `↳ Run #${run.id} (sub-agente de #${run.parent_run_id})` : `Run #${run.id}`}</strong><span className={`chip ${run.status === "completed" ? "muted-chip" : "agentic-chip"}`}>{run.status}</span></div>{run.final_response && <p className="muted">{run.final_response.slice(0, 300)}...</p>}<div className="trace-section"><h3>Eventos</h3>{events.length === 0 ? <p className="muted">Sin eventos.</p> : events.slice(0, 20).map((event) => <div className="trace-event" key={event.id}><strong>{event.title}</strong><span>{event.created_at ? formatDateTime(event.created_at) : ""}</span>{event.content && <small>{event.content.slice(0, 220)}</small>}</div>)}</div><div className="trace-section"><h3>Tool calls</h3>{toolCalls.length === 0 ? <p className="muted">Sin tool calls.</p> : toolCalls.map((toolCall) => <div className="tool-call" key={toolCall.id}><strong>{toolCall.skill_name}</strong><span>{toolCall.status}: {toolCall.input_summary}</span><small>{toolCall.output_summary}</small></div>)}</div><div className="trace-section"><h3>Fuentes</h3>{sources.length === 0 ? <p className="muted">Sin fuentes.</p> : sources.map((source) => <a className="source-link" href={source.url} target="_blank" rel="noreferrer" key={source.id}>{source.title} — {source.url}</a>)}</div></div>)}</section>}

        {activeView === "settings" && <section className="settings-layout">
          <nav className="settings-nav">
            <p className="nav-group-label">Ajustes</p>
            {settingsTabDefs.filter((tab) => tab.id !== "admin").map((tab) => (
              <button key={tab.id} className={settingsTab === tab.id ? "active" : ""} onClick={() => setSettingsTab(tab.id)}>{tab.label}</button>
            ))}
            {isAdmin && <>
              <p className="nav-group-label">Administración</p>
              <div className="admin-sub">
                {adminSections.map((section) => (
                  <button key={section.id} className={settingsTab === "admin" && settingsSection === section.id ? "active" : ""} onClick={() => { setSettingsTab("admin"); setSettingsSection(section.id); }}>{section.label}</button>
                ))}
              </div>
            </>}
          </nav>
          <div className="settings-content">
            <div className="settings-heading">
              <div className="settings-heading-row">
                <h2 className="settings-view-title">{settingsTab === "admin" ? (adminSections.find((section) => section.id === settingsSection)?.label ?? "Administración") : (settingsTabDefs.find((tab) => tab.id === settingsTab)?.label ?? "Ajustes")}</h2>
                <input className="settings-search" value={settingsSearch} onChange={(event) => setSettingsSearch(event.target.value)} placeholder="Buscar en ajustes..." />
              </div>
              <div className="active-model-card">
                <div className="ac-main"><b>{activeModel?.display_name ?? activeModel?.model_name ?? "Sin modelo activo"}</b><small>{activeProvider?.name ?? "Elige un proveedor y activa un modelo para empezar."}</small></div>
                <span className={`ac-badge ${activeModel?.enabled && activeProvider?.enabled ? "on" : "off"}`}>{activeModel?.enabled && activeProvider?.enabled ? "activo" : "sin activar"}</span>
              </div>
            </div>
            {settingsSearch.trim() !== "" && <section className="panel"><h2>Resultados</h2>{settingsResults.length === 0 ? <p className="muted">Ningún ajuste coincide con esa búsqueda.</p> : settingsResults.map((item) => <button type="button" className="settings-result" key={item.label} onClick={() => { setSettingsTab(item.tab); if (item.section) setSettingsSection(item.section); setSettingsSearch(""); }}>{item.label}<small>{settingsTabDefs.find((tab) => tab.id === item.tab)?.label}</small></button>)}</section>}
            {settingsSearch.trim() === "" && settingsTab === "modelo" && <><section className="panel"><h2>Proveedor y modelo</h2><p className="muted">Selecciona proveedor, detecta modelos y activa uno para el agente por defecto.</p><div className="modelo-controls">
              <select value={String(selectedAgent?.provider_id ?? "")} onChange={(event) => { const providerId = Number(event.target.value); const firstModel = metadata.models.find((model) => model.enabled && model.provider_id === providerId); if (isAdmin && providerId && firstModel) { void activateModel(providerId, firstModel.id); } }}><option value="">Proveedor...</option>{metadata.providers.filter((provider) => provider.enabled).map((provider) => <option value={provider.id} key={provider.id}>{provider.name}</option>)}</select>
              <select value={String(selectedAgent?.model_id ?? "")} onChange={(event) => { const modelId = Number(event.target.value); const providerId = selectedAgent?.provider_id ?? metadata.providers.find((provider) => provider.enabled)?.id; if (isAdmin && modelId && providerId) { void activateModel(providerId, modelId); } }}><option value="">Modelo...</option>{metadata.models.filter((model) => model.enabled && model.provider_id === (selectedAgent?.provider_id ?? -1)).map((model) => <option value={model.id} key={model.id}>{model.display_name}</option>)}</select>
            </div>{!isAdmin && <p className="muted">Solo un admin puede activar modelos.</p>}</section>
            <section className="panel"><h2>Proveedores guardados</h2>{isAdmin && <ConfigForm onSubmit={createProvider} submitLabel="Añadir provider"><input value={providerDraft.name} onChange={(event) => setProviderDraft({ ...providerDraft, name: event.target.value })} placeholder="Provider name" required /><select value={providerDraft.provider_type} onChange={(event) => setProviderDraft({ ...providerDraft, provider_type: event.target.value })}>{metadata.providerDefinitions.map((definition) => <option value={definition.provider_type} key={definition.provider_type}>{definition.display_name}</option>)}</select><input value={providerDraft.base_url} onChange={(event) => setProviderDraft({ ...providerDraft, base_url: event.target.value })} placeholder="Base URL" /><input value={providerDraft.api_key_env} onChange={(event) => setProviderDraft({ ...providerDraft, api_key_env: event.target.value })} placeholder="API key env var" /><label><input type="checkbox" checked={providerDraft.enabled} onChange={(event) => setProviderDraft({ ...providerDraft, enabled: event.target.checked })} /> Enabled</label></ConfigForm>}{metadata.providers.map((provider) => <div className="provider-row-block" key={provider.id}><label className="attachment-row"><span>{provider.name} ({provider.provider_type})</span>{isAdmin && <button type="button" className="text-button" disabled={detectingProvider !== null} onClick={() => detectProviderModels(provider.id)}>{detectingProvider === provider.id ? "Detectando..." : "Detectar modelos"}</button>}{isAdmin && <input type="checkbox" checked={provider.enabled} onChange={(event) => toggleProvider(provider, event.target.checked)} />}</label>{detectedModels[provider.id] && <div className="detect-results">{detectedModels[provider.id].slice(0, 12).map((model) => <span className={`chip ${model.already_registered ? "muted-chip" : ""}`} key={model.model_name}>{model.model_name}{model.already_registered ? " · registrado" : ""}</span>)}</div>}</div>)}</section></>}

            {settingsSearch.trim() === "" && settingsTab === "preferencias" && <><section className="panel"><h2>Instrucciones para ObsyGPT</h2><p className="muted">ObsyGPT tendrá esto en cuenta en todos los chats siempre que no entren en conflicto con lo que pidas en la conversación. No se aplicará a las tareas en segundo plano ni a los workflows.</p>
            <div className="instructions-block">
              <textarea className="instructions-textarea" rows={6} value={preferences?.instructions ?? ""} onChange={(event) => setPreferences((current) => (current ? { ...current, instructions: event.target.value } : current))} onBlur={() => void savePreferences({ instructions: preferences?.instructions ?? "" })} placeholder="Ej.: responde siempre en español, sé breve y directo, cita las fuentes con enlaces, usa tablas para comparativas..." />
              <div className="instructions-meta"><span className="muted">Se guarda al salir del campo</span><span className="muted">{(preferences?.instructions ?? "").length}/4000</span></div>
            </div></section>
            <section className="panel"><h2>Personal</h2><div className="swrow"><span className="st"><b>Tu nombre</b><small>ObsyGPT lo usa para dirigirse a ti y personalizar el contexto.</small></span><input value={preferences?.display_name ?? ""} onChange={(event) => setPreferences((current) => (current ? { ...current, display_name: event.target.value } : current))} onBlur={() => void savePreferences({ display_name: preferences?.display_name ?? "" })} placeholder="Tu nombre" /></div><div className="swrow"><span className="st"><b>Color de acento</b><small>Tiñe bordes, chips y botones de toda la interfaz.</small></span><select value={preferences?.accent ?? "gold"} onChange={(event) => void savePreferences({ accent: event.target.value })}><option value="gold">Oro</option><option value="teal">Teal</option><option value="violet">Violeta</option><option value="magenta">Magenta</option><option value="ice">Hielo</option></select></div></section>
            <section className="panel"><h2>Espacio de trabajo</h2><p className="muted">Carpeta donde el agente crea archivos y ejecuta comandos. Las rutas relativas aterrizan aqui.</p><form className="task-create" onSubmit={saveWorkspace}><input value={workspaceDraft} onChange={(event) => setWorkspaceDraft(event.target.value)} placeholder="C:\ruta\absoluta\del\proyecto" /><button type="submit" disabled={workspaceDraft === (workspaceInfo?.workspace ?? "")}>Guardar</button></form>{workspaceInfo && <><p className="muted">Activo: <code>{workspaceInfo.workspace}</code>{workspaceInfo.workspace !== workspaceInfo.default ? <> · por defecto: <code>{workspaceInfo.default}</code></> : null}</p>{workspaceInfo.recent.length > 0 && <div className="chip-row">{workspaceInfo.recent.map((recent) => <button type="button" className="chip" key={recent} onClick={() => setWorkspaceDraft(recent)}>{recent}</button>)}</div>}</>}</section>
            <section className="panel"><h2>Atajos</h2><div className="swrow"><span className="st"><b>Cambiar de modo (Act / Plan / Think)</b></span><span className="kbd">Alt</span><span className="kbd">M</span></div><div className="swrow"><span className="st"><b>Paleta de skills en el chat</b></span><span className="kbd">/</span></div></section></>}

            {settingsSearch.trim() === "" && settingsTab === "seguridad" && <><section className="panel"><h2>Permisos por herramienta</h2><p className="muted">Definen qué puede hacer el agente sin preguntarte: las seguras se ejecutan solas, las sensibles piden aprobacion salvo que las bloquees o las permitas siempre. Permisos por agente en Administracion, Agents.</p><div className="policy-list">{toolDefinitions.map((tool) => { const policy = preferences?.tool_policies?.[tool.name] ?? (tool.permission === "sensitive" ? "ask" : "allow"); return <div className="policy-row" key={tool.name}><span className="st"><b>{tool.name}</b><small>{tool.permission === "safe" ? "Segura" : "Sensible"}</small></span><select value={policy} onChange={(event) => void savePreferences({ tool_policies: { ...(preferences?.tool_policies ?? {}), [tool.name]: event.target.value } })}><option value="allow">Permitir siempre</option><option value="ask">Preguntar antes</option><option value="block">Bloqueado</option></select></div>; })}</div></section>
            <section className="panel"><h2>Límites de ejecución</h2>{!isAdmin ? <p className="muted">Admin role required.</p> : <ConfigForm onSubmit={saveGuardrails} submitLabel="Guardar límites"><label>NÚM. ITERACIONES MÁX.<input type="number" min="1" value={guardrailDraft.max_iterations ?? ""} onChange={(event) => setGuardrailDraft({ ...guardrailDraft, max_iterations: event.target.value ? Number(event.target.value) : undefined })} /></label><label>LLAMADAS A HERRAMIENTAS MÁX.<input type="number" min="1" value={guardrailDraft.max_tool_calls ?? ""} onChange={(event) => setGuardrailDraft({ ...guardrailDraft, max_tool_calls: event.target.value ? Number(event.target.value) : undefined })} /></label><label>DURACIÓN MÁXIMA (SEG.)<input type="number" min="1" value={guardrailDraft.max_duration_seconds ?? ""} onChange={(event) => setGuardrailDraft({ ...guardrailDraft, max_duration_seconds: event.target.value ? Number(event.target.value) : undefined })} /></label><label>REPETICIONES DE UNA ACCIÓN = BUCLE<input type="number" min="2" value={guardrailDraft.loop_repeat_limit ?? ""} onChange={(event) => setGuardrailDraft({ ...guardrailDraft, loop_repeat_limit: event.target.value ? Number(event.target.value) : undefined })} /></label></ConfigForm>}<p className="muted">Al alcanzar un límite la ejecución se detiene y queda explicada en el chat.</p></section></>}

            {settingsSearch.trim() === "" && settingsTab === "agente" && <><section className="panel"><h2>Memoria</h2><div className="swrow"><span className="st"><b>Recuerdos por conversación (1-100)</b><small>Cuánta memoria persistente entra en cada mensaje.</small></span><input type="number" min="1" max="100" value={preferences?.memory_max ?? 30} onChange={(event) => setPreferences((current) => (current ? { ...current, memory_max: Number(event.target.value) || 30 } : current))} onBlur={() => void savePreferences({ memory_max: preferences?.memory_max ?? 30 })} /></div></section>
            <section className="panel"><h2>Tareas en segundo plano</h2>{!isAdmin ? <p className="muted">Admin role required.</p> : <><div className="swrow"><span className="st"><b>Tareas simultáneas (1-4)</b><small>Cuántas tareas puede ejecutar a la vez.</small></span><select value={String(tasksSettings.max_concurrent_tasks)} onChange={(event) => setTasksSettings({ ...tasksSettings, max_concurrent_tasks: Number(event.target.value) })}><option value="1">1</option><option value="2">2</option><option value="3">3</option><option value="4">4</option></select></div><div className="swrow"><span className="st"><b>Recuperar tareas interrumpidas al arrancar</b><small>Se reanudan solas con reintentos acotados.</small></span><label className="switch-row"><input type="checkbox" checked={tasksSettings.auto_resume_tasks} onChange={(event) => setTasksSettings({ ...tasksSettings, auto_resume_tasks: event.target.checked })} /> Activado</label></div><button onClick={() => void saveTasksSettings()}>Guardar</button></>}</section></>}

            {settingsSearch.trim() === "" && settingsTab === "datos" && <><section className="panel"><h2>Hábitos aprendidos</h2><p className="muted">Patrones que ObsyGPT detecta en tus chats (análisis IA y frecuencias de uso) y que tú apruebas, más los que añadas a mano desde Memoria. Los aprobados se inyectan en todas las conversaciones. Nada sale de tu equipo.</p><button className="deny-button" onClick={() => void resetHabits()}>Reiniciar hábitos aprendidos</button></section>
            <section className="panel"><h2>Carpeta de datos</h2><p className="muted">Configuración, memoria, skills y tareas viven en la base de datos y en <code>{workspaceInfo?.default ?? "workspace/"}</code>.</p></section></>}

            {settingsSearch.trim() === "" && settingsTab === "admin" && <>{settingsSection === "agents" && <section className="panel"><h2>Agentes</h2><p className="muted">Cada agente define proveedor, modelo, skills, tools y fallbacks. Despliega uno para editarlo.</p>{!isAdmin && <p className="muted">Admin role required.</p>}{isAdmin && <details className="agent-create-block"><summary>Crear agent</summary><ConfigForm onSubmit={createAgent} submitLabel="Crear agent"><input value={agentDraft.name} onChange={(event) => setAgentDraft({ ...agentDraft, name: event.target.value })} placeholder="Agent name" required /><textarea value={agentDraft.system_prompt} onChange={(event) => setAgentDraft({ ...agentDraft, system_prompt: event.target.value })} placeholder="System prompt" required /><input value={agentDraft.description} onChange={(event) => setAgentDraft({ ...agentDraft, description: event.target.value })} placeholder="Description" /><select value={agentDraft.provider_id} onChange={(event) => setAgentDraft({ ...agentDraft, provider_id: event.target.value })}><option value="">No provider override</option>{metadata.providers.map((provider) => <option value={provider.id} key={provider.id}>{provider.name}</option>)}</select><select value={agentDraft.model_id} onChange={(event) => setAgentDraft({ ...agentDraft, model_id: event.target.value })}><option value="">No model override</option>{metadata.models.map((model) => <option value={model.id} key={model.id}>{model.display_name}</option>)}</select><label><input type="checkbox" checked={agentDraft.internet_enabled} onChange={(event) => setAgentDraft({ ...agentDraft, internet_enabled: event.target.checked })} /> Internet (skills web)</label><label><input type="checkbox" checked={agentDraft.multimodal_enabled} onChange={(event) => setAgentDraft({ ...agentDraft, multimodal_enabled: event.target.checked })} /> Multimodal</label><label><input type="checkbox" checked={agentDraft.agentic_mode} onChange={(event) => setAgentDraft({ ...agentDraft, agentic_mode: event.target.checked })} /> Agentic (tools)</label></ConfigForm></details>}{metadata.agents.map((agent) => { const agentProvider = agent.provider_id ? metadata.providers.find((provider) => provider.id === agent.provider_id) : null; const agentModel = agent.model_id ? metadata.models.find((model) => model.id === agent.model_id) : null; return <details className="agent-block" key={agent.id}><summary><strong>{agent.name}</strong>{agent.agentic_mode && <span className="chip agentic-chip">agentic</span>}<span className="agent-meta">{[agentProvider?.name, agentModel?.display_name ?? agentModel?.model_name].filter(Boolean).join(" · ") || "Sin provider/modelo"}</span>{isAdmin && <input type="checkbox" className="agent-enabled" checked={agent.enabled} title={agent.enabled ? "Activado" : "Desactivado"} onClick={(event) => event.stopPropagation()} onChange={(event) => toggleAgent(agent, event.target.checked)} />}</summary><div className="agent-block-body">{isAdmin && <label className="switch-row"><input type="checkbox" checked={Boolean(agent.agentic_mode)} onChange={(event) => toggleAgentAgentic(agent, event.target.checked)} /> Modo agentic</label>}{isAdmin && (agentEditId === agent.id ? <form className="config-form agent-edit-form" onSubmit={(event) => void saveAgentEdit(agent, event)}><input value={agentEditDraft.name} onChange={(event) => setAgentEditDraft({ ...agentEditDraft, name: event.target.value })} placeholder="Nombre del agente" required /><input value={agentEditDraft.description} onChange={(event) => setAgentEditDraft({ ...agentEditDraft, description: event.target.value })} placeholder="Descripción" /><textarea className="full-width" rows={6} value={agentEditDraft.system_prompt} onChange={(event) => setAgentEditDraft({ ...agentEditDraft, system_prompt: event.target.value })} placeholder="System prompt: personalidad, reglas y estilo de las respuestas" required /><select value={agentEditDraft.provider_id} onChange={(event) => setAgentEditDraft({ ...agentEditDraft, provider_id: event.target.value, model_id: "" })}><option value="">Sin provider</option>{metadata.providers.map((provider) => <option value={provider.id} key={provider.id}>{provider.name}</option>)}</select><select value={agentEditDraft.model_id} onChange={(event) => setAgentEditDraft({ ...agentEditDraft, model_id: event.target.value })}><option value="">Sin modelo</option>{metadata.models.filter((model) => !agentEditDraft.provider_id || model.provider_id === Number(agentEditDraft.provider_id)).map((model) => <option value={model.id} key={model.id}>{model.display_name}</option>)}</select><label>TEMPERATURA<input type="number" step="0.1" min="0" max="2" value={agentEditDraft.temperature} onChange={(event) => setAgentEditDraft({ ...agentEditDraft, temperature: event.target.value })} /></label><label><input type="checkbox" checked={agentEditDraft.internet_enabled} onChange={(event) => setAgentEditDraft({ ...agentEditDraft, internet_enabled: event.target.checked })} /> Internet (skills web)</label><label><input type="checkbox" checked={agentEditDraft.multimodal_enabled} onChange={(event) => setAgentEditDraft({ ...agentEditDraft, multimodal_enabled: event.target.checked })} /> Multimodal</label><div className="skill-actions full-width"><button type="submit">Guardar cambios</button><button type="button" className="text-button" onClick={() => setAgentEditId(null)}>Cancelar</button></div></form> : <div className="skill-actions"><button className="text-button" onClick={() => editAgent(agent)}>Editar nombre, prompt y modelo</button></div>)}<div className="agent-caps"><div><strong>Skills</strong>{metadata.skills.map((skill) => { const checked = metadata.agentSkills.some((assignment) => assignment.agent_id === agent.id && assignment.skill_id === skill.id); return <label key={skill.id}><input type="checkbox" checked={checked} disabled={!isAdmin} onChange={(event) => toggleAgentSkill(agent.id, skill.id, event.target.checked)} /> {skill.name}</label>; })}</div><div><strong>MCPs</strong>{metadata.mcpServers.length === 0 ? <span className="muted">No MCP servers registered.</span> : metadata.mcpServers.map((server) => { const checked = metadata.agentMcps.some((assignment) => assignment.agent_id === agent.id && assignment.mcp_server_id === server.id); return <label key={server.id}><input type="checkbox" checked={checked} disabled={!isAdmin} onChange={(event) => toggleAgentMcp(agent.id, server.id, event.target.checked)} /> {server.name}</label>; })}</div><div><strong>Tools</strong>{toolDefinitions.length === 0 ? <span className="muted">No tools registered.</span> : toolDefinitions.map((tool) => { const toolChecked = agentTools.some((assignment) => assignment.agent_id === agent.id && assignment.tool_name === tool.name && assignment.allowed); return <label key={tool.name}><input type="checkbox" checked={toolChecked} disabled={!isAdmin || !agent.agentic_mode} onChange={(event) => toggleAgentTool(agent.id, tool.name, event.target.checked)} /> {tool.name} ({tool.permission})</label>; })}</div></div><div className="detect-block"><strong>Fallbacks</strong>{agentFallbacks.filter((item) => item.agent_id === agent.id).length === 0 ? <span className="muted">Sin cadena de fallback.</span> : <div className="chip-row">{agentFallbacks.filter((item) => item.agent_id === agent.id).sort((a, b) => a.priority - b.priority).map((fallback) => <span className="chip" key={`${fallback.provider_id}-${fallback.model_id}`}>{fallback.model_display_name} <button type="button" className="text-button danger" disabled={!isAdmin} onClick={() => removeAgentFallback(agent.id, fallback)}>x</button></span>)}</div>}{isAdmin && <span className="fallback-add"><select value={fallbackDraft[agent.id]?.provider_id ?? ""} onChange={(event) => setFallbackDraft((current) => ({ ...current, [agent.id]: { provider_id: event.target.value, model_id: "" } }))}><option value="">Provider</option>{metadata.providers.filter((provider) => provider.enabled).map((provider) => <option value={provider.id} key={provider.id}>{provider.name}</option>)}</select><select value={fallbackDraft[agent.id]?.model_id ?? ""} onChange={(event) => setFallbackDraft((current) => ({ ...current, [agent.id]: { ...current[agent.id], model_id: event.target.value } }))}><option value="">Model</option>{metadata.models.filter((model) => model.enabled && model.provider_id === Number(fallbackDraft[agent.id]?.provider_id)).map((model) => <option value={model.id} key={model.id}>{model.display_name}</option>)}</select><button type="button" className="text-button" disabled={!fallbackDraft[agent.id]?.provider_id || !fallbackDraft[agent.id]?.model_id} onClick={() => addAgentFallback(agent.id)}>Añadir</button></span>}</div></div></details>; })}</section>}


                        {settingsSection === "models" && <section className="panel"><h2>Models</h2>{isAdmin && <ConfigForm onSubmit={createModel} submitLabel="Añadir model"><select value={modelDraft.provider_id} onChange={(event) => setModelDraft({ ...modelDraft, provider_id: event.target.value })} required><option value="">Provider</option>{metadata.providers.map((provider) => <option value={provider.id} key={provider.id}>{provider.name}</option>)}</select><input value={modelDraft.model_name} onChange={(event) => setModelDraft({ ...modelDraft, model_name: event.target.value })} placeholder="Model ID" required /><input value={modelDraft.display_name} onChange={(event) => setModelDraft({ ...modelDraft, display_name: event.target.value })} placeholder="Display name" required /><input value={modelDraft.context_window} onChange={(event) => setModelDraft({ ...modelDraft, context_window: event.target.value })} placeholder="Context window" type="number" min="1" /><label><input type="checkbox" checked={modelDraft.supports_vision} onChange={(event) => setModelDraft({ ...modelDraft, supports_vision: event.target.checked })} /> Vision</label><label><input type="checkbox" checked={modelDraft.supports_audio} onChange={(event) => setModelDraft({ ...modelDraft, supports_audio: event.target.checked })} /> Audio</label><label><input type="checkbox" checked={modelDraft.supports_tools} onChange={(event) => setModelDraft({ ...modelDraft, supports_tools: event.target.checked })} /> Tools</label><label><input type="checkbox" checked={modelDraft.supports_json} onChange={(event) => setModelDraft({ ...modelDraft, supports_json: event.target.checked })} /> JSON</label><label><input type="checkbox" checked={modelDraft.enabled} onChange={(event) => setModelDraft({ ...modelDraft, enabled: event.target.checked })} /> Enabled</label></ConfigForm>}{metadata.models.map((model) => <span className="attachment-row muted" key={model.id}><span>{model.display_name}</span>{isAdmin && <button className="text-button" type="button" onClick={() => checkModel(model)}>Check</button>}{isAdmin && <button className="text-button danger" type="button" onClick={() => deleteModel(model)}>Borrar</button>}{isAdmin && <input type="checkbox" checked={model.enabled} onChange={(event) => toggleModel(model, event.target.checked)} />}</span>)}{modelCheckResult && <ModelCheckResult result={modelCheckResult} />}</section>}

            {settingsSection === "workflows" && <section className="panel"><h2>Workflows</h2>{isAdmin && <ConfigForm onSubmit={createWorkflow} submitLabel="Crear workflow"><input value={workflowDraft.name} onChange={(event) => setWorkflowDraft({ ...workflowDraft, name: event.target.value })} placeholder="Workflow name" required /><select value={workflowDraft.workflow_type} onChange={(event) => setWorkflowDraft({ ...workflowDraft, workflow_type: event.target.value })}><option value="single_agent">Single agent</option><option value="sequential">Sequential</option><option value="reviewer">Reviewer</option><option value="supervisor">Supervisor</option><option value="parallel">Parallel</option><option value="debate">Debate</option></select><select multiple value={workflowDraft.agent_ids.map(String)} onChange={(event) => setWorkflowDraft({ ...workflowDraft, agent_ids: Array.from(event.currentTarget.selectedOptions).map((option) => Number(option.value)) })}>{metadata.agents.map((agent) => <option value={agent.id} key={agent.id}>{agent.name}</option>)}</select></ConfigForm>}{metadata.workflows.map((workflow) => <label className="attachment-row" key={workflow.id}><span>{workflow.name} ({workflow.workflow_type})</span>{isAdmin && <input type="checkbox" checked={workflow.enabled} onChange={(event) => toggleWorkflow(workflow, event.target.checked)} />}</label>)}</section>}


            {settingsSection === "mcps" && <section className="panel"><h2>MCPs</h2>{isAdmin && <ConfigForm onSubmit={createMcpServer} submitLabel="Registrar MCP"><input value={mcpDraft.name} onChange={(event) => setMcpDraft({ ...mcpDraft, name: event.target.value })} placeholder="MCP name" required /><input value={mcpDraft.description} onChange={(event) => setMcpDraft({ ...mcpDraft, description: event.target.value })} placeholder="Description" /><select value={mcpDraft.connection_type} onChange={(event) => setMcpDraft({ ...mcpDraft, connection_type: event.target.value })}><option value="command">Command</option><option value="url">URL</option></select>{mcpDraft.connection_type === "command" ? <input value={mcpDraft.command} onChange={(event) => setMcpDraft({ ...mcpDraft, command: event.target.value })} placeholder="Command" required /> : <input value={mcpDraft.url} onChange={(event) => setMcpDraft({ ...mcpDraft, url: event.target.value })} placeholder="URL" required />}<label><input type="checkbox" checked={mcpDraft.enabled} onChange={(event) => setMcpDraft({ ...mcpDraft, enabled: event.target.checked })} /> Enabled</label><button type="button" onClick={validateMcpServer}>Validate MCP</button></ConfigForm>}{mcpValidation && <pre className="skill-result">{mcpValidation}</pre>}{isAdmin && <ConfigForm onSubmit={runMcpServer} submitLabel="Run MCP method"><select value={mcpRunDraft.server_id} onChange={(event) => setMcpRunDraft({ ...mcpRunDraft, server_id: event.target.value })} required><option value="">Select enabled MCP</option>{metadata.mcpServers.filter((server) => server.enabled).map((server) => <option value={server.id} key={server.id}>{server.name}</option>)}</select><input value={mcpRunDraft.method} onChange={(event) => setMcpRunDraft({ ...mcpRunDraft, method: event.target.value })} placeholder="tools/list" required /><textarea value={mcpRunDraft.params} onChange={(event) => setMcpRunDraft({ ...mcpRunDraft, params: event.target.value })} placeholder='{"name":"tool"}' /></ConfigForm>}{mcpRunResult && <pre className="skill-result">{mcpRunResult}</pre>}{metadata.mcpServers.length ? metadata.mcpServers.map((server) => <div className="provider-row-block" key={server.id}><label className="attachment-row"><span>{server.name} ({server.connection_type})</span>{isAdmin && <button type="button" className="text-button" disabled={inspectingMcp !== null} onClick={() => inspectMcpServer(server)}>{inspectingMcp === server.id ? "Inspeccionando..." : "Inspeccionar"}</button>}{isAdmin && <button type="button" className="text-button danger" onClick={() => deleteMcpServer(server)}>Borrar</button>}{isAdmin && <input type="checkbox" checked={server.enabled} onChange={(event) => toggleMcpServer(server, event.target.checked)} />}</label>{mcpInspection?.serverId === server.id && <div className="detect-results">{mcpInspection.tools.length === 0 ? <span className="chip muted-chip">sin tools descubiertas</span> : mcpInspection.tools.slice(0, 12).map((tool) => <span className="chip" key={tool.name} title={tool.description ?? ""}>{tool.name}</span>)}</div>}</div>) : <p className="muted">No MCP servers registered.</p>}</section>}

{settingsSection === "plugins" && <section className="panel"><h2>Plugins</h2><p className="muted">Packs que agrupan skills, MCPs y sub-agentes. Catalogo local en plugins/ del repo o marketplaces git (https publico).</p>{pluginMessage && <p className="muted">{pluginMessage}</p>}{isAdmin && <ConfigForm onSubmit={addPluginMarketplace} submitLabel="Añadir marketplace"><input value={marketplaceDraft} onChange={(event) => setMarketplaceDraft(event.target.value)} placeholder="https://github.com/owner/plugins-repo" required /></ConfigForm>}{pluginMarketplaces.length > 0 && <div>{pluginMarketplaces.map((marketplace) => <div className="attachment-row" key={marketplace.name}><span>{marketplace.name} · {marketplace.url}</span><button type="button" className="text-button" disabled={pluginBusy === "market:" + marketplace.name} onClick={() => void refreshPluginMarketplace(marketplace.name)}>Actualizar</button><button type="button" className="text-button danger" disabled={pluginBusy === "market:" + marketplace.name} onClick={() => void removePluginMarketplace(marketplace.name)}>Eliminar</button></div>)}</div>}{pluginCatalog.length === 0 ? <p className="muted">No hay plugins en el catalogo.</p> : <div className="skill-grid">{pluginCatalog.map((entry) => <article className="skill-card" key={entry.slug + ":" + entry.source}><div className="skill-card-head"><div><strong>{entry.name}</strong><span>v{entry.version} · {entry.source === "local" ? "local" : "marketplace"}</span></div></div><p>{entry.description}</p><div className="chip-row"><span className="chip">skills: {entry.components.skills}</span><span className="chip">mcps: {entry.components.mcps}</span><span className="chip">agents: {entry.components.agents}</span>{entry.connectors.map((connector) => <span className={missingConnectorsFor(entry).includes(connector) ? "chip muted-chip" : "chip"} key={connector}>{connector}{missingConnectorsFor(entry).includes(connector) ? " · sin conectar" : ""}</span>)}</div>{entry.installed && missingConnectorsFor(entry).length > 0 && <p className="muted">Conectores requeridos sin cuenta: {missingConnectorsFor(entry).join(", ")} (vista Conectores).</p>}{isAdmin && <div className="skill-actions">{entry.installed ? <button className="text-button danger" disabled={pluginBusy === entry.slug} onClick={() => void uninstallPluginEntry(entry)}>{pluginBusy === entry.slug ? "..." : "Desinstalar"}</button> : <button className="text-button" disabled={pluginBusy === entry.slug} onClick={() => void installPluginEntry(entry)}>{pluginBusy === entry.slug ? "Instalando..." : "Instalar"}</button>}</div>}</article>)}</div>}</section>}

            {settingsSection === "users" && <section className="panel"><h2>Users</h2>{!isAdmin ? <p className="muted">Admin role required.</p> : metadata.users.length === 0 ? <p className="muted">No users found.</p> : metadata.users.map((user) => <label className="attachment-row" key={user.id}><span>{user.username} ({user.email})</span><select value={user.role} onChange={(event) => updateUserRole(user.id, event.target.value as "admin" | "user") }><option value="user">User</option><option value="admin">Admin</option></select></label>)}</section>}
            {settingsSection === "audit" && <section className="panel"><h2>Audit Logs</h2><div className="audit-filters"><input value={auditFilters.action} onChange={(event) => setAuditFilters({ ...auditFilters, action: event.target.value })} placeholder="Filter action" /><select value={auditFilters.target_type} onChange={(event) => setAuditFilters({ ...auditFilters, target_type: event.target.value })}><option value="">All targets</option><option value="user">user</option><option value="provider">provider</option><option value="model">model</option><option value="agent">agent</option><option value="workflow">workflow</option><option value="mcp_server">mcp_server</option><option value="skill">skill</option></select><button className="text-button" onClick={() => void refreshWorkspace()}>Apply</button></div>{auditLogs.length === 0 ? <p className="muted">No audit events yet.</p> : <>{auditLogs.slice(0, auditLogLimit).map((log) => <div className="tool-call" key={log.id}><div className="audit-row-head"><strong>{log.action}</strong><span>{formatDateTime(log.created_at)}</span></div><span>{log.actor_username ?? "system"} {"->"} {log.target_type} #{log.target_id ?? "n/a"}</span><small>{formatAuditMetadata(log.metadata)}</small></div>)}{auditLogLimit < auditLogs.length && <button className="text-button" onClick={() => setAuditLogLimit((limit) => Math.min(limit + 8, auditLogs.length))}>Show more audit logs</button>}</>}</section>}
            </>}
          </div>
        </section>}

        {activeView === "skills" && <section className="skills-workspace">
          <div className="subtabs">
          <button className={skillTab === "library" ? "active" : ""} onClick={() => setSkillTab("library")}>Biblioteca</button>
          <button className={skillTab === "editor" ? "active" : ""} onClick={() => setSkillTab("editor")}>{editingSkillId ? "Editar" : "Crear"}</button>
          <button className={skillTab === "generator" ? "active" : ""} onClick={() => setSkillTab("generator")}>Generador IA</button>
          </div>

          {skillTab === "library" && <section className="panel skills-panel"><div className="section-toolbar"><div><h2>Biblioteca Agent Skills</h2><p className="muted">Cada skill representa una carpeta <code>agents/skills/nombre/</code> con un <code>SKILL.md</code> estándar. Invocación manual: <code>/nombre_skill describe la tarea</code>.</p></div><input value={skillSearch} onChange={(event) => setSkillSearch(event.target.value)} placeholder="Buscar skill..." /></div>{filteredSkills.length === 0 ? <p className="muted">No hay skills que coincidan.</p> : <div className="skill-grid">{filteredSkills.map((skill) => { const assignedAgents = skillAgents(skill.id); return <article className="skill-card" key={skill.id}><div className="skill-card-head"><div><strong>{skill.name}</strong><span>{skill.enabled ? "Activa" : "Desactivada"} · agents/skills/{skill.name}/SKILL.md</span></div>{isAdmin && <label className="switch-row"><input type="checkbox" checked={skill.enabled} onChange={(event) => toggleSkill(skill, event.target.checked)} /> Enabled</label>}</div><p>{skill.description || "Sin descripción."}</p><div className="chip-row"><span className="chip">/{skill.name}</span><span className="chip">triggers: {skill.triggers.join(", ")}</span>{skill.argument_hint && <span className="chip">args: {skill.argument_hint}</span>}{assignedAgents.length ? assignedAgents.map((agent) => <span className="chip" key={agent.id}>{agent.name}</span>) : <span className="chip muted-chip">Sin agentes</span>}</div><details className="card-details"><summary>SKILL.md</summary><pre className="skill-md-preview">{skill.skill_md}</pre></details>{isAdmin && <div className="skill-actions"><button className="text-button" onClick={() => editSkill(skill)}>Editar SKILL.md</button><button className="text-button danger" onClick={() => deleteSkill(skill)}>Borrar</button></div>}<details className="agent-toggle-list card-details"><summary>Asignación ({assignedAgents.length})</summary>{metadata.agents.map((agent) => { const checked = metadata.agentSkills.some((assignment) => assignment.agent_id === agent.id && assignment.skill_id === skill.id); return <label key={agent.id}><input type="checkbox" checked={checked} disabled={!isAdmin} onChange={(event) => toggleAgentSkill(agent.id, skill.id, event.target.checked)} />{agent.name}</label>; })}</details></article>; })}</div>}</section>}

          {skillTab === "editor" && <section className="panel skills-panel"><div className="section-toolbar"><div><h2>{editingSkillId ? "Editar SKILL.md" : "Crear Agent Skill"}</h2><p className="muted">Edita frontmatter YAML y cuerpo Markdown. ObsyGPT guarda la versión estructurada y genera la preview canónica.</p></div>{editingSkillId && <button className="text-button" onClick={resetSkillEditor}>Nueva skill</button>}</div>{!isAdmin ? <p className="muted">Admin role required.</p> : <ConfigForm onSubmit={createSkill} submitLabel={editingSkillId ? "Guardar SKILL.md" : "Crear skill"}><input value={skillDraft.name} onChange={(event) => setSkillDraft({ ...skillDraft, name: event.target.value })} placeholder="name: invoice-risk" required /><input value={skillDraft.description} onChange={(event) => setSkillDraft({ ...skillDraft, description: event.target.value })} placeholder="description: qué hace y cuándo se activa" /><input value={skillDraft.argument_hint} onChange={(event) => setSkillDraft({ ...skillDraft, argument_hint: event.target.value })} placeholder="argument-hint: texto, URL, CSV..." /><label><input type="checkbox" checked={skillDraft.triggers.includes("user")} onChange={(event) => setSkillDraft({ ...skillDraft, triggers: event.target.checked ? Array.from(new Set([...skillDraft.triggers, "user"])) : skillDraft.triggers.filter((trigger) => trigger !== "user") as Array<"user" | "model"> })} /> trigger user</label><label><input type="checkbox" checked={skillDraft.triggers.includes("model")} onChange={(event) => setSkillDraft({ ...skillDraft, triggers: event.target.checked ? Array.from(new Set([...skillDraft.triggers, "model"])) : skillDraft.triggers.filter((trigger) => trigger !== "model") as Array<"user" | "model"> })} /> trigger model</label><textarea value={skillDraft.body} onChange={(event) => setSkillDraft({ ...skillDraft, body: event.target.value })} placeholder="# Instrucciones principales" /><textarea value={skillDraft.resources} onChange={(event) => setSkillDraft({ ...skillDraft, resources: event.target.value })} placeholder="Recursos opcionales: scripts/, templates/, examples/" /><label><input type="checkbox" checked={skillDraft.enabled} onChange={(event) => setSkillDraft({ ...skillDraft, enabled: event.target.checked })} /> Enabled</label></ConfigForm>}</section>}

          {skillTab === "generator" && <section className="panel skills-panel"><h2>Creador de Agent Skill</h2><p className="muted">Describe la capacidad. ObsyGPT genera frontmatter y cuerpo Markdown para un <code>SKILL.md</code> revisable antes de guardar.</p>{!isAdmin ? <p className="muted">Admin role required.</p> : <ConfigForm onSubmit={generateSkillDraft} submitLabel="Generar SKILL.md"><textarea value={skillGeneratorPrompt} onChange={(event) => setSkillGeneratorPrompt(event.target.value)} placeholder="Ejemplo: una skill para leer facturas, detectar riesgos y devolver una tabla de incidencias" required /></ConfigForm>}{generatedSkill && <div className="generated-skill"><h3>agents/skills/{generatedSkill.name}/SKILL.md</h3><p>{generatedSkill.description}</p><pre>{`---\nname: ${generatedSkill.name}\ndescription: ${generatedSkill.description}\nargument-hint: ${generatedSkill.argument_hint}\ntriggers: [${generatedSkill.triggers.map((trigger) => `"${trigger}"`).join(", ")}]\n---\n\n${generatedSkill.body}\n\n## Recursos opcionales\n${generatedSkill.resources}`}</pre><div className="chip-row">{generatedSkill.checklist.map((item) => <span className="chip" key={item}>{item}</span>)}</div>{isAdmin && <button onClick={useGeneratedSkill}>Usar este borrador</button>}</div>}<ConfigForm onSubmit={runReadUrl} submitLabel="Probar Read URL"><input value={internetUrl} onChange={(event) => setInternetUrl(event.target.value)} placeholder="https://example.com" required /></ConfigForm>{skillResult && <pre className="skill-result">{skillResult}</pre>}</section>}
        </section>}

        {activeView === "monitoring" && isAdmin && <section className="panel full-panel">
          <h2>Monitoring</h2>
          <div className="audit-filters">
            {[7, 14, 30].map((days) => <button key={days} className={metricsDays === days ? "active" : ""} onClick={() => { setMetricsDays(days); void loadMetrics(days); }}>{days} días</button>)}
          </div>
          {!metrics ? <p className="muted">Cargando métricas...</p> : <>
            <div className="metrics-summary">
              <div className="metric-card"><strong>{metrics.summary.runs}</strong><span>runs</span></div>
              <div className="metric-card"><strong>{metrics.summary.completed}</strong><span>completados</span></div>
              <div className="metric-card"><strong>{metrics.summary.failed}</strong><span>fallidos</span></div>
              <div className="metric-card"><strong>{metrics.summary.avg_duration_seconds.toFixed(1)}s</strong><span>duración media</span></div>
              <div className="metric-card"><strong>{metrics.summary.active_users}</strong><span>usuarios activos</span></div>
              <div className="metric-card"><strong>{metrics.provider_fallbacks}</strong><span>fallbacks de proveedor</span></div>
            </div>
            <h3>Runs por día</h3>
            <MetricsBarChart rows={metrics.runs_per_day.map((row) => ({ label: row.day, segments: [
              { value: row.completed, color: "#7aa860", label: "completados" },
              { value: row.failed, color: "#c96a5f", label: "fallidos" },
              { value: row.other, color: "#d5b06d", label: "otros" }
            ] }))} />
            <h3>Llamadas a herramientas por día</h3>
            <MetricsBarChart rows={metrics.tool_calls_per_day.map((row) => ({ label: row.day, segments: [
              { value: row.total - row.failed, color: "#7fbfb4", label: "ok" },
              { value: row.failed, color: "#c96a5f", label: "fallidas" }
            ] }))} />
            <h3>Top herramientas</h3>
            <div className="chip-row">{Object.entries(metrics.tool_categories).map(([category, calls]) => <span className="chip" key={category}>{category}: {calls}</span>)}</div>
            <table className="metrics-table"><thead><tr><th>Tool</th><th>Llamadas</th><th>Fallidas</th></tr></thead><tbody>{metrics.top_tools.map((tool) => <tr key={tool.name}><td>{tool.name}</td><td>{tool.calls}</td><td>{tool.failed}</td></tr>)}</tbody></table>
            <h3>Actividad por agente</h3>
            <table className="metrics-table"><thead><tr><th>Agente</th><th>Runs</th><th>Fallidos</th></tr></thead><tbody>{metrics.agent_activity.map((row) => <tr key={row.agent}><td>{row.agent}</td><td>{row.runs}</td><td>{row.failed}</td></tr>)}</tbody></table>
            {metrics.mcp_calls.length > 0 && <>
              <h3>Llamadas MCP</h3>
              <table className="metrics-table"><thead><tr><th>Método/Tool</th><th>Llamadas</th><th>Fallidas</th></tr></thead><tbody>{metrics.mcp_calls.map((row) => <tr key={row.name}><td>{row.name}</td><td>{row.calls}</td><td>{row.failed}</td></tr>)}</tbody></table>
            </>}
            <p className="muted">Export OTLP opcional: configura OTEL_EXPORTER_OTLP_ENDPOINT en backend/.env (eventos user_prompt, assistant_response, tool_result, api_error; contenido redactado por defecto con OTEL_CONTENT_CAPTURE).</p>
          </>}
        </section>}

        {activeView === "diagnostics" && isAdmin && <section className="panel full-panel"><h2>Diagnostics</h2>{diagnostics ? <><p>Users: {diagnostics.counts.users} | Agents: {diagnostics.counts.agents} | Workflows: {diagnostics.counts.workflows} | MCPs: {diagnostics.counts.mcp_servers}</p>{diagnostics.providers.map((provider) => <p className="muted" key={provider.id}>{provider.name}: {provider.ready ? "ready" : "not ready"} ({provider.configured_models} model(s), key {provider.api_key_configured ? "set" : "missing"})</p>)}</> : <p className="muted">No diagnostics loaded.</p>}</section>}
      </section>

      {rightSidebarOpen && <aside className="right-rail">
        <button className="drawer-close" onClick={() => setRightSidebarOpen(false)}>Cerrar</button>
        <section className="panel"><h2>Consumo</h2><p className="metric">{approximateTokens.toLocaleString()} tokens</p><p className="muted">Estimado por conversación activa.</p>{runs[0] && <p className="run-status">Run #{runs[0].id}: {runs[0].status}</p>}</section>
        <section className="panel"><h2>Agent activo</h2><p>{selectedAgent?.name ?? "Default agent"}</p><p className="muted">Workflow: {selectedWorkflow?.name ?? "Sin override"}</p></section>
        <section className="panel"><h2>Skills activas</h2>{activeSkills.length ? activeSkills.map((skill) => <p key={skill.id}>{skill.name}</p>) : <p className="muted">Ninguna skill asignada.</p>}</section>
        <section className="panel"><h2>MCPs activos</h2>{activeMcps.length ? activeMcps.map((server) => <p key={server.id}>{server.name} ({server.connection_type})</p>) : <p className="muted">Ningún MCP asignado.</p>}</section>
        <section className="panel trace-panel"><h2>Tools</h2>{toolCalls.length === 0 ? <p className="muted">Sin tool calls.</p> : toolCalls.slice(0, 6).map((toolCall) => <div className="tool-call" key={toolCall.id}><strong>{toolCall.skill_name}</strong><span>{toolCall.status}: {toolCall.input_summary}</span></div>)}</section>
        <section className="panel"><h2>Files</h2>{attachments.length === 0 ? <p className="muted">Sin adjuntos.</p> : attachments.map((attachment) => <div className="attachment-row" key={attachment.id}>
          <label className="attachment-check" title="Incluir en el próximo mensaje"><input type="checkbox" checked={selectedAttachmentIds.includes(attachment.id)} onChange={(event) => setSelectedAttachmentIds((current) => event.target.checked ? [...current, attachment.id] : current.filter((id) => id !== attachment.id))} /><span>{attachment.file_name}</span></label>
          <span className="muted">{Math.max(1, Math.round(attachment.size_bytes / 1024))} KB</span>
          <button className="text-button danger" title="Borrar adjunto para siempre" onClick={() => void deleteAttachment(attachment)}>Borrar</button>
        </div>)}
        {attachments.length > 0 && <p className="muted">Los adjuntos que marques se añaden al contexto del próximo mensaje. Borrar un adjunto elimina el archivo y su texto extraído; no afecta a los chats que ya lo usaron.</p>}</section>
      </aside>}

    </main>
  );
}

function ConfigForm({ children, onSubmit, submitLabel }: { children: ReactNode; onSubmit: (event: FormEvent) => void; submitLabel: string }) {
  return (
    <form className="config-form" onSubmit={onSubmit}>
      {children}
      <button type="submit">{submitLabel}</button>
    </form>
  );
}

const INLINE_PATTERN = /(\*\*[^*]+\*\*|\*[^*\s][^*]*\*|`[^`]+`|\[[^\]]+\]\((https?:\/\/[^)\s]+)\))/g;

function renderInline(text: string, keyPrefix: string): ReactNode[] {
  const nodes: ReactNode[] = [];
  const pattern = new RegExp(INLINE_PATTERN.source, "g");
  let lastIndex = 0;
  let key = 0;
  let match: RegExpExecArray | null;
  while ((match = pattern.exec(text)) !== null) {
    if (match.index > lastIndex) nodes.push(text.slice(lastIndex, match.index));
    const token = match[0];
    const id = `${keyPrefix}-${key++}`;
    if (token.startsWith("**")) nodes.push(<strong key={id}>{token.slice(2, -2)}</strong>);
    else if (token.startsWith("`")) nodes.push(<code key={id} className="md-inline-code">{token.slice(1, -1)}</code>);
    else if (token.startsWith("[")) nodes.push(<a key={id} href={match[2]} target="_blank" rel="noreferrer">{token.slice(1, token.indexOf("]"))}</a>);
    else nodes.push(<em key={id}>{token.slice(1, -1)}</em>);
    lastIndex = pattern.lastIndex;
  }
  if (lastIndex < text.length) nodes.push(text.slice(lastIndex));
  return nodes;
}

function renderBlocks(text: string, keyPrefix: string): ReactNode[] {
  const lines = text.split("\n");
  const blocks: ReactNode[] = [];
  let i = 0;
  let key = 0;
  while (i < lines.length) {
    const line = lines[i];
    if (!line.trim()) { i++; continue; }
    const id = `${keyPrefix}-b${key++}`;

    const heading = line.match(/^(#{1,4})\s+(.*)$/);
    if (heading) {
      const content = renderInline(heading[2], id);
      if (heading[1].length === 1) blocks.push(<h3 key={id}>{content}</h3>);
      else if (heading[1].length === 2) blocks.push(<h4 key={id}>{content}</h4>);
      else blocks.push(<h5 key={id}>{content}</h5>);
      i++; continue;
    }

    if (/^\s*(-{3,}|\*{3,})\s*$/.test(line)) { blocks.push(<hr key={id} />); i++; continue; }

    if (/^\s*[-*+]\s+/.test(line)) {
      const items: string[] = [];
      while (i < lines.length && /^\s*[-*+]\s+/.test(lines[i])) { items.push(lines[i].replace(/^\s*[-*+]\s+/, "")); i++; }
      blocks.push(<ul key={id}>{items.map((item, n) => <li key={n}>{renderInline(item, `${id}-${n}`)}</li>)}</ul>);
      continue;
    }

    if (/^\s*\d+[.)]\s+/.test(line)) {
      const items: string[] = [];
      while (i < lines.length && /^\s*\d+[.)]\s+/.test(lines[i])) { items.push(lines[i].replace(/^\s*\d+[.)]\s+/, "")); i++; }
      blocks.push(<ol key={id}>{items.map((item, n) => <li key={n}>{renderInline(item, `${id}-${n}`)}</li>)}</ol>);
      continue;
    }

    if (line.trim().startsWith("|") && i + 1 < lines.length && /^\s*\|?[\s:|-]+\|?\s*$/.test(lines[i + 1]) && lines[i + 1].includes("-")) {
      const parseRow = (row: string) => row.trim().replace(/^\|/, "").replace(/\|$/, "").split("|").map((cell) => cell.trim());
      const header = parseRow(lines[i]);
      i += 2;
      const rows: string[][] = [];
      while (i < lines.length && lines[i].trim().startsWith("|")) { rows.push(parseRow(lines[i])); i++; }
      blocks.push(
        <div className="md-table-wrap" key={id}>
          <table>
            <thead><tr>{header.map((cell, n) => <th key={n}>{renderInline(cell, `${id}-th${n}`)}</th>)}</tr></thead>
            <tbody>{rows.map((row, r) => <tr key={r}>{row.map((cell, n) => <td key={n}>{renderInline(cell, `${id}-td${r}-${n}`)}</td>)}</tr>)}</tbody>
          </table>
        </div>
      );
      continue;
    }

    const paragraph: string[] = [];
    while (i < lines.length && lines[i].trim()) { paragraph.push(lines[i]); i++; }
    blocks.push(<p key={id}>{renderInline(paragraph.join(" "), id)}</p>);
  }
  return blocks;
}

function renderMarkdown(text: string): ReactNode {
  const segments = text.split("```");
  return segments.map((segment, index) => {
    const id = `seg${index}`;
    if (index % 2 === 1) {
      const firstBreak = segment.indexOf("\n");
      const looksLikeLanguageTag = firstBreak > 0 && firstBreak < 24 && !segment.slice(0, firstBreak).includes(" ");
      const code = looksLikeLanguageTag ? segment.slice(firstBreak + 1) : segment;
      return <pre className="md-code" key={id}><code>{code.replace(/\n$/, "")}</code></pre>;
    }
    return <div className="md-text" key={id}>{renderBlocks(segment, id)}</div>;
  });
}

function HealthLine({ health }: { health: HealthResponse | null }) {
  if (!health) return <p className="muted">Checking backend...</p>;
  const database = health.database ? `, DB ${health.database}` : "";
  return <p className="muted">Backend {health.status}{database}</p>;
}

function ModelCheckResult({ result }: { result: ModelCheckResponse }) {
  let summary = "Ready";
  if (!result.enabled) summary = "Model disabled";
  else if (!result.provider_enabled) summary = "Provider disabled";
  else if (!result.api_key_configured) summary = `Missing API key: ${result.api_key_env ?? "provider key"}`;
  else if (!result.ready) summary = "Not ready";

  return (
    <div className="skill-result">
      <strong>{summary}</strong>
      <pre>{JSON.stringify(result, null, 2)}</pre>
    </div>
  );
}


function MetricsBarChart({ rows }: { rows: Array<{ label: string; segments: Array<{ value: number; color: string; label: string }> }> }) {
  if (rows.length === 0) return <p className="muted">Sin datos en este periodo.</p>;
  const max = Math.max(1, ...rows.map((row) => row.segments.reduce((sum, segment) => sum + segment.value, 0)));
  const chartWidth = 560;
  const chartHeight = 110;
  const barSpace = chartWidth / rows.length;
  const barWidth = Math.max(6, barSpace * 0.6);
  return (
    <svg className="metrics-chart" viewBox={`0 0 ${chartWidth} ${chartHeight + 22}`} role="img" aria-label="Grafico de barras por dia">
      {rows.map((row, index) => {
        let cursor = chartHeight;
        return (
          <g key={row.label}>
            {row.segments.map((segment, segmentIndex) => {
              const height = (segment.value / max) * chartHeight;
              cursor -= height;
              return <rect key={segmentIndex} x={index * barSpace + (barSpace - barWidth) / 2} y={cursor} width={barWidth} height={height} fill={segment.color}><title>{`${row.label} ${segment.label}: ${segment.value}`}</title></rect>;
            })}
            <text x={index * barSpace + barSpace / 2} y={chartHeight + 16} textAnchor="middle" fontSize="9" fill="currentColor">{row.label.slice(5)}</text>
          </g>
        );
      })}
    </svg>
  );
}
