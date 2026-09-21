from collections.abc import Iterator
from dataclasses import dataclass
import re
from typing import Literal

from ..providers import ChatMessage, ChatRequest, ProviderRegistry
from ..skills.runtime import SkillRegistry
from ..traces.store import TraceStore


WorkflowType = Literal["single_agent", "sequential", "supervisor", "reviewer", "parallel", "debate"]


@dataclass(frozen=True)
class McpSpec:
    name: str
    description: str
    connection_type: str


@dataclass(frozen=True)
class FallbackSpec:
    provider_type: str
    provider_base_url: str | None
    provider_api_key_env: str | None
    model: str


@dataclass(frozen=True)
class AgentSpec:
    id: int | None
    name: str
    system_prompt: str
    provider_type: str
    provider_base_url: str | None
    provider_api_key_env: str | None
    model: str
    temperature: float
    internet_enabled: bool = False
    multimodal_enabled: bool = False
    allowed_skills: list[str] | None = None
    allowed_mcps: list[McpSpec] | None = None
    agentic_mode: bool = False
    fallbacks: list[FallbackSpec] | None = None
    model_supports_vision: bool = False


@dataclass(frozen=True)
class WorkflowSpec:
    id: int | None
    name: str
    workflow_type: WorkflowType
    agents: list[AgentSpec]


