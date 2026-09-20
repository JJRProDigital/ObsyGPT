from app.providers import ChatMessage
from app.workflows.runtime import AgentSpec, McpSpec, WorkflowRuntime, WorkflowSpec


class FakeProviderRegistry:
    def __init__(self):
        self.calls = []
        self.last_request = None

    def stream_chat(self, provider_type, request):
        prompt = request.messages[-1].content
        yield f"{provider_type}:{request.model}:{prompt}"

    def stream_chat_with_config(self, provider_type, request, api_key_env=None, base_url=None):
        self.calls.append((provider_type, api_key_env, base_url))
        self.last_request = request
        prompt = request.messages[-1].content
        if base_url is None:
            yield f"{provider_type}:{request.model}:{prompt}"
            return
        yield f"{provider_type}:{base_url}:{request.model}:{prompt}"


class FakeTraceStore:
    def __init__(self):
        self.events = []
        self.completed = []
        self.sources = []
        self.tool_calls = []

    def add_event(self, agent_run_id, event_type, title, content=""):
        self.events.append((agent_run_id, event_type, title, content))

    def complete_run(self, agent_run_id, final_response):
        self.completed.append((agent_run_id, final_response))

    def fail_run(self, agent_run_id, error_message):
        self.events.append((agent_run_id, "failed", "Failed", error_message))

    def add_source(self, agent_run_id, url, title, snippet):
        self.sources.append((agent_run_id, url, title, snippet))

    def add_tool_call(self, agent_run_id, skill_name, input_summary, output_summary, status):
        self.tool_calls.append((agent_run_id, skill_name, input_summary, output_summary, status))


class FakeSkillRegistry:
    def __init__(self):
        self.calls = []

    def run(self, name, payload):
        self.calls.append((name, payload))
        if name == "web_search":
            return {
                "query": payload["query"],
                "results": [
                    {"title": "Search Result", "url": "https://example.com/search", "snippet": "Search result snippet."}
                ],
            }
        return {
            "url": payload["url"],
            "title": "Example",
            "content": "Extracted web page content.",
        }


def make_agent(name: str) -> AgentSpec:
    return AgentSpec(
        id=1,
        name=name,
        system_prompt=f"You are {name}.",
        provider_type="fake",
        provider_base_url=None,
        provider_api_key_env=None,
        model="model-a",
        temperature=0.2,
        internet_enabled=False,
        multimodal_enabled=False,
        allowed_skills=[],
    )


def test_workflow_runtime_passes_agent_provider_config_to_registry():
    traces = FakeTraceStore()
    registry = FakeProviderRegistry()
    runtime = WorkflowRuntime(provider_registry=registry, trace_store=traces)
    agent = AgentSpec(
        id=2,
        name="Local Agent",
        system_prompt="Use local model.",
        provider_type="openai_compatible",
        provider_base_url="http://127.0.0.1:8080/v1",
        provider_api_key_env="LOCAL_API_KEY",
        model="local-model",
        temperature=0.1,
        internet_enabled=False,
        multimodal_enabled=False,
        allowed_skills=[],
    )

    result = "".join(
        runtime.stream_workflow(
            agent_run_id=11,
            workflow=WorkflowSpec(id=1, name="Local", workflow_type="single_agent", agents=[agent]),
            messages=[ChatMessage(role="user", content="hello")],
        )
    )

    assert result == "openai_compatible:http://127.0.0.1:8080/v1:local-model:hello"
    assert registry.calls == [("openai_compatible", "LOCAL_API_KEY", "http://127.0.0.1:8080/v1")]


