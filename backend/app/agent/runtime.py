"""Iterative agent loop: plan -> act -> observe until a final answer."""

import http.client
import json
import re
import socket
import threading
import time
from collections.abc import Callable, Iterator
from dataclasses import replace
from urllib.error import HTTPError, URLError

from ..providers import ChatMessage, ChatRequest, ProviderRegistry
from ..traces.store import TraceStore
from .errors import ApprovalRequiredError, RunCancelledError
from .guardrails import GuardrailConfig, Guardrails, GuardrailViolation
from .protocol import PROTOCOL_INSTRUCTIONS, parse_model_output
from .tools.base import ToolResult, ToolSpec

CONNECTION_RETRY_DELAYS = [2, 6]

# Misbehaving LLM gateways return these non-deterministically for valid requests
# (verified: same key/payload gets 200, then 401/502 seconds apart). One cheap
# retry absorbs the hiccup; genuinely broken auth just fails ~8s later.
# 400 included because model POOLS (aliases) route per-request: a member-specific
# "model not available" bad_request is transient — the next attempt lands elsewhere.
TRANSIENT_PROVIDER_STATUS_CODES = {400, 401, 408, 425, 429, 500, 502, 503, 504}


def is_connection_error(error: Exception) -> bool:
    """Connection-level failures worth retrying (the server never answered)."""
    if isinstance(error, HTTPError):
        return False
    if isinstance(error, (ConnectionError, TimeoutError, socket.timeout, socket.gaierror, URLError, http.client.HTTPException)):
        return True
    # Provider SDKs (openai, anthropic) expose dedicated connection error types.
    return type(error).__name__ in {"APIConnectionError", "APIConnectionTimeoutError"} or "connection" in repr(error).lower()


def is_transient_provider_error(error: Exception) -> bool:
    """Provider-level status failures worth retrying (flaky gateway responses)."""
    status = getattr(error, "status_code", None)
    if status is None:
        match = re.search(r"\[(\d{3})\]", repr(error))
        status = int(match.group(1)) if match else None
    return status in TRANSIENT_PROVIDER_STATUS_CODES


def _resolve_tool_name(name: str, known_tools: set[str]) -> str | None:
    """Exact match, then case-insensitive, then a unique suffix match. Smaller models
    often shorten long tool names (mcp_google_flow_flow_upload_file -> flow_upload_file);
    a unique suffix resolves unambiguously."""
    if name in known_tools:
        return name
    lowered = {tool.lower(): tool for tool in known_tools}
    if name.lower() in lowered:
        return lowered[name.lower()]
    suffix_matches = [tool for tool in known_tools if tool.lower().endswith(f"_{name.lower()}")]
    if len(suffix_matches) == 1:
        return suffix_matches[0]
    return None


def build_tool_catalog(entries: list[tuple[str, str, str]]) -> list[ToolSpec]:
    return [ToolSpec(name=name, description=description, parameters="", permission=permission) for name, description, permission in entries]


