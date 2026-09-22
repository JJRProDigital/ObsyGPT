import { FormEvent, KeyboardEvent as ReactKeyboardEvent, useCallback, useEffect, useRef, useState } from "react";
import { useLocation, useNavigate } from "react-router-dom";
import { useQuery, useQueryClient } from "@tanstack/react-query";
import { apiRequest, streamApprovalResume, streamMessage, uploadAttachment, UNAUTHORIZED_EVENT, type ActivityEvent } from "./api";
import { emptyMetadata } from "./types";
import type {
  AdminSection, Agent, AgentEvent, AgentFallback, AgentMcp, AgentRun, AgentSkill, AgentTool, AppView, Attachment,
  AuditLog, CatalogConnector, ChatFolder, Conversation, DetectedModel, DiagnosticsResponse, GuardrailSettings,
  HabitSuggestion, HealthResponse, McpServer, MemoryItem, Message, MetricsResponse, Model, ModelCheckResponse,
  PendingApproval, PluginCatalogEntry, PluginMarketplace, Preferences, Project, ProjectDetail, ProjectFilesResponse,
  ProjectTab, Provider, ProviderDefinition, SessionResponse, SettingsSection, SettingsTab, Skill, SkillDraftResponse,
  SkillTab, Source, Task, TaskApproval, TaskEvent, TasksSettings, ToolCall, ToolDefinition, User, Workflow, WorkflowStep,
  WorkspaceInfo
} from "./types";
import type { AdminUser } from "./types";
import { LiveActivityBar, MessageItem } from "./components/chat";
import type { LiveActivityState } from "./components/chat";
import { ConfigForm, HealthLine, MetricsBarChart, ModelCheckResult } from "./components/shared";
import { AuthScreen } from "./views/AuthScreen";
import { LeftRail } from "./views/LeftRail";
import { ChatView } from "./views/ChatView";
import { TasksView } from "./views/TasksView";
import { ProjectsView } from "./views/ProjectsView";
import { MemoryView } from "./views/MemoryView";
import { ToolsView } from "./views/ToolsView";
import { ConnectorsView } from "./views/ConnectorsView";
import { HistoryView } from "./views/HistoryView";
import { TraceView } from "./views/TraceView";
import { SettingsView } from "./views/SettingsView";
import { SkillsView } from "./views/SkillsView";
import { MonitoringView } from "./views/MonitoringView";
import { DiagnosticsView } from "./views/DiagnosticsView";
import { RightRail } from "./views/RightRail";
import { AppStateContext, type AppState } from "./state/context";

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
  const [resumingApprovalId, setResumingApprovalId] = useState<number | null>(null);
  const [detectedModels, setDetectedModels] = useState<Record<number, DetectedModel[]>>({});
  const [detectingProvider, setDetectingProvider] = useState<number | null>(null);
  const [fallbackDraft, setFallbackDraft] = useState<Record<number, { provider_id: string; model_id: string }>>({});
  const [chatMode, setChatMode] = useState<"act" | "plan" | "think">("act");
  const [paletteIndex, setPaletteIndex] = useState(0);
  const routerLocation = useLocation();
  const navigate = useNavigate();
  const queryClient = useQueryClient();
  const activeView: AppView = ((): AppView => {
    const segment = routerLocation.pathname.replace(/^\/+/, "").split("/")[0];
    const views: AppView[] = ["chat", "tasks", "projects", "memory", "skills", "tools", "connectors", "history", "trace", "settings", "monitoring", "diagnostics"];
    return (views as string[]).includes(segment) ? (segment as AppView) : "chat";
  })();
  const setActiveView = useCallback((view: AppView) => {
    void navigate(view === "chat" ? "/" : `/${view}`);
  }, [navigate]);
  const [settingsSection, setSettingsSection] = useState<SettingsSection>("agents");
  const [settingsTab, setSettingsTab] = useState<SettingsTab>("modelo");
  const [settingsSearch, setSettingsSearch] = useState("");
  // Tasks + approvals live in TanStack Query: one poll covers the tasks view
  // (5s), the sidebar badge (30s) and post-mutation refreshes (invalidation).
  const tasksQuery = useQuery({
    queryKey: ["tasks", session?.id ?? 0],
    enabled: Boolean(session),
    refetchInterval: activeView === "tasks" ? 5000 : 30000,
    queryFn: async () => {
      const data = await apiRequest<{ tasks: Task[] }>("/api/tasks");
      const approvals: Record<number, TaskApproval[]> = {};
      for (const task of data.tasks.filter((task) => task.status === "awaiting_approval")) {
        try {
          const taskApprovalsData = await apiRequest<{ approvals: TaskApproval[] }>(`/api/tasks/approvals/pending?task_id=${task.id}`);
          approvals[task.id] = taskApprovalsData.approvals;
        } catch { /* sin aprobaciones */ }
      }
      return { tasks: data.tasks, taskApprovals: approvals };
    }
  });
  const tasks = tasksQuery.data?.tasks ?? [];
  const taskApprovals = tasksQuery.data?.taskApprovals ?? {};
  // Pending chat approvals poll only while the chat view is open.
  const approvalsQuery = useQuery({
    queryKey: ["approvals", activeConversationId],
    enabled: Boolean(session) && activeConversationId !== null && activeView === "chat",
    refetchInterval: 4000,
    queryFn: async () => {
      const data = await apiRequest<{ approvals: PendingApproval[] }>(`/api/approvals/pending?conversation_id=${activeConversationId}`);
      return data.approvals;
    }
  });
  const pendingApprovals = approvalsQuery.data ?? [];
  const [taskDraft, setTaskDraft] = useState({ goal: "", mode: "act", scheduled_at: "", recurrence: "" });
  const [expandedTaskId, setExpandedTaskId] = useState<number | null>(null);
  const [taskEvents, setTaskEvents] = useState<Record<number, TaskEvent[]>>({});
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
    // Approvals poll via the approvals query (refetchInterval).
  }, [session, activeConversationId, activeView]);

  useEffect(() => {
    if (!session || !projectDetail || projectTab !== "archivos") return;
    void refreshProjectFiles(projectDetail.id);
  }, [projectDetail?.id, projectTab]);

  const activeViewRef = useRef(activeView);
  activeViewRef.current = activeView;

  useEffect(() => {
    if (!session) return;
    void refreshMemories();
    void refreshProjects();
    // The tasks query polls itself: 5s in the tasks view, 30s elsewhere (badge).
  }, [session]);

  useEffect(() => {
    if (!session || (activeView !== "memory" && activeView !== "settings")) return;
    void refreshMemories();
    void refreshHabitSuggestions();
  }, [session, activeView]);

  // Session-expiry and unhandled failures: never let an error pass silently.
  useEffect(() => {
    const onUnauthorized = () => {
      setSession(null);
      setError("Tu sesión expiró. Vuelve a entrar.");
    };
    const onRejection = (event: PromiseRejectionEvent) => {
      const reason = event.reason;
      const message =
        reason instanceof Error ? reason.message :
        typeof reason === "string" ? reason :
        "La operación falló inesperadamente";
      setError(message);
      event.preventDefault();
    };
    window.addEventListener(UNAUTHORIZED_EVENT, onUnauthorized);
    window.addEventListener("unhandledrejection", onRejection);
    return () => {
      window.removeEventListener(UNAUTHORIZED_EVENT, onUnauthorized);
      window.removeEventListener("unhandledrejection", onRejection);
    };
  }, []);

  // Global errors auto-dismiss so the banner never gets stuck.
  useEffect(() => {
    if (!error) return;
    const timer = window.setTimeout(() => setError(""), 8000);
    return () => window.clearTimeout(timer);
  }, [error]);

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
    // Data lives in the tasks query; mutations just invalidate it.
    await queryClient.invalidateQueries({ queryKey: ["tasks"] });
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
    void conversationId; // key covers the active conversation; kept for interface compatibility
    await queryClient.invalidateQueries({ queryKey: ["approvals"] });
  }

  async function resumeApproval(approval: PendingApproval, approved: boolean) {
    if (!activeConversationId || resumingApprovalId !== null) return;
    setResumingApprovalId(approval.id);
    setError("");
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

  // Refs keep message-action callbacks identity-stable so memoized
  // MessageItems don't re-render on every streaming token.
  const messagesRef = useRef(messages);
  messagesRef.current = messages;
  const messageStackRef = useRef<HTMLDivElement | null>(null);
  const messageStackEndRef = useRef<HTMLDivElement | null>(null);

  // Auto-scroll: follow new content only when the user is already near the bottom.
  useEffect(() => {
    const stack = messageStackRef.current;
    if (!stack) return;
    const nearBottom = stack.scrollHeight - stack.scrollTop - stack.clientHeight < 160;
    if (nearBottom) messageStackEndRef.current?.scrollIntoView({ block: "end" });
  }, [messages]);
  const editingDraftRef = useRef(editingMessageDraft);
  editingDraftRef.current = editingMessageDraft;
  const activeConversationRef = useRef(activeConversationId);
  activeConversationRef.current = activeConversationId;

  const copyMessageText = useCallback((index: number) => {
    const text = messagesRef.current[index]?.content ?? "";
    void (async () => {
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
    })();
  }, []);

  const startEditMessage = useCallback((index: number) => {
    setEditingMessageIndex(index);
    setEditingMessageDraft(messagesRef.current[index]?.content ?? "");
  }, []);

  const saveEditMessage = useCallback((index: number) => {
    const message = messagesRef.current[index];
    const content = editingDraftRef.current.trim();
    const conversationId = activeConversationRef.current;
    if (!message || !content || !conversationId) return;
    void (async () => {
      try {
        if (message.id) {
          await apiRequest(`/api/conversations/${conversationId}/messages/${message.id}`, {
            method: "PATCH",
            body: JSON.stringify({ content })
          });
        }
        setMessages((current) => current.map((item, itemIndex) => itemIndex === index ? { ...item, content } : item));
        setEditingMessageIndex(null);
        setEditingMessageDraft("");
      } catch (err) {
        setError(err instanceof Error ? err.message : "Message update failed");
      }
    })();
  }, []);

  const cancelEditMessage = useCallback(() => {
    setEditingMessageIndex(null);
    setEditingMessageDraft("");
  }, []);

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
      const base: LiveActivityState = current ?? { label: "Iniciando…", startedAt: Date.now(), lastAt: Date.now() };
      const next = { ...base, iteration: event.iteration ?? base.iteration, chars: event.chars ?? base.chars, lastAt: Date.now() };
      if (event.kind === "thinking") next.label = `Pensando (iteración ${event.iteration ?? base.iteration ?? "?"})…`;
      else if (event.kind === "iteration") next.label = `Iteración ${event.iteration ?? "?"}`;
      else if (event.kind === "thought") { next.label = `Pensando (iteración ${event.iteration ?? base.iteration ?? "?"})…`; next.thought = event.text; }
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
      // Token buffering: cap re-renders at ~16/s regardless of token rate.
      let pending = "";
      let flushTimer: number | null = null;
      const flushTokens = () => {
        flushTimer = null;
        if (!pending) return;
        const chunk = pending;
        pending = "";
        setMessages((current) => {
          const next = [...current];
          const last = next[next.length - 1];
          next[next.length - 1] = { ...last, content: last.content + chunk };
          return next;
        });
      };
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
          pending += token;
          if (flushTimer === null) flushTimer = window.setTimeout(flushTokens, 60);
        },
        applyLiveActivity
      );
      if (flushTimer !== null) window.clearTimeout(flushTimer);
      flushTokens();
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
      <AuthScreen
        health={health}
        error={error}
        authMode={authMode}
        username={username}
        email={email}
        password={password}
        confirmPassword={confirmPassword}
        setUsername={setUsername}
        setEmail={setEmail}
        setPassword={setPassword}
        setConfirmPassword={setConfirmPassword}
        setAuthMode={setAuthMode}
        handleAuth={handleAuth}
      />
    );
  }

  const isAdmin = session.role === "admin";

  const appState: AppState = {
    session, authMode, username, email, password, confirmPassword,
    conversations, folders, expandedFolders, editingMessageIndex, editingMessageDraft, copiedMessageIndex,
    activeConversationId, messages, draft, metadata, runs, events, sources, toolCalls, attachments,
    selectedAttachmentIds, error, isStreaming, liveActivity, providerDraft, modelDraft, agentDraft, agentEditId,
    agentEditDraft, skillDraft, editingSkillId, skillTab, skillSearch, skillGeneratorPrompt, generatedSkill,
    mcpDraft, workflowDraft, selectedWorkflowId, selectedAgentId, internetUrl, skillResult, mcpValidation,
    catalogConnectors, pluginCatalog, pluginMarketplaces, marketplaceDraft, pluginBusy, pluginMessage,
    connectorTokenDrafts, connectorBusy, connectorMessage, mcpInspection, inspectingMcp, mcpRunDraft, mcpRunResult,
    health, modelCheckResult, diagnostics, metrics, metricsDays, auditLogs, auditLogLimit, auditFilters,
    agentTools, toolDefinitions, agentFallbacks, pendingApprovals, resumingApprovalId, detectedModels,
    detectingProvider, fallbackDraft, chatMode, paletteIndex, activeView, settingsSection, settingsTab,
    settingsSearch, tasks, taskDraft, expandedTaskId, taskEvents, taskApprovals, memories, habitSuggestions,
    memoryDraft, workspaceInfo, workspaceDraft, preferences, guardrailDraft, tasksSettings, historySearch,
    projects, projectDetail, projectDraft, projectInstructionsDraft, projectTab, projectFiles, projectTasks,
    projectMemories, projectTaskDraft, projectMemoryDraft, activeProjectName, leftSidebarCollapsed,
    rightSidebarOpen, userMenuOpen,
    isAdmin, selectedAgent, selectedWorkflow, activeProvider, activeModel, activeSkills, activeMcps,
    approximateTokens, activeTaskCount, paletteOpen, paletteSkills, settingsTabDefs, adminSections,
    settingsResults, filteredSkills, setProjectDraft,
    messageStackRef, messageStackEndRef,
    setActiveView, setActiveConversationId, setDraft, setEditingMessageDraft, setPaletteIndex, setChatMode,
    setSelectedWorkflowId, setSelectedAgentId, setSelectedAttachmentIds, setTaskDraft, setExpandedTaskId,
    setMemoryDraft, setProjectDetail, setProjectTab, setProjectTaskDraft, setProjectMemoryDraft,
    setProjectInstructionsDraft, setHistorySearch, setSettingsTab, setSettingsSection, setSettingsSearch,
    setSkillTab, setSkillSearch, setSkillGeneratorPrompt, setSkillDraft, setInternetUrl, setProviderDraft,
    setModelDraft, setAgentDraft, setAgentEditDraft, setAgentEditId, setMcpDraft, setMcpRunDraft,
    setMcpInspection, setWorkflowDraft, setFallbackDraft, setMetricsDays, setAuditLogLimit, setAuditFilters,
    setMarketplaceDraft, setConnectorTokenDrafts, setPreferences, setGuardrailDraft, setTasksSettings,
    setWorkspaceDraft, setUserMenuOpen, setLeftSidebarCollapsed, setRightSidebarOpen, setError,
    handleAuth, logout, createConversation, deleteConversation, renameConversation, createFolder, renameFolder,
    deleteFolder, moveConversation, toggleFolderExpanded, navButton, openSettings, sendMessage, resumeApproval,
    decideHabitSuggestion, saveEditMessage, cancelEditMessage, copyMessageText, startEditMessage, cycleChatMode,
    selectPaletteSkill, handleComposerKeyDown, handleAttachmentUpload, createTask, taskAction, removeTask,
    toggleTaskEvents, decideTaskApproval, formatDateTime, createProject, openProjectDetail, archiveProject,
    removeProject, createProjectChat, projectLinkConversation, createProjectTask, projectTaskAction,
    uploadProjectKnowledge, projectLinkAttachment, saveProjectInstructions, addProjectMemory, deleteProjectMemory,
    enableProjectWorkspace, unlinkProjectWorkspace, refreshProjectFiles, deleteProjectFile, addMemory,
    deleteMemory, resetHabits, testConnectorAccount, disconnectConnector, connectConnector, activateModel,
    createProvider, detectProviderModels, toggleProvider, savePreferences, saveWorkspace, saveGuardrails,
    saveTasksSettings, createAgent, editAgent, saveAgentEdit, toggleAgent, toggleAgentAgentic, toggleAgentTool,
    toggleAgentSkill, toggleAgentMcp, addAgentFallback, removeAgentFallback, createModel, toggleModel,
    deleteModel, checkModel, createWorkflow, toggleWorkflow, createMcpServer, validateMcpServer, runMcpServer,
    toggleMcpServer, inspectMcpServer, deleteMcpServer, installPluginEntry, uninstallPluginEntry,
    addPluginMarketplace, refreshPluginMarketplace, removePluginMarketplace, missingConnectorsFor, updateUserRole,
    refreshWorkspace, formatAuditMetadata, createSkill, editSkill, resetSkillEditor, toggleSkill, deleteSkill,
    generateSkillDraft, useGeneratedSkill, runReadUrl, skillAgents, loadMetrics, deleteAttachment
  };

  return (
    <AppStateContext.Provider value={appState}>
    <main className={`workspace-shell ${leftSidebarCollapsed ? "nav-collapsed" : ""} ${rightSidebarOpen ? "" : "right-collapsed"}`}>
      {error && (
        <div className="global-error-banner" role="alert">
          <span>{error}</span>
          <button type="button" className="text-button" aria-label="Cerrar aviso" onClick={() => setError("")}>×</button>
        </div>
      )}
      <LeftRail />

      <section className="main-stage">
        <header className="top-bar">
          <div>
            <p className="eyebrow">Obsessive Solutions</p>
            <h1>{activeView === "chat" ? (selectedAgent?.name ?? "ObsyGPT") : activeView === "tasks" ? "Tareas" : activeView === "projects" ? "Proyectos" : activeView === "memory" ? "Memoria" : activeView === "skills" ? "Skills" : activeView === "tools" ? "Herramientas" : activeView === "connectors" ? "Conectores" : activeView === "history" ? "Historial" : activeView === "settings" ? "Ajustes" : activeView === "trace" ? "Traza de runs" : activeView === "monitoring" ? "Monitoring" : "Diagnostics"}</h1>
          </div>
          <button className="details-button" onClick={() => setRightSidebarOpen((value) => !value)}>{rightSidebarOpen ? "Ocultar actividad" : "Actividad"}</button>
        </header>

        {activeView === "chat" && <ChatView />}

        {activeView === "tasks" && <TasksView />}

        {activeView === "projects" && <ProjectsView />}

        {activeView === "memory" && <MemoryView />}

        {activeView === "tools" && <ToolsView />}

        {activeView === "connectors" && <ConnectorsView />}

        {activeView === "history" && <HistoryView />}

        {activeView === "trace" && <TraceView />}

        {activeView === "settings" && <SettingsView />}

        {activeView === "skills" && <SkillsView />}

        {activeView === "monitoring" && isAdmin && <MonitoringView />}

        {activeView === "diagnostics" && isAdmin && <DiagnosticsView />}
      </section>

      {rightSidebarOpen && <RightRail />}

    </main>
    </AppStateContext.Provider>
  );
}

