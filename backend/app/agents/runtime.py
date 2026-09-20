from collections.abc import Iterator

from ..providers import ChatMessage, ChatRequest, ProviderRegistry
from ..traces.store import TraceStore


DEFAULT_MODEL = "nvidia/nemotron-3-super-120b-a12b:free"


class AgentRuntime:
    def __init__(self, provider_registry: ProviderRegistry | None = None, trace_store: TraceStore | None = None):
        self.provider_registry = provider_registry or ProviderRegistry()
        self.trace_store = trace_store or TraceStore()

    def stream_default_agent(self, agent_run_id: int, messages: list[ChatMessage]) -> Iterator[str]:
        self.trace_store.add_event(agent_run_id, "agent_started", "Default Assistant started")

        request = ChatRequest(
            model=DEFAULT_MODEL,
            messages=messages[-20:],
            temperature=0.7,
        )

        self.trace_store.add_event(agent_run_id, "provider_started", "OpenRouter streaming started", DEFAULT_MODEL)

        complete_response = ""
        try:
            for token in self.provider_registry.stream_chat("openrouter", request):
                complete_response += token
                yield token
        except Exception as error:
            self.trace_store.add_event(agent_run_id, "agent_failed", "Default Assistant failed", repr(error))
            self.trace_store.fail_run(agent_run_id, str(error))
            raise

        self.trace_store.add_event(agent_run_id, "agent_completed", "Default Assistant completed")
        self.trace_store.complete_run(agent_run_id, complete_response)
