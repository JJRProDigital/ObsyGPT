"""Agentic chat streaming: drives the AgentLoop behind a text/plain SSE-like stream."""

import logging
from collections.abc import Generator, Iterator

from fastapi import HTTPException
from fastapi.responses import StreamingResponse

from ..agent.errors import ApprovalRequiredError
from ..agent.runtime import AgentLoop
from ..agent.settings import load_guardrail_config
from ..agent.subagents import DispatchSubagentsTool
from ..memory.context import build_memory_context, build_user_instructions_block
from ..memory.learning import learn_habits_in_background
from ..monitoring import otel
from ..providers import ChatMessage
from ..traces.store import TraceStore
from . import activity as chat_activity
from . import approvals as chat_approvals
from . import attachments as chat_attachments
from . import conversations as chat_conversations
from . import specs as chat_specs


logger = logging.getLogger("obsygpt.chat.streaming")


def stream_agentic(
    user_id: int,
    conversation_id: int,
    agent_run_id: int,
    agent,
    provider_messages: list[ChatMessage],
    trace_store: TraceStore,
    project_folder: str | None = None,
    user_message: str = "",
) -> StreamingResponse:
    registry = chat_specs.build_agent_tool_registry(user_id=user_id, workspace_root=project_folder, agent_id=agent.id)
    registry.register(DispatchSubagentsTool(user_id, agent_run_id, project_folder, conversation_id, trace_store, context_message=user_message))
    tool_specs = chat_specs.get_agent_tool_specs(agent.id, user_id=user_id, workspace_root=project_folder)
    executor = chat_approvals.build_approval_aware_executor(user_id, conversation_id, agent_run_id, registry)

    def on_before_tool(name: str, args: dict, conversation: list[ChatMessage]) -> None:
        from ..agent.store import save_run_state

        save_run_state(agent_run_id, conversation, iterations=0, tool_call_count=0, thought_text="")

    otel.bind_context(**{"user.id": user_id, "session.id": conversation_id, "prompt.id": agent_run_id})
    otel.record_user_prompt(len(user_message), user_message)

    def generate() -> Generator[str, None, None]:
        complete_response = ""
        loop = AgentLoop(trace_store=trace_store, execute_tool=executor)

        def start_loop(on_activity) -> Iterator[str]:  # noqa: ANN001
            return loop.run(
                agent_run_id=agent_run_id,
                system_prompt=agent.system_prompt,
                provider_type=agent.provider_type,
                provider_base_url=agent.provider_base_url,
                provider_api_key_env=agent.provider_api_key_env,
                model=agent.model,
                temperature=agent.temperature,
                tool_specs=tool_specs,
                messages=provider_messages,
                guardrail_config=load_guardrail_config(),
                on_before_tool=on_before_tool,
                fallbacks=agent.fallbacks,
                on_activity=on_activity,
            )

        outcome: tuple[str, object] | None = None
        try:
            for kind, payload in chat_activity.drive_agent_loop(start_loop):
                if kind == "token":
                    complete_response += str(payload)
                    yield str(payload)
                elif kind == "activity":
                    yield chat_activity.frame_activity(payload)  # type: ignore[arg-type]
                elif kind == "done":
                    break
                else:
                    outcome = (kind, payload)
                    break

            if outcome is not None and outcome[0] == "approval":
                error = outcome[1]
                notice = (
                    f"\n\n[ObsyGPT] Aprobacion requerida para ejecutar `{error.tool_name}` "
                    f"(aprobacion #{error.approval_id}). Acepta o rechaza la ejecucion para continuar."
                )
                complete_response += notice
                yield notice
                if complete_response.strip():
                    chat_conversations.save_message(conversation_id, "assistant", complete_response)
                trace_store.pause_run(agent_run_id, notice)
                return

            if outcome is not None:  # error
                raise outcome[1]  # type: ignore[misc]

            if complete_response:
                chat_conversations.save_message(conversation_id, "assistant", complete_response)
                trace_store.complete_run(agent_run_id, complete_response)
                otel.record_assistant_response(agent.model or "unknown", len(complete_response), complete_response)
                if user_message:
                    learn_habits_in_background(user_id, conversation_id, agent, user_message, complete_response)
        except Exception as error:
            logger.error("Agentic loop error: %s", repr(error))
            yield "\n\nObsyGPT could not complete the response."
            trace_store.fail_run(agent_run_id, str(error))

    return StreamingResponse(
        generate(),
        media_type="text/plain",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )
