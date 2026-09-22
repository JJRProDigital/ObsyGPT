"""Approval endpoints: resume an agent run after the user decides on a tool call."""

import json
import logging
from collections.abc import Generator, Iterator

from fastapi import APIRouter, HTTPException, Request
from fastapi.responses import StreamingResponse

from ..agent.errors import ApprovalRequiredError
from ..agent.runtime import AgentLoop
from ..agent.settings import load_guardrail_config
from ..agent import store as agent_store
from ..auth import routes as auth
from ..providers import ChatMessage
from ..traces.store import TraceStore
from ..workspace import routes as workspace_routes
from . import activity as chat_activity
from . import conversations as chat_conversations
from . import specs as chat_specs


logger = logging.getLogger("obsygpt.chat.approvals")

router = APIRouter()


def _safe_json(value: str) -> dict:
    try:
        parsed = json.loads(value)
        return parsed if isinstance(parsed, dict) else {}
    except json.JSONDecodeError:
        return {}


def build_approval_aware_executor(user_id: int, conversation_id: int, agent_run_id: int, registry):
    preferences = workspace_routes.get_user_preferences(user_id)
    policies = preferences.get("tool_policies") or {}
    from .. import db as app_db

    def _already_failed_identically(name: str, args: dict) -> int:
        """Counts prior approved attempts of this exact call that ran (the run
        re-asked for the same call afterwards). Guard against approval loops:
        a model retrying an identical failing call would re-ask forever."""
        try:
            with app_db.connect() as connection:
                with connection.cursor() as cursor:
                    cursor.execute(
                        """
                        SELECT COUNT(*) AS prior
                        FROM tool_approvals
                        WHERE agent_run_id = %s AND tool_name = %s AND args::jsonb = %s::jsonb AND status = 'approved';
                        """,
                        (agent_run_id, name, json.dumps(args, ensure_ascii=False, default=str)),
                    )
                    return int(cursor.fetchone()[0])
        except Exception:  # noqa: BLE001 - guard must never break execution
            return 0

    def execute(name: str, args: dict):
        spec = registry.get(name).spec
        default_policy = "ask" if spec.permission == "sensitive" else "allow"
        policy = policies.get(name, default_policy)
        if policy == "block":
            from ..agent.tools.base import ToolResult

            return ToolResult(ok=False, output=f"Tool '{name}' is blocked by your security policy (Ajustes > Seguridad).")
        if spec.permission == "sensitive" and policy == "ask":
            from ..agent.tools.base import ToolResult

            prior = _already_failed_identically(name, args)
            if prior >= 2:
                return ToolResult(
                    ok=False,
                    output=(
                        f"Tool '{name}' was already approved and attempted {prior} times with these exact arguments "
                        "and the run came back to ask again. Do NOT call it again with the same arguments: "
                        "analyze the previous result, change the approach, or ask the user for instructions."
                    ),
                )
            approval_id = agent_store.create_tool_approval(agent_run_id, user_id, conversation_id, name, args)
            raise ApprovalRequiredError(approval_id=approval_id, tool_name=name, args=args)
        return registry.run(name, args)

    return execute


@router.get("/approvals/pending")
def pending_approvals(conversation_id: int, request: Request):
    user_id = auth.require_user(request)
    conversation = chat_conversations.get_conversation(conversation_id, user_id)
    if not conversation:
        raise HTTPException(status_code=404, detail="Conversation not found.")
    approvals = [
        {
            "id": approval["id"],
            "agent_run_id": approval["agent_run_id"],
            "conversation_id": approval["conversation_id"],
            "tool_name": approval["tool_name"],
            "args": approval["args"] if not isinstance(approval["args"], str) else _safe_json(approval["args"]),
            "created_at": chat_conversations.serialize_datetime(approval["created_at"]),
        }
        for approval in agent_store.list_pending_approvals(user_id, conversation_id)
    ]
    return {"approvals": approvals}


@router.post("/approvals/{approval_id}/approve")
def approve_tool(approval_id: int, request: Request):
    return _resume_with_approval(approval_id, request, approved=True)


@router.post("/approvals/{approval_id}/deny")
def deny_tool(approval_id: int, request: Request):
    return _resume_with_approval(approval_id, request, approved=False)


