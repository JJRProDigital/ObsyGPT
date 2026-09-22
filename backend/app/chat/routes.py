"""Chat API composition: conversations, approvals, and the message endpoint.

Domain logic lives in `conversations` (chats/folders/messages), `specs`
(agent and context assembly), `attachments`, `approvals` (resume after a user
decision), `streaming` (agentic loop streaming) and `activity` (loop plumbing).
This module composes the router, hosts the message entry point and re-exports
moved names for backwards compatibility.
"""

import logging
from collections.abc import Generator
from typing import Literal

from fastapi import APIRouter, HTTPException, Request
from fastapi.responses import StreamingResponse
from pydantic import BaseModel

from ..agent.protocol import strip_tool_blocks  # noqa: F401 - re-exported
from ..auth import routes as auth
from ..memory.context import build_memory_context, build_user_instructions_block
from ..memory.learning import learn_habits_in_background
from ..monitoring import otel
from ..projects.store import get_project_for_conversation
from ..providers import ChatMessage
from ..traces.store import TraceStore
from ..workflows import WorkflowRuntime
from . import approvals as chat_approvals
from . import attachments as chat_attachments
from . import conversations as chat_conversations
from . import specs as chat_specs
from . import streaming as chat_streaming


logger = logging.getLogger("obsygpt.chat")

router = APIRouter(prefix="/api", tags=["chat"])

router.include_router(chat_conversations.router)
router.include_router(chat_approvals.router)


class MessageRequest(BaseModel):
    message: str
    agent_id: int | None = None
    workflow_id: int | None = None
    attachment_ids: list[int] = []
    mode: Literal["act", "plan", "think"] | None = None


@router.post("/conversations/{conversation_id}/messages")
def stream_message(conversation_id: int, data: MessageRequest, request: Request):
    user_id = auth.require_user(request)
    conversation = chat_conversations.get_conversation(conversation_id, user_id)
    if not conversation:
        raise HTTPException(status_code=404, detail="Conversation not found.")

    user_message = data.message.strip()
    if not user_message:
        raise HTTPException(status_code=400, detail="Please enter a message.")

    slash_skill = chat_specs.parse_slash_skill(user_message)
    slash_skill_prompt = None
    if slash_skill:
        skill_name, skill_task = slash_skill
        skill = chat_specs.get_enabled_skill_by_name(skill_name)
        if not skill:
            raise HTTPException(status_code=404, detail=f"Skill not found or disabled: {skill_name}")
        slash_skill_prompt = chat_specs.build_slash_skill_prompt(skill, skill_task)

    user_message_id = chat_conversations.save_message(conversation_id, "user", user_message)
    stored_messages = chat_conversations.get_messages(conversation_id)
    provider_messages = [
        ChatMessage(role=row[1], content=strip_tool_blocks(row[2]) if row[1] == "assistant" else row[2])
        for row in stored_messages
    ]
    if slash_skill_prompt:
        provider_messages[-1] = ChatMessage(role="user", content=slash_skill_prompt)
    attachments = chat_attachments.get_attachment_records(user_id, data.attachment_ids)
    chat_attachments.ensure_requested_attachments_available(data.attachment_ids, attachments)
    workflow = chat_specs.get_workflow_spec(data.workflow_id, data.agent_id)
    trace_store = TraceStore()
    agent_run_id = trace_store.create_run(user_id, conversation_id, user_message_id, workflow.agents[0].id if workflow.agents else None, workflow.id)
    active_agent = workflow.agents[0] if workflow.agents else None
    vision_supported = bool(active_agent and active_agent.model_supports_vision)
    attachment_context = chat_attachments.build_attachment_context(attachments, vision_supported=vision_supported)
    if vision_supported:
        image_urls = [url for attachment in attachments for url in [chat_attachments.attachment_data_url(attachment)] if url]
        if image_urls and provider_messages:
            last_user_index = max(index for index, message in enumerate(provider_messages) if message.role == "user")
            original = provider_messages[last_user_index]
            provider_messages[last_user_index] = ChatMessage(role="user", content=original.content, images=tuple(image_urls))
            trace_store.add_event(agent_run_id, "images_loaded", f"{len(image_urls)} image(s) attached for vision")
    if attachment_context:
        provider_messages.append(ChatMessage(role="user", content=f"Attachment context for this request:\n\n{attachment_context}"))
        trace_store.add_event(agent_run_id, "attachments_loaded", "Attachments loaded", ", ".join(attachment.file_name for attachment in attachments))
    instructions_block = build_user_instructions_block(user_id)
    if instructions_block:
        provider_messages.append(ChatMessage(role="user", content=instructions_block))
        trace_store.add_event(agent_run_id, "user_instructions", "Instrucciones personales cargadas")
    project = get_project_for_conversation(conversation_id, user_id)
    memory_context = build_memory_context(user_id, project_id=(project or {}).get("id"))
    if memory_context:
        provider_messages.append(ChatMessage(role="user", content=memory_context))
        trace_store.add_event(agent_run_id, "memory_loaded", "Persistent memory loaded", "memories and habits injected")
    if project:
        project_context = chat_specs.build_project_context(project, user_id)
        if project_context:
            provider_messages.append(ChatMessage(role="user", content=project_context))
            trace_store.add_event(agent_run_id, "project_context", f"Project context loaded: {project['name']}")
    mode_directive = chat_specs.build_mode_directive(data.mode)
    if mode_directive:
        provider_messages.append(ChatMessage(role="user", content=mode_directive))
        trace_store.add_event(agent_run_id, "mode_selected", f"Mode {data.mode} selected")
    if active_agent and not active_agent.agentic_mode:
        provider_messages.append(ChatMessage(role="user", content=(
            "SYSTEM NOTE: This conversation runs WITHOUT tool access. You cannot browse, fetch URLs, read files or run commands, "
            "and no tool will be executed for you. Never emit <<<TOOL blocks and never pretend a tool ran or imagine its output. "
            "If the user needs tools, tell them to pick an agent with agentic mode enabled in the agent selector."
        )))

    if active_agent and active_agent.agentic_mode:
        return chat_streaming.stream_agentic(user_id, conversation_id, agent_run_id, active_agent, provider_messages, trace_store, project_folder=(project or {}).get("folder_path"), user_message=user_message)

    otel.bind_context(**{"user.id": user_id, "session.id": conversation_id, "prompt.id": agent_run_id})
    otel.record_user_prompt(len(user_message), user_message)

    def generate() -> Generator[str, None, None]:
        complete_response = ""
        runtime = WorkflowRuntime(trace_store=trace_store)
        try:
            for token in runtime.stream_workflow(agent_run_id, workflow, provider_messages):
                complete_response += token
                yield token

            if complete_response:
                chat_conversations.save_message(conversation_id, "assistant", complete_response)
                learn_habits_in_background(user_id, conversation_id, active_agent, user_message, complete_response)
                otel.record_assistant_response(getattr(active_agent, "model", "workflow") or "workflow", len(complete_response), complete_response)
        except Exception as error:
            logger.error("OpenRouter streaming error: %s", repr(error))
            yield "\n\nObsyGPT could not complete the response."

    return StreamingResponse(
        generate(),
        media_type="text/plain",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )


# --- Backwards-compatible re-exports (tests and other modules import these) ---

from .conversations import (  # noqa: E402,F401
    ConversationUpdateRequest,
    FolderPayload,
    ConversationFolderPayload,
    MessageEditPayload,
    build_conversation_label,
    create_chat_folder,
    create_conversation,
    delete_chat_folder,
    delete_conversation,
    edit_message,
    get_conversation,
    get_conversations,
    get_folders,
    get_messages,
    list_chat_folders,
    list_conversations,
    list_messages,
    move_conversation_to_folder,
    new_conversation,
    patch_folder,
    post_folder,
    remove_conversation,
    remove_folder,
    rename_chat_folder,
    rename_conversation,
    save_message,
    serialize_datetime,
    set_conversation_folder,
    update_conversation_title,
    update_user_message,
)
from .specs import (  # noqa: E402,F401
    MODE_DIRECTIVES,
    build_agent_spec,
    build_agent_tool_registry,
    build_mode_directive,
    build_project_context,
    build_slash_skill_prompt,
    get_agent_fallbacks,
    get_agent_spec,
    get_allowed_mcps,
    get_allowed_skill_names,
    get_default_agent_spec,
    get_enabled_skill_by_name,
    get_workflow_spec,
    get_agent_tool_specs,
    parse_slash_skill,
    workspace_root_for_run,
)
from .attachments import (  # noqa: E402,F401
    attachment_data_url,
    build_attachment_context,
    ensure_requested_attachments_available,
    get_attachment_records,
)
from .approvals import approve_tool, build_approval_aware_executor, deny_tool, pending_approvals  # noqa: E402,F401
from .streaming import stream_agentic  # noqa: E402,F401