def test_internet_enabled_agent_reads_urls_and_injects_context():
    traces = FakeTraceStore()
    registry = FakeProviderRegistry()
    skills = FakeSkillRegistry()
    runtime = WorkflowRuntime(provider_registry=registry, trace_store=traces, skill_registry=skills)
    agent = AgentSpec(
        id=3,
        name="Research Agent",
        system_prompt="Research carefully.",
        provider_type="fake",
        provider_base_url=None,
        provider_api_key_env=None,
        model="model-a",
        temperature=0.1,
        internet_enabled=True,
        multimodal_enabled=False,
        allowed_skills=["read_url"],
    )

    result = "".join(
        runtime.stream_workflow(
            agent_run_id=12,
            workflow=WorkflowSpec(id=5, name="Research", workflow_type="single_agent", agents=[agent]),
            messages=[ChatMessage(role="user", content="Read https://example.com and summarize it")],
        )
    )

    assert "Extracted web page content." in registry.last_request.messages[-1].content
    assert skills.calls == [("read_url", {"url": "https://example.com"})]
    assert (12, "tool_completed", "read_url completed", "https://example.com") in traces.events
    assert traces.sources == [(12, "https://example.com", "Example", "Extracted web page content.")]
    assert traces.tool_calls == [(12, "read_url", "https://example.com", "Example", "completed")]
    assert result.startswith("fake:model-a:")


def test_agent_without_internet_does_not_read_urls():
    traces = FakeTraceStore()
    registry = FakeProviderRegistry()
    skills = FakeSkillRegistry()
    runtime = WorkflowRuntime(provider_registry=registry, trace_store=traces, skill_registry=skills)

    list(
        runtime.stream_workflow(
            agent_run_id=13,
            workflow=WorkflowSpec(id=6, name="No Internet", workflow_type="single_agent", agents=[make_agent("Assistant")]),
            messages=[ChatMessage(role="user", content="Read https://example.com")],
        )
    )

    assert skills.calls == []
    assert "Extracted web page content." not in registry.last_request.messages[-1].content


def test_internet_enabled_agent_without_read_url_skill_does_not_read_urls():
    traces = FakeTraceStore()
    registry = FakeProviderRegistry()
    skills = FakeSkillRegistry()
    runtime = WorkflowRuntime(provider_registry=registry, trace_store=traces, skill_registry=skills)
    agent = AgentSpec(
        id=4,
        name="Restricted Research Agent",
        system_prompt="Research carefully.",
        provider_type="fake",
        provider_base_url=None,
        provider_api_key_env=None,
        model="model-a",
        temperature=0.1,
        internet_enabled=True,
        multimodal_enabled=False,
        allowed_skills=[],
    )

    list(
        runtime.stream_workflow(
            agent_run_id=14,
            workflow=WorkflowSpec(id=7, name="Restricted", workflow_type="single_agent", agents=[agent]),
            messages=[ChatMessage(role="user", content="Read https://example.com")],
        )
    )

    assert skills.calls == []
    assert (14, "tool_skipped", "read_url skipped", "Skill is not assigned to this agent.") in traces.events
    assert traces.tool_calls == [(14, "read_url", "https://example.com", "Skill is not assigned to this agent.", "failed")]


def test_internet_enabled_agent_with_web_search_skill_adds_search_context():
    traces = FakeTraceStore()
    registry = FakeProviderRegistry()
    skills = FakeSkillRegistry()
    runtime = WorkflowRuntime(provider_registry=registry, trace_store=traces, skill_registry=skills)
    agent = AgentSpec(
        id=5,
        name="Search Agent",
        system_prompt="Research carefully.",
        provider_type="fake",
        provider_base_url=None,
        provider_api_key_env=None,
        model="model-a",
        temperature=0.1,
        internet_enabled=True,
        multimodal_enabled=False,
        allowed_skills=["web_search"],
    )

    result = "".join(
        runtime.stream_workflow(
            agent_run_id=18,
            workflow=WorkflowSpec(id=11, name="Search", workflow_type="single_agent", agents=[agent]),
            messages=[ChatMessage(role="user", content="search for multi agent orchestration patterns")],
        )
    )

    assert "Search result snippet." in registry.last_request.messages[-1].content
    assert skills.calls == [("web_search", {"query": "search for multi agent orchestration patterns", "limit": 5})]
    assert traces.sources == [(18, "https://example.com/search", "Search Result", "Search result snippet.")]
    assert traces.tool_calls == [(18, "web_search", "search for multi agent orchestration patterns", "1 results", "completed")]
    assert result.startswith("fake:model-a:")


