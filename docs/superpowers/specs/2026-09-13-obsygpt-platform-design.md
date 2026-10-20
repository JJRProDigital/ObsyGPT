# ObsyGPT Platform Design

## Goal

Transform the current Python chat application into ObsyGPT: a visible multi-agent, multimodal AI platform with a modern frontend, configurable AI providers, skills, MCP integrations, and controlled internet access.

ObsyGPT is not only a chatbot. It is an agent workspace where users configure providers, models, agents, skills, MCP servers, workflows, files, and execution traces from the UI.

## Scope

The target system includes:

- A full rebrand from the previous product names to ObsyGPT.
- A modern frontend, preferably Next.js, React, and TypeScript.
- A FastAPI backend refactored into modules.
- PostgreSQL persistence for users, conversations, providers, models, agents, skills, MCPs, workflows, traces, files, artifacts, and sources.
- Multi-provider AI routing for OpenRouter, OpenAI, Anthropic, Gemini, Ollama, llama.cpp, and generic OpenAI-compatible endpoints.
- Visible multi-agent execution with traces and per-step events.
- Skills as reusable internal capabilities.
- MCP server configuration and per-agent access control.
- Controlled internet access through search, URL reading, extraction, and source tracking.
- Initial multimodality for images, PDFs, text, Markdown, and CSV files.

Out of initial scope:

- Full video understanding.
- Drag-and-drop visual workflow editing in the first implementation pass.
- Billing, organizations, team permissions, and public sharing.
- Production-grade sandboxing for arbitrary code execution.

## Architecture

```text
Modern Frontend
  -> FastAPI API
  -> Auth, Conversations, Files, Settings
  -> Workflow Orchestrator
  -> Agent Runtime
  -> Skills Runtime
  -> MCP Gateway
  -> Provider Router
  -> AI Providers
  -> Trace Store, Artifacts, Sources, Final Response
```

The backend owns orchestration and persistence. The frontend presents configuration, chat, file attachments, workflow selection, and live traces.

## Frontend

The frontend should move from simple Flask templates to a modern application. Next.js with React and TypeScript is the preferred implementation because the requested product needs stateful dashboards, forms, trace views, and workflow configuration.

Primary screens:

- Chat Workspace: conversation UI, selected agent/workflow, attachments, live trace panel, final answer.
- Agent Studio: create, edit, enable, disable, and test agents.
- Provider Settings: configure provider credentials, base URLs, models, defaults, and capabilities.
- Workflow Builder: define single-agent, sequential, supervisor, reviewer, parallel, and debate workflows.
- Skills Library: manage internal skills and assign them to agents.
- MCP Manager: register MCP servers, test connectivity, assign them to agents, and inspect call logs.
- Trace Viewer: inspect agent events, tool calls, MCP calls, sources, errors, duration, tokens, and cost estimates.
- Files and Artifacts: view uploaded files, extracted content, generated artifacts, and source citations.

The first frontend implementation can use forms and structured panels. A visual drag-and-drop builder can come later.

## Backend

The current backend should be split from one large `app.py` into modules:

```text
backend/app/
  main.py
  api/
  auth/
  db/
  providers/
  agents/
  workflows/
  skills/
  mcps/
  tools/
  files/
  internet/
  traces/
  settings/
```

The current chat endpoint should stop calling OpenRouter directly. It should save the user message, create a workflow run, execute the selected workflow through the orchestrator, stream visible events and the final response, then persist all outputs.

## Provider Router

Providers implement a common interface:

```text
chat
stream_chat
vision
embeddings
tool_calling
json_mode
audio_transcription
```

Initial providers:

- OpenRouter.
- OpenAI.
- Anthropic.
- Gemini.
- Ollama.
- llama.cpp through an OpenAI-compatible endpoint when available.
- Custom OpenAI-compatible provider.

Provider and model records declare capabilities including text, streaming, vision, audio, tool calling, JSON mode, embeddings, context window, default model, and enabled state.

## Agents

Agents are configured from the UI and executed by the agent runtime.

Each agent has:

- Name and description.
- System prompt.
- Provider and model.
- Temperature and generation settings.
- Allowed skills.
- Allowed MCP servers.
- Internet access permission.
- Multimodal permission.
- Token and cost limits.
- Enabled state.

Initial built-in agents:

- Supervisor Agent: decides workflow steps.
- Research Agent: uses internet and source extraction.
- Document Agent: reads uploaded documents.
- Vision Agent: analyzes images when the chosen model supports vision.
- Writer Agent: drafts user-facing responses.
- Critic Agent: reviews quality, accuracy, and missing context.
- Final Answer Agent: synthesizes the final answer.

## Workflows

Supported workflow types:

