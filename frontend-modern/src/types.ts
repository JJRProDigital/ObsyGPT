// Domain types shared across the ObsyGPT frontend.

export type User = { id: number; username: string; role?: "admin" | "user" };
export type SessionResponse = { logged_in: boolean; user: User | null };
export type HealthResponse = { status: string; database?: string };
export type ModelCheckResponse = { ready?: boolean; enabled?: boolean; provider_enabled?: boolean; api_key_configured?: boolean; api_key_env?: string; model_name?: string; provider?: string; [key: string]: unknown };
export type DiagnosticsResponse = { counts: Record<string, number>; providers: Array<{ id: number; name: string; ready: boolean; enabled: boolean; configured_models: number; api_key_configured: boolean }> };
export type AuditLog = { id: number; actor_username: string | null; action: string; target_type: string; target_id: number | null; metadata: Record<string, unknown>; created_at: string };
export type Conversation = { id: number; title: string; label?: string; created_at: string; folder_id?: number | null };
export type ChatFolder = { id: number; name: string; conversation_count: number };
export type Message = { role: "user" | "assistant"; content: string; created_at?: string; id?: number };
export type Provider = { id: number; name: string; provider_type: string; base_url: string | null; api_key_env: string | null; enabled: boolean };
export type Model = { id: number; display_name: string; model_name: string; provider_id: number; supports_text: boolean; supports_streaming: boolean; supports_vision: boolean; supports_audio: boolean; supports_tools: boolean; supports_json: boolean; context_window: number | null; enabled: boolean };
export type Agent = { id: number; name: string; description: string; system_prompt?: string; provider_id: number | null; model_id: number | null; temperature: string | number; internet_enabled: boolean; multimodal_enabled: boolean; agentic_mode?: boolean; enabled: boolean };
export type AgentTool = { agent_id: number; tool_name: string; allowed: boolean };
export type ToolDefinition = { name: string; description: string; parameters: string; permission: "safe" | "sensitive" };
export type PendingApproval = { id: number; agent_run_id: number; conversation_id: number; tool_name: string; args: Record<string, unknown>; created_at: string };
export type DetectedModel = { model_name: string; display_name: string; already_registered: boolean };
export type AgentFallback = { agent_id: number; provider_id: number; model_id: number; priority: number; provider_name: string; model_display_name: string };
export type Task = { id: number; goal: string; mode: string; status: string; scheduled_at: string | null; attempts: number; agent_id: number | null; project_id: number | null; recurrence: string | null; last_occurrence_at?: string | null; result: string; error: string; created_at: string; updated_at: string };
export type TaskEvent = { id: number; event_type: string; title: string; content: string; created_at: string };
export type TaskApproval = { id: number; task_id: number; tool_name: string; args: Record<string, unknown>; created_at: string };
export type MemoryItem = { id: number; kind: string; content: string; project_id?: number | null; created_at: string; updated_at: string };
export type HabitSuggestion = { id: number; content: string; evidence: string; source: string; created_at: string };
export type WorkspaceInfo = { workspace: string; recent: string[]; default: string };
export type Preferences = { display_name: string; accent: string; memory_max: number; tool_policies: Record<string, string>; instructions: string };
export type GuardrailSettings = { max_iterations?: number; max_tool_calls?: number; max_duration_seconds?: number; max_tool_output_chars?: number; max_total_chars?: number; loop_repeat_limit?: number };
export type TasksSettings = { max_concurrent_tasks: number; auto_resume_tasks: boolean };
export type Project = { id: number; name: string; description: string; instructions: string; folder_path?: string | null; archived?: boolean; conversation_count?: number; attachment_count?: number; active_task_count?: number; created_at: string; updated_at: string };
export type ProjectDetail = Project & { conversations: Array<{ id: number; title: string; created_at: string }>; attachments: Attachment[] };
export type ProjectTab = "chats" | "tareas" | "conocimiento" | "instrucciones" | "memoria" | "archivos";
export type ProjectFileEntry = { name: string; is_dir: boolean; size: number; modified: string };
export type ProjectFilesResponse = { folder: string | null; subpath: string; parent: string | null; entries: ProjectFileEntry[] };
export type Skill = { id: number; name: string; description: string; argument_hint: string; triggers: Array<"user" | "model">; body: string; resources: string; skill_md: string; enabled: boolean };
export type McpServer = { id: number; name: string; description: string; connection_type: string; command: string | null; url: string | null; enabled: boolean };
export type CatalogConnector = { slug: string; name: string; description: string; token_label: string; token_help: string; tool_names: string[]; account: { id: number; display_name: string; status: string } | null };
export type PluginCatalogEntry = { slug: string; name: string; version: string; description: string; source: string; marketplace_name: string | null; installed: boolean; connectors: string[]; components: { skills: number; mcps: number; agents: number } };
export type PluginMarketplace = { name: string; url: string };
export type AgentSkill = { agent_id: number; skill_id: number };
export type AgentMcp = { agent_id: number; mcp_server_id: number };
export type ProviderDefinition = { provider_type: string; display_name: string; default_base_url: string | null; api_key_env: string | null; supports_vision: boolean; supports_tools: boolean; supports_audio: boolean; supports_json: boolean };
export type Workflow = { id: number; name: string; workflow_type: string; enabled: boolean };
export type WorkflowStep = { workflow_id: number; agent_id: number; step_order: number; step_name: string };
export type AdminUser = { id: number; username: string; email: string; role: "admin" | "user"; created_at: string };
export type AgentRun = { id: number; status: string; final_response: string | null; created_at: string; completed_at: string | null; parent_run_id?: number | null };
export type AgentEvent = { id: number; event_type: string; title: string; content: string; created_at: string };
export type Attachment = { id: number; file_name: string; mime_type: string; size_bytes: number };
export type Source = { id: number; agent_run_id: number; url: string; title: string; snippet: string; created_at: string };
export type ToolCall = { id: number; agent_run_id: number; skill_name: string; input_summary: string; output_summary: string; status: string; created_at: string };
export type AppView = "chat" | "tasks" | "projects" | "memory" | "skills" | "tools" | "connectors" | "history" | "trace" | "settings" | "monitoring" | "diagnostics";
export type MetricsResponse = {
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
export type SettingsTab = "modelo" | "preferencias" | "seguridad" | "agente" | "datos" | "admin";
export type AdminSection = "agents" | "models" | "workflows" | "mcps" | "plugins" | "users" | "audit";
export type SettingsSection = AdminSection;
export type SkillTab = "library" | "editor" | "generator";
export type SkillDraftResponse = { name: string; description: string; argument_hint: string; triggers: Array<"user" | "model">; body: string; resources: string; instructions: string; checklist: string[] };

export const emptyMetadata = {
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
