"""Iterative agent loop: plan -> act -> observe until a final answer."""

import json
import time
from collections.abc import Callable, Iterator

from ..providers import ChatMessage, ChatRequest, ProviderRegistry
from ..traces.store import TraceStore
from .errors import ApprovalRequiredError, RunCancelledError
from .guardrails import GuardrailConfig, Guardrails, GuardrailViolation
from .protocol import PROTOCOL_INSTRUCTIONS, parse_model_output
from .tools.base import ToolResult, ToolSpec

CONNECTION_RETRY_DELAYS = [2, 6]


def is_connection_error(error: Exception) -> bool:
    return "connection" in repr(error).lower() or type(error).__name__ == "APIConnectionError"


def build_tool_catalog(entries: list[tuple[str, str, str]]) -> list[ToolSpec]:
    return [ToolSpec(name=name, description=description, parameters="", permission=permission) for name, description, permission in entries]


def build_system_prompt(base_prompt: str, tool_specs: list[ToolSpec]) -> str:
    if not tool_specs:
        return base_prompt
    lines = [base_prompt, "", "# Available tools"]
    for spec in tool_specs:
        params = f' args: {spec.parameters}' if spec.parameters else ""
        lines.append(f"- {spec.name} ({spec.permission}): {spec.description}{params}")
    if any(spec.name == "dispatch_subagents" for spec in tool_specs):
        lines.append("")
        lines.append(
            "Cuando el usuario pida algo que encaje con otro agente (revisiones, analisis, borradores), "
            "delega con dispatch_subagents en vez de hacerlo tu mismo."
        )
    lines.append("")
    lines.append(PROTOCOL_INSTRUCTIONS)
    return "\n".join(lines)


class _NoopTraceStore:
    def add_event(self, *args, **kwargs) -> None:
        pass

    def add_tool_call(self, *args, **kwargs) -> None:
        pass


def _default_execute_tool(name: str, args: dict) -> ToolResult:
    return ToolResult(ok=False, output=f"Unknown tool: {name}")