- Single Agent: one configured agent answers.
- Sequential: fixed ordered agent steps.
- Supervisor: a supervisor decides which agents to run.
- Reviewer: a responder and critic produce a final answer.
- Parallel: multiple agents run independently, then a synthesizer combines outputs.
- Debate: multiple agents propose viewpoints, then a final agent resolves.

The first implementation should support Single Agent, Sequential, Supervisor, and Reviewer. Parallel and Debate can be implemented after the trace and event model is stable.

## Skills

Skills are internal capabilities with schemas, permissions, handlers, and trace logging.

Initial skills:

- `web_search`: search the web and return ranked results.
- `read_url`: fetch and extract clean content from a URL.
- `extract_pdf`: extract text and metadata from uploaded PDFs.
- `summarize_document`: summarize extracted document content.
- `analyze_image`: prepare image prompts and route to a vision-capable provider.
- `code_assistant`: analyze or generate code text.
- `critic_review`: review an intermediate answer.
- `final_answer`: synthesize a final response.

Each skill execution should create a trace event with input summary, output summary, duration, errors, and sources where applicable.

## MCP Gateway

The MCP Gateway manages external MCP servers and exposes approved tools to agents.

Required capabilities:

- Register MCP servers by command or URL.
- Enable or disable MCP servers.
- Assign MCP servers to agents.
- List available tools per MCP server.
- Execute approved MCP tools.
- Store MCP call logs, errors, latency, and input/output summaries.

MCP permissions must be explicit per agent. Agents should not automatically receive access to every MCP server.

## Internet Access

Internet access is a controlled tool capability.

Initial layers:

- Web search.
- URL reading.
- Clean content extraction.
- Source citation tracking.

Later layers:

- Headless browser navigation.
- Screenshots.
- Interactive browsing.

Every internet operation should be recorded in `sources` and linked to an agent event or tool call.

## Multimodality

Initial supported inputs:

- Images.
- PDFs.
- Plain text.
- Markdown.
- CSV.

Later inputs:

- DOCX.
- Audio with transcription.
- Video.

The backend should store files as attachments and create artifacts for extracted text, summaries, image analyses, transcriptions, or generated outputs. The orchestrator decides whether to send media directly to a model or preprocess it with a skill.

## Data Model

Existing tables remain conceptually useful: users, conversations, and messages.

New tables:

- `providers`.
- `models`.
- `agents`.
- `skills`.
- `agent_skills`.
- `mcp_servers`.
- `agent_mcps`.
- `workflows`.
- `workflow_steps`.
- `agent_runs`.
- `agent_events`.
- `tool_calls`.
- `mcp_calls`.
- `attachments`.
- `artifacts`.
- `sources`.
- `settings`.

All run-time operations should be traceable back to a user, conversation, message, workflow, and agent run where applicable.

## Rebranding

All product references must use ObsyGPT.

Expected changes:

- UI titles and labels.
- README and documentation.
- Backend title.
- Session cookie name must be `obsygpt_session`.
- Example database names and environment placeholders.
- Error messages.
- Local app naming.

Historical license attribution remains unchanged.

## Error Handling

The system should expose clean user-facing errors and retain detailed internal trace events.

Error categories:

- Provider unavailable.
- Model capability mismatch.
- Missing provider credentials.
- Agent disabled or not found.
- Workflow misconfigured.
- Skill execution failure.
- MCP server unreachable.
- File too large or unsupported.
- Internet extraction failure.

The final chat UI should show a useful summary while Trace Viewer exposes the exact failed step.

## Testing Strategy

Backend:

- Unit tests for provider normalization and capability checks.
- Unit tests for agent runtime and workflow decisions.
- Unit tests for skills and MCP permission checks.
- API tests for auth, providers, agents, workflows, files, and chat.
- Regression test that OpenRouter text chat still works after refactor.

Frontend:

- Component tests for Agent Studio, Provider Settings, Trace Viewer, and Chat Workspace.
- API contract tests or generated client validation.
- Browser smoke tests for login, provider setup, agent creation, chat execution, and trace display.

Database:

- Migration tests for new schema.
- Seed data tests for default providers, models, agents, skills, and workflows.

## Implementation Phases

1. Rebrand current app to ObsyGPT and verify existing chat still works.
2. Refactor FastAPI backend into modules while preserving existing behavior.
3. Create provider abstraction and migrate OpenRouter to it.
4. Add OpenAI, Anthropic, Gemini, Ollama, llama.cpp, and OpenAI-compatible provider records and adapters.
5. Create modern frontend shell and authentication flow.
6. Add Provider Settings UI.
7. Add Agent Studio and backend CRUD.
8. Add workflow runtime and visible traces.
9. Add Skills Library and initial skills.
10. Add MCP Manager and gateway.
11. Add internet search, URL reading, extraction, and citations.
12. Add file uploads, attachments, images, PDFs, and artifacts.

## Approval

This design reflects the approved direction: option B, with a modern frontend and ObsyGPT as a visible multi-agent platform.