def test_agent_with_assigned_mcps_gets_mcp_context():
    traces = FakeTraceStore()
    registry = FakeProviderRegistry()
    runtime = WorkflowRuntime(provider_registry=registry, trace_store=traces)
    agent = AgentSpec(
        id=7,
        name="MCP Agent",
        system_prompt="Use tools carefully.",
        provider_type="fake",
        provider_base_url=None,
        provider_api_key_env=None,
        model="model-a",
        temperature=0.1,
        allowed_mcps=[McpSpec(name="filesystem", description="Local file access", connection_type="command")],
    )

    list(
        runtime.stream_workflow(
            agent_run_id=20,
            workflow=WorkflowSpec(id=13, name="MCP", workflow_type="single_agent", agents=[agent]),
            messages=[ChatMessage(role="user", content="list tools")],
        )
    )

    assert "Available MCP servers" in registry.last_request.messages[-1].content
    assert "filesystem (command): Local file access" in registry.last_request.messages[-1].content
    assert (20, "mcp_context", "MCP context added", "1 MCP server(s) available") in traces.events


def test_internet_enabled_agent_without_web_search_skill_skips_search():
    traces = FakeTraceStore()
    registry = FakeProviderRegistry()
    skills = FakeSkillRegistry()
    runtime = WorkflowRuntime(provider_registry=registry, trace_store=traces, skill_registry=skills)
    agent = AgentSpec(
        id=6,
        name="Restricted Search Agent",
        system_prompt="Research carefully.",
        provider_type="fake",
        provider_base_url=None,
        provider_api_key_env=None,
        model="model-a",
        temperature=0.1,
        internet_enabled=True,
        multimodal_enabled=False,
        allowed_skills=[],
    )

    list(
        runtime.stream_workflow(
            agent_run_id=19,
            workflow=WorkflowSpec(id=12, name="Restricted Search", workflow_type="single_agent", agents=[agent]),
            messages=[ChatMessage(role="user", content="search for multi agent orchestration patterns")],
        )
    )

    assert skills.calls == []
    assert (19, "tool_skipped", "web_search skipped", "Skill is not assigned to this agent.") in traces.events
    assert traces.tool_calls == [(19, "web_search", "search for multi agent orchestration patterns", "Skill is not assigned to this agent.", "failed")]


def test_single_agent_workflow_streams_response_and_completes_run():
    traces = FakeTraceStore()
    runtime = WorkflowRuntime(provider_registry=FakeProviderRegistry(), trace_store=traces)

    result = "".join(
        runtime.stream_workflow(
            agent_run_id=42,
            workflow=WorkflowSpec(id=1, name="Single", workflow_type="single_agent", agents=[make_agent("Assistant")]),
            messages=[ChatMessage(role="user", content="hello")],
        )
    )

    assert result == "fake:model-a:hello"
    assert traces.completed == [(42, "fake:model-a:hello")]
    assert (42, "workflow_started", "Workflow started", "Single") in traces.events
    assert (42, "agent_completed", "Assistant completed", "fake:model-a:hello") in traces.events


def test_sequential_workflow_feeds_previous_agent_output_to_next_agent():
    traces = FakeTraceStore()
    runtime = WorkflowRuntime(provider_registry=FakeProviderRegistry(), trace_store=traces)

    result = "".join(
        runtime.stream_workflow(
            agent_run_id=7,
            workflow=WorkflowSpec(
                id=2,
                name="Sequential",
                workflow_type="sequential",
                agents=[make_agent("Researcher"), make_agent("Writer")],
            ),
            messages=[ChatMessage(role="user", content="topic")],
        )
    )

    assert result == "fake:model-a:fake:model-a:topic"
    assert traces.completed == [(7, "fake:model-a:fake:model-a:topic")]
    assert [event[2] for event in traces.events if event[1] == "agent_started"] == ["Researcher started", "Writer started"]