class WorkflowRuntime:
    def __init__(
        self,
        provider_registry: ProviderRegistry | None = None,
        trace_store: TraceStore | None = None,
        skill_registry: SkillRegistry | None = None,
    ):
        self.provider_registry = provider_registry or ProviderRegistry()
        self.trace_store = trace_store or TraceStore()
        self.skill_registry = skill_registry or SkillRegistry()

    def stream_workflow(self, agent_run_id: int, workflow: WorkflowSpec, messages: list[ChatMessage]) -> Iterator[str]:
        if not workflow.agents:
            raise ValueError("Workflow requires at least one agent.")

        self.trace_store.add_event(agent_run_id, "workflow_started", "Workflow started", workflow.name)

        try:
            if workflow.workflow_type == "single_agent":
                final_response = self._run_agent(agent_run_id, workflow.agents[0], messages)
            elif workflow.workflow_type == "reviewer":
                final_response = self._run_reviewer(agent_run_id, workflow, messages)
            elif workflow.workflow_type == "supervisor":
                final_response = self._run_supervisor(agent_run_id, workflow, messages)
            elif workflow.workflow_type == "parallel":
                final_response = self._run_parallel(agent_run_id, workflow, messages)
            elif workflow.workflow_type == "debate":
                final_response = self._run_debate(agent_run_id, workflow, messages)
            else:
                final_response = self._run_sequential(agent_run_id, workflow, messages)

            yield final_response
            self.trace_store.add_event(agent_run_id, "workflow_completed", "Workflow completed", workflow.name)
            self.trace_store.complete_run(agent_run_id, final_response)
        except Exception as error:
            self.trace_store.add_event(agent_run_id, "workflow_failed", "Workflow failed", repr(error))
            self.trace_store.fail_run(agent_run_id, str(error))
            raise

    def _run_sequential(self, agent_run_id: int, workflow: WorkflowSpec, messages: list[ChatMessage]) -> str:
        current_messages = messages
        final_response = ""

        for agent in workflow.agents:
            final_response = self._run_agent(agent_run_id, agent, current_messages)
            current_messages = [*messages, ChatMessage(role="assistant", content=final_response)]

        return final_response

    def _run_reviewer(self, agent_run_id: int, workflow: WorkflowSpec, messages: list[ChatMessage]) -> str:
        if len(workflow.agents) < 2:
            return self._run_agent(agent_run_id, workflow.agents[0], messages)

        draft = self._run_agent(agent_run_id, workflow.agents[0], messages)
        review_messages = [
            *messages,
            ChatMessage(role="assistant", content=draft),
            ChatMessage(role="user", content=f"Review and improve this answer:\n\n{draft}"),
        ]
        return self._run_agent(agent_run_id, workflow.agents[1], review_messages)

    def _run_supervisor(self, agent_run_id: int, workflow: WorkflowSpec, messages: list[ChatMessage]) -> str:
        supervisor = workflow.agents[0]
        worker_agents = workflow.agents[1:]

        if not worker_agents:
            return self._run_agent(agent_run_id, supervisor, messages)

        plan = self._run_agent(agent_run_id, supervisor, messages)
        self.trace_store.add_event(agent_run_id, "supervisor_plan", "Supervisor plan created", plan)

        current_messages = [*messages, ChatMessage(role="user", content=f"Supervisor plan:\n\n{plan}")]
        final_response = plan

        for agent in worker_agents:
            final_response = self._run_agent(agent_run_id, agent, current_messages)
            current_messages = [*current_messages, ChatMessage(role="assistant", content=final_response)]

        return final_response

    def _run_parallel(self, agent_run_id: int, workflow: WorkflowSpec, messages: list[ChatMessage]) -> str:
        outputs = []

        for agent in workflow.agents:
            output = self._run_agent(agent_run_id, agent, messages)
            outputs.append(f"{agent.name}:\n{output}")

        self.trace_store.add_event(agent_run_id, "workflow_parallel", "Parallel agents completed", f"{len(outputs)} agents")
        return "\n\n".join(outputs)

    def _run_debate(self, agent_run_id: int, workflow: WorkflowSpec, messages: list[ChatMessage]) -> str:
        if len(workflow.agents) < 3:
            return self._run_parallel(agent_run_id, workflow, messages)

        debaters = workflow.agents[:-1]
        judge = workflow.agents[-1]
        positions = []

        for agent in debaters:
            output = self._run_agent(agent_run_id, agent, messages)
            positions.append(f"{agent.name}:\n{output}")

        debate_context = "\n\n".join(positions)
        self.trace_store.add_event(agent_run_id, "workflow_debate", "Debate positions collected", f"{len(positions)} positions")

        judge_messages = [
            *messages,
            ChatMessage(role="user", content=f"Resolve this debate and provide the final answer:\n\n{debate_context}"),
        ]
        return self._run_agent(agent_run_id, judge, judge_messages)

    def _run_agent(self, agent_run_id: int, agent: AgentSpec, messages: list[ChatMessage]) -> str:
        self.trace_store.add_event(agent_run_id, "agent_started", f"{agent.name} started")
        prepared_messages = self._prepare_messages(agent_run_id, agent, messages)

        request = ChatRequest(
            model=agent.model,
            messages=[ChatMessage(role="system", content=agent.system_prompt), *prepared_messages[-20:]],
            temperature=agent.temperature,
        )

        def call_primary() -> str:
            return "".join(
                self.provider_registry.stream_chat_with_config(
                    agent.provider_type,
                    request,
                    api_key_env=agent.provider_api_key_env,
                    base_url=agent.provider_base_url,
                )
            )

        response = self._call_with_fallbacks(agent_run_id, agent, request, call_primary)
        self.trace_store.add_event(agent_run_id, "agent_completed", f"{agent.name} completed", response)
        return response

    def _call_with_fallbacks(self, agent_run_id: int, agent: AgentSpec, request: ChatRequest, call_primary) -> str:  # noqa: ANN001
        try:
            return call_primary()
        except Exception as primary_error:  # noqa: BLE001
            for fallback in agent.fallbacks or []:
                try:
                    self.trace_store.add_event(
                        agent_run_id,
                        "provider_fallback",
                        f"Fallback to {fallback.model}",
                        f"Primary failed: {repr(primary_error)[:200]}",
                    )
                    return "".join(
                        self.provider_registry.stream_chat_with_config(
                            fallback.provider_type,
                            ChatRequest(model=fallback.model, messages=request.messages, temperature=request.temperature),
                            api_key_env=fallback.provider_api_key_env,
                            base_url=fallback.provider_base_url,
                        )
                    )
                except Exception:  # noqa: BLE001
                    continue
            raise

    def _prepare_messages(self, agent_run_id: int, agent: AgentSpec, messages: list[ChatMessage]) -> list[ChatMessage]:
        messages = self._prepare_mcp_context(agent_run_id, agent, messages)
        if not agent.internet_enabled:
            return messages

        user_text = "\n".join(message.content for message in messages if message.role == "user")
        urls = self._extract_urls(user_text)
        if not urls:
            return self._prepare_search_context(agent_run_id, agent, messages, user_text)

        if "read_url" not in (agent.allowed_skills or []):
            self.trace_store.add_event(agent_run_id, "tool_skipped", "read_url skipped", "Skill is not assigned to this agent.")
            for url in urls[:3]:
                self.trace_store.add_tool_call(agent_run_id, "read_url", url, "Skill is not assigned to this agent.", "failed")
            return messages

        context_blocks = []
        for url in urls[:3]:
            self.trace_store.add_event(agent_run_id, "tool_started", "read_url started", url)
            result = self.skill_registry.run("read_url", {"url": url})
            self.trace_store.add_event(agent_run_id, "tool_completed", "read_url completed", url)
            self.trace_store.add_tool_call(agent_run_id, "read_url", url, result["title"], "completed")
            self.trace_store.add_source(
                agent_run_id,
                result["url"],
                result["title"],
                result["content"],
            )
            context_blocks.append(f"Source: {result['title']}\nURL: {result['url']}\nContent: {result['content']}")

        if not context_blocks:
            return messages

        tool_context = "Web context gathered by ObsyGPT:\n\n" + "\n\n".join(context_blocks)
        return [*messages, ChatMessage(role="user", content=tool_context)]

    def _prepare_search_context(
        self,
        agent_run_id: int,
        agent: AgentSpec,
        messages: list[ChatMessage],
        user_text: str,
    ) -> list[ChatMessage]:
        query = user_text.strip()
        if not self._looks_like_search_request(query):
            return messages

        if "web_search" not in (agent.allowed_skills or []):
            self.trace_store.add_event(agent_run_id, "tool_skipped", "web_search skipped", "Skill is not assigned to this agent.")
            self.trace_store.add_tool_call(agent_run_id, "web_search", query, "Skill is not assigned to this agent.", "failed")
            return messages

        self.trace_store.add_event(agent_run_id, "tool_started", "web_search started", query)
        result = self.skill_registry.run("web_search", {"query": query, "limit": 5})
        results = result.get("results", [])
        self.trace_store.add_event(agent_run_id, "tool_completed", "web_search completed", query)
        self.trace_store.add_tool_call(agent_run_id, "web_search", query, f"{len(results)} results", "completed")

        context_blocks = []
        for item in results:
            title = item.get("title", item.get("url", "Search result"))
            url = item.get("url", "")
            snippet = item.get("snippet", "")
            if url:
                self.trace_store.add_source(agent_run_id, url, title, snippet)
            context_blocks.append(f"Result: {title}\nURL: {url}\nSnippet: {snippet}")

        if not context_blocks:
            return messages

        tool_context = "Search context gathered by ObsyGPT:\n\n" + "\n\n".join(context_blocks)
        return [*messages, ChatMessage(role="user", content=tool_context)]

    def _prepare_mcp_context(self, agent_run_id: int, agent: AgentSpec, messages: list[ChatMessage]) -> list[ChatMessage]:
        mcps = agent.allowed_mcps or []
        if not mcps:
            return messages

        lines = [f"- {mcp.name} ({mcp.connection_type}): {mcp.description}" for mcp in mcps]
        self.trace_store.add_event(agent_run_id, "mcp_context", "MCP context added", f"{len(mcps)} MCP server(s) available")
        return [*messages, ChatMessage(role="user", content="Available MCP servers for this agent:\n" + "\n".join(lines))]

    def _extract_urls(self, text: str) -> list[str]:
        matches = re.findall(r"https?://[^\s)\]}>,]+", text)
        return list(dict.fromkeys(match.rstrip(".,;:") for match in matches))

    def _looks_like_search_request(self, text: str) -> bool:
        lowered = text.lower()
        return any(phrase in lowered for phrase in ["search ", "buscar ", "investigate", "research", "find sources", "busca "])