def build_system_prompt(base_prompt: str, tool_specs: list[ToolSpec]) -> str:
    lines = [
        base_prompt,
        "",
        "Idioma: responde SIEMPRE en el idioma en el que escribe el usuario (si escribe en espanol, responde en espanol). "
        "Esto aplica tambien a los resumenes de resultados de herramientas: nunca traduzcas URLs ni nombres tecnicos.",
        "",
        "Honestidad de datos: todo dato que presentes como resultado de una herramienta debe venir literalmente de un "
        "TOOL RESULT del contexto. Si la herramienta fallo, devolvio vacio o no cubre lo pedido, di lo que paso con el "
        "error real y propone el siguiente paso. NUNCA inventes, completes ni estimes nombres, direcciones, telefonos, "
        "emails, URLs, valoraciones ni cifras: presentar datos inventados como resultados reales es el fallo mas grave posible.",
    ]
    if not tool_specs:
        return "\n".join(lines)
    lines.append("")
    lines.append("# Available tools")
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
        guardrail_config: GuardrailConfig | None = None,
        on_before_tool: Callable[[str, dict, list[ChatMessage]], None] | None = None,
        fallbacks: list | None = None,
        should_continue: Callable[[], bool] | None = None,
        on_activity: Callable[[dict], None] | None = None,
        provider_api_key: str | None = None,
    ) -> Iterator[str]:
        config = guardrail_config or GuardrailConfig()
        if max_iterations:
            config = replace(config, max_iterations=max_iterations)
        guardrails = Guardrails(config)
        known_tools = {spec.name for spec in tool_specs}
        system = build_system_prompt(system_prompt, tool_specs)
        conversation = list(messages)
        parse_retries = 0
        empty_answer_retries = 0
        self._on_activity = on_activity
        self._cumulative_chars = 0
        self._thought_flush_at = 0.0

        while True:
            if should_continue is not None and not should_continue():
                raise RunCancelledError()
            try:
                guardrails.check_before_iteration()
            except GuardrailViolation as error:
                yield f"\n\n[ObsyGPT] {error}"
                return

            reasoning_buffer: list[str] = []

            def reasoning_sink(text: str) -> None:
                """Live reasoning stream (ChatGPT/Claude style): accumulates the
                model's thinking and flushes it (tail) at most every 0.4s."""
                import time as _time

                reasoning_buffer.append(text)
                now = _time.monotonic()
                if now - self._thought_flush_at < 0.4:
                    return
                self._thought_flush_at = now
                self._emit_activity({"kind": "thought", "text": "".join(reasoning_buffer)[-1500:], "iteration": guardrails.iterations})

            request = ChatRequest(
                model=model,
                messages=[ChatMessage(role="system", content=system), *conversation[-20:]],
                temperature=temperature,
                reasoning_sink=reasoning_sink,
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
                        api_key=provider_api_key,
                    )
                )

            # Heartbeat: even when nothing streams (long prefill, non-reasoning
            # stretches, retries), the UI gets a signal every 10s so the run
            # never looks frozen while it is working.
            heartbeat_stop = threading.Event()

            def _heartbeat() -> None:
                while not heartbeat_stop.wait(10.0):
                    self._emit_activity({"kind": "heartbeat", "iteration": guardrails.iterations})

            heartbeat_thread = threading.Thread(target=_heartbeat, daemon=True)
            heartbeat_thread.start()
            try:
                response = self._call_with_fallbacks(agent_run_id, request, call_primary, fallbacks)
            finally:
                heartbeat_stop.set()
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
                final_text = parsed.thought
                if not final_text.strip():
                    # Reasoning models served by llama.cpp (e.g. Gemma with a
                    # reasoning budget) can end the turn with everything inside
                    # reasoning_content and an empty visible answer. Retry once
                    # asking for a direct answer; if it stays empty, fall back
                    # to the tail of the reasoning so the user is never left
                    # with silence.
                    empty_answer_retries += 1
                    if empty_answer_retries <= 1:
                        self.trace_store.add_event(agent_run_id, "empty_answer_retry", "Empty visible answer, retrying")
                        conversation.append(ChatMessage(role="assistant", content=response or "(empty response)"))
                        conversation.append(
                            ChatMessage(
                                role="user",
                                content=(
                                    "Your previous response had no visible content (it was likely all internal "
                                    "reasoning). Reply to the user now with the final answer directly, in plain "
                                    "text, without tool blocks and without hiding it inside your reasoning."
                                ),
                            )
                        )
                        continue
                    reasoning_tail = "".join(reasoning_buffer).strip()
                    final_text = (
                        f"(El modelo respondió solo con razonamiento interno; este es el final de su razonamiento):\n{reasoning_tail[-1200:]}"
                        if reasoning_tail
                        else "(El modelo devolvió una respuesta vacía. Reintenta la tarea.)"
                    )
                self.trace_store.add_event(agent_run_id, "agent_completed", "Agent completed", final_text[:500])
                yield final_text
                return

            for tool_call in calls:
                try:
                    guardrails.check_tool_call(tool_call.name, tool_call.args)
                except GuardrailViolation as error:
                    yield f"\n\n[ObsyGPT] {error}"
                    return

            if parsed.thought:
                # Reasoning stays OUT of the answer text (ChatGPT/Claude style):
                # it travels through the activity channel and the UI renders it
                # as a gray "thinking" line. Only final responses are yielded.
                self._emit_activity({"kind": "thought", "text": parsed.thought[:2000], "iteration": guardrails.iterations})

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
                retryable = is_connection_error(error) or is_transient_provider_error(error)
                if attempt < len(CONNECTION_RETRY_DELAYS) and retryable:
                    delay = CONNECTION_RETRY_DELAYS[attempt]
                    self.trace_store.add_event(
                        agent_run_id,
                        "provider_retry",
                        f"Provider retry {attempt + 1}/{len(CONNECTION_RETRY_DELAYS)} in {delay}s",
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
                            api_key=getattr(fallback, "provider_api_key", None),
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
            resolved = _resolve_tool_name(name, known_tools)
            if resolved is not None:
                self.trace_store.add_event(agent_run_id, "tool_resolved", f"{name} -> {resolved}")
                name = resolved
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