def test_reviewer_workflow_runs_answer_agent_then_reviewer_agent():
    traces = FakeTraceStore()
    runtime = WorkflowRuntime(provider_registry=FakeProviderRegistry(), trace_store=traces)

    result = "".join(
        runtime.stream_workflow(
            agent_run_id=9,
            workflow=WorkflowSpec(
                id=3,
                name="Reviewer",
                workflow_type="reviewer",
                agents=[make_agent("Writer"), make_agent("Critic")],
            ),
            messages=[ChatMessage(role="user", content="draft this")],
        )
    )

    assert result == "fake:model-a:Review and improve this answer:\n\nfake:model-a:draft this"
    assert [event[2] for event in traces.events if event[1] == "agent_started"] == ["Writer started", "Critic started"]


def test_supervisor_workflow_runs_supervisor_then_worker_agents_with_plan_context():
    traces = FakeTraceStore()
    registry = FakeProviderRegistry()
    runtime = WorkflowRuntime(provider_registry=registry, trace_store=traces)

    result = "".join(
        runtime.stream_workflow(
            agent_run_id=15,
            workflow=WorkflowSpec(
                id=8,
                name="Supervisor",
                workflow_type="supervisor",
                agents=[make_agent("Supervisor"), make_agent("Researcher"), make_agent("Writer")],
            ),
            messages=[ChatMessage(role="user", content="plan launch")],
        )
    )

    assert result.startswith("fake:model-a:fake:model-a:Supervisor plan:")
    assert (15, "supervisor_plan", "Supervisor plan created", "fake:model-a:plan launch") in traces.events
    assert [event[2] for event in traces.events if event[1] == "agent_started"] == ["Supervisor started", "Researcher started", "Writer started"]


def test_parallel_workflow_runs_agents_against_original_prompt_and_combines_outputs():
    traces = FakeTraceStore()
    registry = FakeProviderRegistry()
    runtime = WorkflowRuntime(provider_registry=registry, trace_store=traces)

    result = "".join(
        runtime.stream_workflow(
            agent_run_id=16,
            workflow=WorkflowSpec(
                id=9,
                name="Parallel",
                workflow_type="parallel",
                agents=[make_agent("Researcher"), make_agent("Writer")],
            ),
            messages=[ChatMessage(role="user", content="compare options")],
        )
    )

    assert result == "Researcher:\nfake:model-a:compare options\n\nWriter:\nfake:model-a:compare options"
    assert (16, "workflow_parallel", "Parallel agents completed", "2 agents") in traces.events


def test_debate_workflow_collects_positions_then_final_agent_resolves():
    traces = FakeTraceStore()
    registry = FakeProviderRegistry()
    runtime = WorkflowRuntime(provider_registry=registry, trace_store=traces)

    result = "".join(
        runtime.stream_workflow(
            agent_run_id=17,
            workflow=WorkflowSpec(
                id=10,
                name="Debate",
                workflow_type="debate",
                agents=[make_agent("Pro"), make_agent("Con"), make_agent("Judge")],
            ),
            messages=[ChatMessage(role="user", content="choose architecture")],
        )
    )

    assert result.startswith("fake:model-a:Resolve this debate")
    assert "Pro:\nfake:model-a:choose architecture" in registry.last_request.messages[-1].content
    assert "Con:\nfake:model-a:choose architecture" in registry.last_request.messages[-1].content
    assert (17, "workflow_debate", "Debate positions collected", "2 positions") in traces.events


def test_workflow_runtime_rejects_workflow_without_agents():
    traces = FakeTraceStore()
    runtime = WorkflowRuntime(provider_registry=FakeProviderRegistry(), trace_store=traces)

    try:
        list(
            runtime.stream_workflow(
                agent_run_id=5,
                workflow=WorkflowSpec(id=4, name="Broken", workflow_type="single_agent", agents=[]),
                messages=[ChatMessage(role="user", content="hello")],
            )
        )
    except ValueError as error:
        assert str(error) == "Workflow requires at least one agent."
    else:
        raise AssertionError("Expected ValueError")