def _resume_with_approval(approval_id: int, request: Request, approved: bool) -> StreamingResponse:
    user_id = auth.require_user(request)
    approval = agent_store.decide_approval(approval_id, user_id, "approved" if approved else "denied")
    if not approval:
        raise HTTPException(status_code=404, detail="Approval not found or already decided.")

    run_config = agent_store.get_run_config(approval["agent_run_id"])
    state = agent_store.load_run_state(approval["agent_run_id"])
    if not run_config or not state:
        raise HTTPException(status_code=404, detail="Run state not found for this approval.")

    conversation_id = approval["conversation_id"]
    run_id = approval["agent_run_id"]
    conversation_messages = [
        ChatMessage(role=item.get("role", "user"), content=item.get("content", ""))
        for item in state.get("messages", [])
        if isinstance(item, dict)
    ]

    run_workspace = chat_specs.workspace_root_for_run(run_config)
    registry = chat_specs.build_agent_tool_registry(user_id=user_id, workspace_root=run_workspace, agent_id=run_config.get("agent_id"))
    permissions = agent_store.get_agent_tool_permissions(run_config.get("agent_id"))
    trace_store = TraceStore()
    from ..agent.subagents import DISPATCH_SPEC, DispatchSubagentsTool

    if permissions.get(DISPATCH_SPEC.name) and not any(spec.name == DISPATCH_SPEC.name for spec in registry.list_specs()):
        from ..agent.subagents import context_for_parent_run

        registry.register(DispatchSubagentsTool(user_id, run_id, run_workspace, conversation_id, trace_store, context_message=context_for_parent_run(run_id, state)))
    tool_specs = [spec for spec in registry.list_specs() if permissions.get(spec.name, False)]
    executor = build_approval_aware_executor(user_id, conversation_id, run_id, registry)

    tool_name = approval["tool_name"]
    tool_args = approval["args"] if isinstance(approval["args"], dict) else _safe_json(str(approval["args"]))

    paused_child_error = None
    if approved:
        try:
            result = registry.get(tool_name).run(tool_args)
            observation = f"TOOL RESULT ({tool_name}):\n{result.output[:10000]}"
        except ApprovalRequiredError as child_error:
            paused_child_error = child_error
            observation = None
        except Exception as error:  # noqa: BLE001 - tool crash must not leave a zombie run: report it to the model
            trace_store.add_event(run_id, "tool_failed", f"{tool_name} failed after approval", repr(error)[:500])
            observation = (
                f"TOOL RESULT ({tool_name}):\nThe approved tool call FAILED to execute: {error}. "
                "Explain the problem to the user and propose an alternative."
            )
    else:
        observation = (
            f"TOOL RESULT ({tool_name}):\nUser denied execution of this tool. "
            "Explain the limitation to the user and propose an alternative that does not require it."
        )

    if paused_child_error is not None:
        notice = (
            f"\n\n[ObsyGPT] El sub-agente requiere aprobacion para `{paused_child_error.tool_name}` "
            f"(aprobacion #{paused_child_error.approval_id}). Acepta o rechaza para continuar."
        )

        def paused_generate() -> Generator[str, None, None]:
            yield notice
            if conversation_id:
                chat_conversations.save_message(conversation_id, "assistant", notice)
            trace_store.pause_run(run_id, notice)

        return StreamingResponse(
            paused_generate(),
            media_type="text/plain",
            headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
        )

    resume_messages = [*conversation_messages, ChatMessage(role="user", content=observation)]

    def generate() -> Generator[str, None, None]:
        agent_store.set_run_status(run_id, "running")
        complete_response = ""
        loop = AgentLoop(trace_store=trace_store, execute_tool=executor)

        def start_loop(on_activity) -> Iterator[str]:  # noqa: ANN001
            return loop.run(
                agent_run_id=run_id,
                system_prompt=run_config["system_prompt"],
                provider_type=run_config["provider_type"],
                provider_base_url=run_config["base_url"],
                provider_api_key_env=run_config["api_key_env"],
                model=run_config["model_name"],
                temperature=float(run_config["temperature"]),
                tool_specs=tool_specs,
                messages=resume_messages,
                guardrail_config=load_guardrail_config(),
                on_before_tool=lambda name, args, conversation: agent_store.save_run_state(run_id, conversation, iterations=0, tool_call_count=0, thought_text=""),
                fallbacks=chat_specs.get_agent_fallbacks(run_config.get("agent_id")),
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
                trace_store.pause_run(run_id, notice)
                from ..agent.subagents import update_dispatch

                update_dispatch(run_id, "awaiting_approval")
                return

            if outcome is not None:
                raise outcome[1]  # type: ignore[misc]

            if complete_response:
                chat_conversations.save_message(conversation_id, "assistant", complete_response)
                trace_store.complete_run(run_id, complete_response)
                yield from _cascade_parent_in_chat(user_id, run_id, complete_response)
        except Exception as error:
            logger.error("Approval resume error: %s", repr(error))
            yield "\n\nObsyGPT could not complete the response."
            trace_store.fail_run(run_id, str(error))

    return StreamingResponse(
        generate(),
        media_type="text/plain",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )


def _cascade_parent_in_chat(user_id: int, child_run_id: int, final_text: str) -> Generator[str, None, None]:
    """After a dispatched sub-agent finishes, resumes the parent chat loop when the whole dispatch is done."""
    from ..agent.subagents import DispatchSubagentsTool, context_for_parent_run, mark_child_completed_and_cascade

    cascade = mark_child_completed_and_cascade(child_run_id, final_text)
    if not cascade:
        return
    parent_run_id, observation = cascade
    parent_config = agent_store.get_run_config(parent_run_id)
    parent_state = agent_store.load_run_state(parent_run_id)
    if not parent_config or not parent_state or not parent_config.get("conversation_id"):
        return
    conversation_id = parent_config["conversation_id"]
    trace_store = TraceStore()
    parent_workspace = chat_specs.workspace_root_for_run(parent_config)
    registry = chat_specs.build_agent_tool_registry(user_id=user_id, workspace_root=parent_workspace, agent_id=parent_config.get("agent_id"))
    registry.register(DispatchSubagentsTool(user_id, parent_run_id, parent_workspace, conversation_id, trace_store, context_message=context_for_parent_run(parent_run_id, parent_state)))
    permissions = agent_store.get_agent_tool_permissions(parent_config.get("agent_id"))
    tool_specs = [spec for spec in registry.list_specs() if permissions.get(spec.name, False)]
    executor = build_approval_aware_executor(user_id, conversation_id, parent_run_id, registry)
    conversation = [
        ChatMessage(role=item.get("role", "user"), content=item.get("content", ""))
        for item in parent_state.get("messages", [])
        if isinstance(item, dict)
    ]
    messages = [*conversation, ChatMessage(role="user", content=observation)]

    agent_store.set_run_status(parent_run_id, "running")
    loop = AgentLoop(trace_store=trace_store, execute_tool=executor)
    try:
        complete_response = ""
        for token in loop.run(
            agent_run_id=parent_run_id,
            system_prompt=parent_config["system_prompt"],
            provider_type=parent_config["provider_type"],
            provider_base_url=parent_config["base_url"],
            provider_api_key_env=parent_config["api_key_env"],
            model=parent_config["model_name"],
            temperature=float(parent_config["temperature"]),
            tool_specs=tool_specs,
            messages=messages,
            guardrail_config=load_guardrail_config(),
            on_before_tool=lambda name, args, conversation_state: agent_store.save_run_state(parent_run_id, conversation_state, iterations=0, tool_call_count=0, thought_text=""),
            fallbacks=chat_specs.get_agent_fallbacks(parent_config.get("agent_id")),
        ):
            complete_response += token
            yield token
        if complete_response:
            chat_conversations.save_message(conversation_id, "assistant", complete_response)
            trace_store.complete_run(parent_run_id, complete_response)
    except ApprovalRequiredError as error:
        notice = (
            f"\n\n[ObsyGPT] Aprobacion requerida para ejecutar `{error.tool_name}` "
            f"(aprobacion #{error.approval_id}). Acepta o rechaza la ejecucion para continuar."
        )
        yield notice
        trace_store.pause_run(parent_run_id, notice)
    except Exception as error:  # noqa: BLE001
        logger.error("Parent cascade error: %s", repr(error))
        yield "\n\nObsyGPT could not resume the parent agent."
        trace_store.fail_run(parent_run_id, str(error))