class AgentLoop:
    def __init__(
        self,
        provider_registry: ProviderRegistry | None = None,
        trace_store: TraceStore | None = None,
        execute_tool: Callable[[str, dict], ToolResult] | None = None,
    ):
        self.provider_registry = provider_registry or ProviderRegistry()
        self.trace_store = trace_store or _NoopTraceStore()
        self.execute_tool = execute_tool or _default_execute_tool
        self._on_activity: Callable[[dict], None] | None = None
        self._cumulative_chars = 0

    def _emit_activity(self, payload: dict) -> None:
        if self._on_activity is not None:
            try:
                self._on_activity(payload)
            except Exception:  # noqa: BLE001 - activity reporting must never break the loop
                pass

    def run(  # noqa: PLR0913
        self,
        agent_run_id: int,
        system_prompt: str,
        provider_type: str,
        provider_base_url: str | None,
        provider_api_key_env: str | None,
        model: str,
        temperature: float,
        tool_specs: list[ToolSpec],
        messages: list[ChatMessage],
        max_iterations: int | None = None,
        on_before_tool: Callable[[str, dict, list[ChatMessage]], None] | None = None,
        fallbacks: list | None = None,
        should_continue: Callable[[], bool] | None = None,
        on_activity: Callable[[dict], None] | None = None,
    ) -> Iterator[str]:
        config = GuardrailConfig(max_iterations=max_iterations) if max_iterations else GuardrailConfig()
        guardrails = Guardrails(config)
        known_tools = {spec.name for spec in tool_specs}
        system = build_system_prompt(system_prompt, tool_specs)
        conversation = list(messages)
        parse_retries = 0
        self._on_activity = on_activity
        self._cumulative_chars = 0

        while True:
            if should_continue is not None and not should_continue():
                raise RunCancelledError()
            try:
                guardrails.check_before_iteration()
            except GuardrailViolation as error:
                yield f"\n\n[ObsyGPT] {error}"
                return

            request = ChatRequest(
                model=model,
                messages=[ChatMessage(role="system", content=system), *conversation[-20:]],
                temperature=temperature,
            )
            self.trace_store.add_event(agent_run_id, "agent_started", f"Iteration {guardrails.iterations} started")
            self._emit_activity({"kind": "iteration", "iteration": guardrails.iterations})
            self._emit_activity({"kind": "thinking", "iteration": guardrails.iterations})

            def call_primary() -> str:
                return "".join(
                    self.provider_registry.stream_chat_with_config(
                        provider_type,
                        request,
                        api_key_env=provider_api_key_env,
                        base_url=provider_base_url,
                    )
                )

            response = self._call_with_fallbacks(agent_run_id, request, call_primary, fallbacks)
            self._cumulative_chars += len(response)
            self._emit_activity({"kind": "response", "iteration": guardrails.iterations, "chars": self._cumulative_chars})
            parsed = parse_model_output(response)

            if parsed.parse_error:
                parse_retries += 1
                self._emit_activity({"kind": "repair", "iteration": guardrails.iterations})
                if parse_retries >= 3:
                    yield (
                        "\n\n[ObsyGPT] No se pudo emitir una llamada a herramienta con JSON valido tras varios intentos. "
                        "Responde directamente al usuario sin usar herramientas."
                    )
                    return
                conversation.append(ChatMessage(role="assistant", content=response))
                conversation.append(
                    ChatMessage(
                        role="user",
                        content=(
                            f"TOOL ERROR: {parsed.parse_error} Fix the JSON format and emit the tool block again, "
                            "or answer directly without tools. Tip: keep argument values short and never embed code, "
                            "HTML, or long documents inside the JSON."
                        ),
                    )
                )
                continue

            calls = parsed.calls()
            if not calls:
                self.trace_store.add_event(agent_run_id, "agent_completed", "Agent completed", parsed.thought[:500])
                yield parsed.thought
                return

            for tool_call in calls:
                try:
                    guardrails.check_tool_call(tool_call.name, tool_call.args)
                except GuardrailViolation as error:
                    yield f"\n\n[ObsyGPT] {error}"
                    return

            if parsed.thought:
                yield parsed.thought + "\n"

            conversation.append(ChatMessage(role="assistant", content=response))
            for tool_call in calls:
                if on_before_tool:
                    on_before_tool(tool_call.name, tool_call.args, conversation)
                self._emit_activity({"kind": "tool", "phase": "start", "name": tool_call.name, "iteration": guardrails.iterations})
                try:
                    observation = self._execute_tool(agent_run_id, guardrails, tool_call.name, tool_call.args, known_tools)
                except GuardrailViolation as error:
                    yield f"\n\n[ObsyGPT] {error}"
                    return
                self._emit_activity({"kind": "tool", "phase": "done", "name": tool_call.name, "iteration": guardrails.iterations})
                conversation.append(ChatMessage(role="user", content=observation))

    def _call_primary_with_retries(self, agent_run_id: int, call_primary) -> str:  # noqa: ANN001
        for attempt in range(len(CONNECTION_RETRY_DELAYS) + 1):
            try:
                return call_primary()
            except Exception as error:  # noqa: BLE001
                if attempt < len(CONNECTION_RETRY_DELAYS) and is_connection_error(error):
                    delay = CONNECTION_RETRY_DELAYS[attempt]
                    self.trace_store.add_event(
                        agent_run_id,
                        "provider_retry",
                        f"Connection retry {attempt + 1}/{len(CONNECTION_RETRY_DELAYS)} in {delay}s",
                        repr(error)[:200],
                    )
                    self._emit_activity({"kind": "retry", "detail": f"reintento {attempt + 1}/{len(CONNECTION_RETRY_DELAYS)} en {delay}s"})
                    time.sleep(delay)
                    continue
                raise
        raise RuntimeError("unreachable")

    def _call_with_fallbacks(self, agent_run_id: int, request: ChatRequest, call_primary, fallbacks: list | None) -> str:  # noqa: ANN001
        try:
            return self._call_primary_with_retries(agent_run_id, call_primary)
        except Exception as primary_error:  # noqa: BLE001
            from ..monitoring import otel

            otel.record_api_error(request.model, repr(primary_error), stage="primary")
            for fallback in fallbacks or []:
                try:
                    self.trace_store.add_event(
                        agent_run_id,
                        "provider_fallback",
                        f"Fallback to {fallback.model}",
                        f"Primary failed: {repr(primary_error)[:200]}",
                    )
                    self._emit_activity({"kind": "fallback", "detail": f"cambio a modelo de respaldo: {fallback.model}"})
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

    def _execute_tool(
        self,
        agent_run_id: int,
        guardrails: Guardrails,
        name: str,
        args: dict,
        known_tools: set[str],
    ) -> str:
        args_summary = json.dumps(args, default=str)[:400]

        def finish(output: str, ok: bool) -> str:
            clipped = guardrails.clip_output(output)
            guardrails.add_output_chars(len(clipped))
            self._record_tool(agent_run_id, name, args_summary, clipped, "completed" if ok else "failed")
            return f"TOOL RESULT ({name}):\n{clipped}"

        if name not in known_tools:
            self.trace_store.add_event(agent_run_id, "tool_skipped", f"{name} skipped", "Tool is not available for this agent.")
            return finish(f"Unknown tool: {name}. Available tools: {', '.join(sorted(known_tools))}.", ok=False)

        self.trace_store.add_event(agent_run_id, "tool_started", f"{name} started", args_summary)
        try:
            result = self.execute_tool(name, args)
        except ApprovalRequiredError:
            raise
        except Exception as error:  # noqa: BLE001
            self.trace_store.add_event(agent_run_id, "tool_failed", f"{name} failed", repr(error))
            return finish(f"Tool execution error: {error}", ok=False)

        self.trace_store.add_event(agent_run_id, "tool_completed", f"{name} completed", args_summary)
        return finish(result.output, ok=result.ok)

    def _record_tool(self, agent_run_id: int, name: str, input_summary: str, output_summary: str, status: str) -> None:
        from ..monitoring import otel

        self.trace_store.add_tool_call(agent_run_id, name, input_summary, output_summary[:1000], status)
        otel.record_tool_result(agent_run_id, name, status, output_summary)
