from collections.abc import Generator, Iterator
from datetime import datetime
import json
from pathlib import Path
from queue import Queue
from threading import Thread
from typing import Literal

from fastapi import APIRouter, HTTPException, Request
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, Field, field_validator

from ..agent.errors import ApprovalRequiredError
from ..agent.protocol import strip_tool_blocks
from ..agent.runtime import AgentLoop
from ..agent.store import (
    create_tool_approval,
    decide_approval,
    get_agent_tool_permissions,
    get_run_config,
    list_pending_approvals,
    load_run_state,
    save_run_state,
    set_run_status,
)
from ..agent.tools.base import ToolRegistry, ToolResult, ToolSpec
from ..agent.tools.browser import BrowserTools
from ..agent.tools.files import FilesTools, default_workspace_root
from ..agent.tools.terminal import TerminalTool
from ..agent.tools.web import WebFetchTool
from ..auth.routes import require_user
from ..db import connect
from ..files import AttachmentRecord, build_attachment_context
from ..files.service import IMAGE_MIME_TYPES
from ..memory.context import build_memory_context, build_user_instructions_block
from ..memory.learning import learn_habits_in_background
from ..projects.store import get_project_for_conversation
from ..providers import ChatMessage
from ..traces.store import TraceStore
from ..workflows import AgentSpec, FallbackSpec, McpSpec, WorkflowRuntime, WorkflowSpec
from ..admin.routes import render_skill_md
from ..workspace.routes import get_user_preferences, get_user_workspace


router = APIRouter(prefix="/api", tags=["chat"])


class MessageRequest(BaseModel):
    message: str
    agent_id: int | None = None
    workflow_id: int | None = None
    attachment_ids: list[int] = []
    mode: Literal["act", "plan", "think"] | None = None


MODE_DIRECTIVES: dict[str, str] = {
    "plan": (
        "Directiva de modo PLAN para esta respuesta: antes de responder o usar herramientas, "
        "presenta un plan numerado y concreto de pasos (que incluye que herramienta usarias en cada uno si aplica). "
        "Despues ejecuta el plan paso a paso y termina con el resultado final."
    ),
    "think": (
        "Directiva de modo THINK para esta respuesta: razona en profundidad antes de contestar. "
        "Considera alternativas, supuestos, riesgos y contraejemplos. Usa herramientas si necesitas datos reales. "
        "Termina con una respuesta final clara y estructurada; el razonamiento previo debe ser breve y util, no relleno."
    ),
}


def build_mode_directive(mode: str | None) -> str | None:
    if not mode or mode == "act":
        return None
    return MODE_DIRECTIVES.get(mode)


class ConversationUpdateRequest(BaseModel):
    title: str = Field(min_length=1, max_length=120)


def parse_slash_skill(message: str) -> tuple[str, str] | None:
    stripped = message.strip()
    if not stripped.startswith("/") or stripped.startswith("//"):
        return None
    command, _, task = stripped[1:].partition(" ")
    skill_name = command.strip()
    if not skill_name:
        return None
    return skill_name, task.strip()


def build_project_context(project: dict, user_id: int) -> str:
    """Builds the context block with project instructions and knowledge files."""
    blocks = []
    instructions = (project.get("instructions") or "").strip()
    if instructions:
        blocks.append(f"Instrucciones del proyecto '{project['name']}' (siguelas en todas las respuestas de este proyecto):\n{instructions}")

    attachment_ids = project.get("attachment_ids") or []
    if attachment_ids:
        records = get_attachment_records(user_id, attachment_ids)
        attachment_context = build_attachment_context(records)
        if attachment_context:
            blocks.append(f"Conocimiento del proyecto '{project['name']}':\n\n{attachment_context}")

    if not blocks:
        return ""
    return "CONTEXTO DE PROYECTO OBSYGPT\n\n" + "\n\n".join(blocks)


def create_conversation(user_id: int):
    with connect() as connection:
        with connection.cursor() as cursor:
            cursor.execute(
                """
                INSERT INTO conversations (user_id)
                VALUES (%s)
                RETURNING id, title, created_at;
                """,
                (user_id,),
            )
            return cursor.fetchone()


def delete_conversation(conversation_id: int, user_id: int) -> bool:
    with connect() as connection:
        with connection.cursor() as cursor:
            cursor.execute(
                """
                DELETE FROM conversations
                WHERE id = %s AND user_id = %s;
                """,
                (conversation_id, user_id),
            )
            return cursor.rowcount > 0


def update_conversation_title(conversation_id: int, user_id: int, title: str):  # noqa: ANN201
    with connect() as connection:
        with connection.cursor() as cursor:
            cursor.execute(
                """
                UPDATE conversations
                SET title = %s
                WHERE id = %s AND user_id = %s
                RETURNING id, title, created_at;
                """,
                (title, conversation_id, user_id),
            )
            row = cursor.fetchone()
            if not row:
                return None
            columns = [column.name for column in cursor.description]
            return dict(zip(columns, row))


def get_conversation(conversation_id: int, user_id: int):
    with connect() as connection:
        with connection.cursor() as cursor:
            cursor.execute(
                """
                SELECT id, title, created_at
                FROM conversations
                WHERE id = %s AND user_id = %s;
                """,
                (conversation_id, user_id),
            )
            return cursor.fetchone()


def get_conversations(user_id: int):
    with connect() as connection:
        with connection.cursor() as cursor:
            cursor.execute(
                """
                SELECT id, title, created_at, chat_number, folder_id
                FROM (
                    SELECT id, title, created_at, folder_id,
                           ROW_NUMBER() OVER (ORDER BY created_at, id) AS chat_number
                    FROM conversations
                    WHERE user_id = %s
                ) AS numbered_conversations
                ORDER BY folder_id NULLS LAST, created_at DESC, id DESC;
                """,
                (user_id,),
            )
            return cursor.fetchall()


def list_chat_folders(user_id: int) -> list[dict]:
    with connect() as connection:
        with connection.cursor() as cursor:
            cursor.execute(
                """
                SELECT f.id, f.name,
                       (SELECT COUNT(*) FROM conversations c WHERE c.folder_id = f.id) AS conversation_count
                FROM chat_folders f
                WHERE f.user_id = %s
                ORDER BY f.created_at, f.id;
                """,
                (user_id,),
            )
            columns = [column.name for column in cursor.description]
            return [dict(zip(columns, row)) for row in cursor.fetchall()]


def create_chat_folder(user_id: int, name: str) -> dict:
    with connect() as connection:
        with connection.cursor() as cursor:
            cursor.execute(
                """
                INSERT INTO chat_folders (user_id, name)
                VALUES (%s, %s)
                RETURNING id, name, created_at;
                """,
                (user_id, name),
            )
            row = cursor.fetchone()
            return {"id": row[0], "name": row[1], "conversation_count": 0}


def rename_chat_folder(folder_id: int, user_id: int, name: str) -> dict | None:
    with connect() as connection:
        with connection.cursor() as cursor:
            cursor.execute(
                """
                UPDATE chat_folders
                SET name = %s
                WHERE id = %s AND user_id = %s
                RETURNING id, name;
                """,
                (name, folder_id, user_id),
            )
            row = cursor.fetchone()
            if not row:
                return None
            return {"id": row[0], "name": row[1]}


def delete_chat_folder(folder_id: int, user_id: int) -> bool:
    with connect() as connection:
        with connection.cursor() as cursor:
            cursor.execute(
                "DELETE FROM chat_folders WHERE id = %s AND user_id = %s;",
                (folder_id, user_id),
            )
            return cursor.rowcount > 0


def move_conversation_to_folder(conversation_id: int, user_id: int, folder_id: int | None) -> dict | None:
    if folder_id is not None:
        with connect() as connection:
            with connection.cursor() as cursor:
                cursor.execute("SELECT id FROM chat_folders WHERE id = %s AND user_id = %s;", (folder_id, user_id))
                if not cursor.fetchone():
                    return None
    with connect() as connection:
        with connection.cursor() as cursor:
            cursor.execute(
                """
                UPDATE conversations
                SET folder_id = %s
                WHERE id = %s AND user_id = %s
                RETURNING id, folder_id;
                """,
                (folder_id, conversation_id, user_id),
            )
            row = cursor.fetchone()
            if not row:
                return None
            return {"id": row[0], "folder_id": row[1]}


def update_user_message(message_id: int, conversation_id: int, user_id: int, content: str) -> bool:
    with connect() as connection:
        with connection.cursor() as cursor:
            cursor.execute(
                """
                UPDATE messages m
                SET content = %s
                FROM conversations c
                WHERE m.id = %s
                  AND m.conversation_id = c.id
                  AND m.conversation_id = %s
                  AND c.user_id = %s
                  AND m.role = 'user'
                ;
                """,
                (content, message_id, conversation_id, user_id),
            )
            return cursor.rowcount > 0


def save_message(conversation_id: int, role: str, content: str) -> int:
    with connect() as connection:
        with connection.cursor() as cursor:
            cursor.execute(
                """
                INSERT INTO messages (conversation_id, role, content)
                VALUES (%s, %s, %s)
                RETURNING id;
                """,
                (conversation_id, role, content),
            )
            return cursor.fetchone()[0]


def get_messages(conversation_id: int):
    with connect() as connection:
        with connection.cursor() as cursor:
            cursor.execute(
                """
                SELECT id, role, content, created_at
                FROM messages
                WHERE conversation_id = %s
                ORDER BY created_at, id;
                """,
                (conversation_id,),
            )
            return cursor.fetchall()


def get_attachment_records(user_id: int, attachment_ids: list[int]) -> list[AttachmentRecord]:
    if not attachment_ids:
        return []

    with connect() as connection:
        with connection.cursor() as cursor:
            cursor.execute(
                """
                SELECT
                    a.id,
                    a.file_name,
                    a.mime_type,
                    a.storage_path,
                    a.size_bytes,
                    ar.artifact_type,
                    ar.content
                FROM attachments a
                LEFT JOIN LATERAL (
                    SELECT artifact_type, content
                    FROM artifacts
                    WHERE attachment_id = a.id
                    ORDER BY created_at DESC, id DESC
                    LIMIT 1
                ) ar ON true
                WHERE a.user_id = %s AND a.id = ANY(%s)
                ORDER BY a.created_at, a.id;
                """,
                (user_id, attachment_ids),
            )
            rows = cursor.fetchall()

    return [
        AttachmentRecord(
            id=row[0],
            file_name=row[1],
            mime_type=row[2],
            storage_path=row[3],
            size_bytes=row[4],
            artifact_type=row[5],
            artifact_content=row[6],
        )
        for row in rows
    ]


def ensure_requested_attachments_available(attachment_ids: list[int], attachments: list[AttachmentRecord]) -> None:
    requested_ids = set(attachment_ids)
    if not requested_ids:
        return

    available_ids = {attachment.id for attachment in attachments}
    if requested_ids - available_ids:
        raise HTTPException(status_code=404, detail="One or more attachments were not found.")


def get_allowed_skill_names(agent_id: int | None) -> list[str]:
    if agent_id is None:
        return []

    with connect() as connection:
        with connection.cursor() as cursor:
            cursor.execute(
                """
                SELECT s.name
                FROM agent_skills askill
                JOIN skills s ON s.id = askill.skill_id
                WHERE askill.agent_id = %s AND s.enabled = true
                ORDER BY s.name;
                """,
                (agent_id,),
            )
            return [row[0] for row in cursor.fetchall()]


def get_enabled_skill_by_name(name: str) -> dict | None:
    with connect() as connection:
        with connection.cursor() as cursor:
            cursor.execute(
                """
                SELECT id, name, description, argument_hint, triggers, body, resources, enabled
                FROM skills
                WHERE name = %s AND enabled = true;
                """,
                (name,),
            )
            row = cursor.fetchone()
            if not row:
                return None
            columns = [column.name for column in cursor.description]
            return dict(zip(columns, row))


def build_slash_skill_prompt(skill: dict, task: str) -> str:
    skill_md = render_skill_md(skill)
    task_text = task or "Ejecuta esta skill con el contexto disponible. Si faltan datos, pide exactamente lo necesario."
    return (
        "Invocacion manual de Agent Skill. Sigue estrictamente el SKILL.md y aplica la skill a la tarea del usuario.\n\n"
        f"Ruta estandar: agents/skills/{skill['name']}/SKILL.md\n\n"
        f"{skill_md}\n"
        "## Tarea del usuario\n"
        f"{task_text}"
    )


def get_allowed_mcps(agent_id: int | None) -> list[McpSpec]:
    if agent_id is None:
        return []

    with connect() as connection:
        with connection.cursor() as cursor:
            cursor.execute(
                """
                SELECT m.name, m.description, m.connection_type
                FROM agent_mcps am
                JOIN mcp_servers m ON m.id = am.mcp_server_id
                WHERE am.agent_id = %s AND m.enabled = true
                ORDER BY m.name;
                """,
                (agent_id,),
            )
            return [McpSpec(name=row[0], description=row[1], connection_type=row[2]) for row in cursor.fetchall()]


def get_agent_fallbacks(agent_id: int | None) -> list[FallbackSpec]:
    if agent_id is None:
        return []
    with connect() as connection:
        with connection.cursor() as cursor:
            cursor.execute(
                """
                SELECT p.provider_type, p.base_url, p.api_key_env, m.model_name
                FROM agent_fallbacks af
                JOIN providers p ON p.id = af.provider_id
                JOIN models m ON m.id = af.model_id
                WHERE af.agent_id = %s
                ORDER BY af.priority, m.model_name;
                """,
                (agent_id,),
            )
            return [
                FallbackSpec(provider_type=row[0], provider_base_url=row[1], provider_api_key_env=row[2], model=row[3])
                for row in cursor.fetchall()
            ]


def build_agent_spec(row) -> AgentSpec:  # noqa: ANN001
    agent_id = row[0]
    return AgentSpec(
        id=agent_id,
        name=row[1],
        system_prompt=row[2],
        provider_type=row[3],
        provider_base_url=row[6],
        provider_api_key_env=row[7],
        model=row[4],
        temperature=float(row[5]),
        internet_enabled=bool(row[8]),
        multimodal_enabled=bool(row[9]),
        allowed_skills=get_allowed_skill_names(agent_id),
        allowed_mcps=get_allowed_mcps(agent_id),
        agentic_mode=bool(row[10]) if len(row) > 10 else False,
        fallbacks=get_agent_fallbacks(agent_id),
        model_supports_vision=bool(row[11]) if len(row) > 11 else False,
    )


def get_default_agent_spec() -> AgentSpec:
    with connect() as connection:
        with connection.cursor() as cursor:
            cursor.execute(
                """
                SELECT
                    a.id,
                    a.name,
                    a.system_prompt,
                    p.provider_type,
                    m.model_name,
                    a.temperature,
                    p.base_url,
                    p.api_key_env,
                    a.internet_enabled,
                    a.multimodal_enabled,
                    a.agentic_mode,
                    m.supports_vision
                FROM agents a
                JOIN providers p ON p.id = a.provider_id
                JOIN models m ON m.id = a.model_id
                WHERE a.enabled = true
                ORDER BY a.id
                LIMIT 1;
                """
            )
            row = cursor.fetchone()

    if not row:
        return AgentSpec(
            id=None,
            name="Default Assistant",
            system_prompt="You are ObsyGPT, a helpful multi-agent AI assistant. Answer clearly and accurately.",
            provider_type="openrouter",
            provider_base_url="https://openrouter.ai/api/v1",
            provider_api_key_env="OPENROUTER_API_KEY",
            model="nvidia/nemotron-3-super-120b-a12b:free",
            temperature=0.7,
            internet_enabled=False,
            multimodal_enabled=False,
            allowed_skills=[],
            allowed_mcps=[],
        )

    return build_agent_spec(row)


def get_agent_spec(agent_id: int | None) -> AgentSpec:
    if agent_id is None:
        return get_default_agent_spec()

    with connect() as connection:
        with connection.cursor() as cursor:
            cursor.execute(
                """
                SELECT
                    a.id,
                    a.name,
                    a.system_prompt,
                    p.provider_type,
                    m.model_name,
                    a.temperature,
                    p.base_url,
                    p.api_key_env,
                    a.internet_enabled,
                    a.multimodal_enabled,
                    a.agentic_mode,
                    m.supports_vision
                FROM agents a
                JOIN providers p ON p.id = a.provider_id
                JOIN models m ON m.id = a.model_id
                WHERE a.id = %s AND a.enabled = true;
                """,
                (agent_id,),
            )
            row = cursor.fetchone()

    if not row:
        raise HTTPException(status_code=404, detail="Agent not found.")
    return build_agent_spec(row)


def get_workflow_spec(workflow_id: int | None, agent_id: int | None) -> WorkflowSpec:
    if workflow_id is None:
        agent = get_agent_spec(agent_id)
        return WorkflowSpec(id=None, name="Selected Agent", workflow_type="single_agent", agents=[agent])

    with connect() as connection:
        with connection.cursor() as cursor:
            cursor.execute(
                """
                SELECT id, name, workflow_type
                FROM workflows
                WHERE id = %s AND enabled = true;
                """,
                (workflow_id,),
            )
            workflow = cursor.fetchone()

            if not workflow:
                raise HTTPException(status_code=404, detail="Workflow not found.")

            cursor.execute(
                """
                SELECT
                    a.id,
                    a.name,
                    a.system_prompt,
                    p.provider_type,
                    m.model_name,
                    a.temperature,
                    p.base_url,
                    p.api_key_env,
                    a.internet_enabled,
                    a.multimodal_enabled,
                    a.agentic_mode,
                    m.supports_vision
                FROM workflow_steps ws
                JOIN agents a ON a.id = ws.agent_id
                JOIN providers p ON p.id = a.provider_id
                JOIN models m ON m.id = a.model_id
                WHERE ws.workflow_id = %s AND a.enabled = true
                ORDER BY ws.step_order;
                """,
                (workflow_id,),
            )
            agent_rows = cursor.fetchall()

    agents = [build_agent_spec(row) for row in agent_rows]
    if not agents:
        agents = [get_agent_spec(agent_id)]

    return WorkflowSpec(id=workflow[0], name=workflow[1], workflow_type=workflow[2], agents=agents)


def serialize_datetime(value: datetime) -> str:
    return value.isoformat()


def build_conversation_label(chat_number: int, created_at: datetime) -> str:
    formatted_time = created_at.astimezone().strftime("%m/%d/%Y %I:%M %p")
    formatted_time = formatted_time.replace(" 0", " ").lower()
    return f"Chat {chat_number} - {formatted_time}"


@router.get("/conversations")
def list_conversations(request: Request):
    user_id = require_user(request)
    conversations = [
        {
            "id": row[0],
            "title": row[1],
            "created_at": serialize_datetime(row[2]),
            "chat_number": row[3],
            "folder_id": row[4],
            "label": (row[1] or "").strip() or build_conversation_label(row[3], row[2]),
        }
        for row in get_conversations(user_id)
    ]
    return {"conversations": conversations}


@router.post("/conversations")
def new_conversation(request: Request):
    user_id = require_user(request)
    conversation = create_conversation(user_id)
    return {"conversation": {"id": conversation[0], "title": conversation[1], "created_at": serialize_datetime(conversation[2])}}


@router.delete("/conversations/{conversation_id}")
def remove_conversation(conversation_id: int, request: Request):
    user_id = require_user(request)
    if not delete_conversation(conversation_id, user_id):
        raise HTTPException(status_code=404, detail="Conversation not found.")
    return {"removed": True, "conversation_id": conversation_id}


@router.patch("/conversations/{conversation_id}")
def rename_conversation(conversation_id: int, data: ConversationUpdateRequest, request: Request):
    user_id = require_user(request)
    title = data.title.strip()
    if not title:
        raise HTTPException(status_code=400, detail="Conversation title is required.")
    conversation = update_conversation_title(conversation_id, user_id, title)
    if not conversation:
        raise HTTPException(status_code=404, detail="Conversation not found.")
    return {"conversation": {**conversation, "created_at": serialize_datetime(conversation["created_at"])}}


class FolderPayload(BaseModel):
    name: str = Field(min_length=1, max_length=100)

    @field_validator("name")
    @classmethod
    def strip_name(cls, value: str) -> str:
        stripped = value.strip()
        if not stripped:
            raise ValueError("Folder name is required.")
        return stripped


class ConversationFolderPayload(BaseModel):
    folder_id: int | None = Field(default=None, ge=1)


@router.get("/folders")
def get_folders(request: Request):
    user_id = require_user(request)
    return {"folders": list_chat_folders(user_id)}


@router.post("/folders")
def post_folder(payload: FolderPayload, request: Request):
    user_id = require_user(request)
    return {"folder": create_chat_folder(user_id, payload.name.strip())}


@router.patch("/folders/{folder_id}")
def patch_folder(folder_id: int, payload: FolderPayload, request: Request):
    user_id = require_user(request)
    folder = rename_chat_folder(folder_id, user_id, payload.name.strip())
    if not folder:
        raise HTTPException(status_code=404, detail="Folder not found.")
    return {"folder": folder}


@router.delete("/folders/{folder_id}")
def remove_folder(folder_id: int, request: Request):
    user_id = require_user(request)
    if not delete_chat_folder(folder_id, user_id):
        raise HTTPException(status_code=404, detail="Folder not found.")
    return {"id": folder_id, "deleted": True}


@router.put("/conversations/{conversation_id}/folder")
def set_conversation_folder(conversation_id: int, payload: ConversationFolderPayload, request: Request):
    user_id = require_user(request)
    result = move_conversation_to_folder(conversation_id, user_id, payload.folder_id)
    if not result:
        raise HTTPException(status_code=404, detail="Conversation or folder not found.")
    return result


class MessageEditPayload(BaseModel):
    content: str = Field(min_length=1, max_length=100000)


@router.patch("/conversations/{conversation_id}/messages/{message_id}")
def edit_message(conversation_id: int, message_id: int, payload: MessageEditPayload, request: Request):
    user_id = require_user(request)
    if not update_user_message(message_id, conversation_id, user_id, payload.content):
        raise HTTPException(status_code=404, detail="Message not found or not editable.")
    return {"message_id": message_id, "updated": True}


@router.get("/conversations/{conversation_id}/messages")
def list_messages(conversation_id: int, request: Request):
    user_id = require_user(request)
    conversation = get_conversation(conversation_id, user_id)
    if not conversation:
        raise HTTPException(status_code=404, detail="Conversation not found.")

    messages = [
        {"id": row[0], "role": row[1], "content": row[2], "created_at": serialize_datetime(row[3])}
        for row in get_messages(conversation_id)
    ]
    return {
        "conversation": {"id": conversation[0], "title": conversation[1], "created_at": serialize_datetime(conversation[2])},
        "messages": messages,
    }


@router.post("/conversations/{conversation_id}/messages")
def stream_message(conversation_id: int, data: MessageRequest, request: Request):
    user_id = require_user(request)
    conversation = get_conversation(conversation_id, user_id)
    if not conversation:
        raise HTTPException(status_code=404, detail="Conversation not found.")

    user_message = data.message.strip()
    if not user_message:
        raise HTTPException(status_code=400, detail="Please enter a message.")

    slash_skill = parse_slash_skill(user_message)
    slash_skill_prompt = None
    if slash_skill:
        skill_name, skill_task = slash_skill
        skill = get_enabled_skill_by_name(skill_name)
        if not skill:
            raise HTTPException(status_code=404, detail=f"Skill not found or disabled: {skill_name}")
        slash_skill_prompt = build_slash_skill_prompt(skill, skill_task)

    user_message_id = save_message(conversation_id, "user", user_message)
    stored_messages = get_messages(conversation_id)
    provider_messages = [
        ChatMessage(role=row[1], content=strip_tool_blocks(row[2]) if row[1] == "assistant" else row[2])
        for row in stored_messages
    ]
    if slash_skill_prompt:
        provider_messages[-1] = ChatMessage(role="user", content=slash_skill_prompt)
    attachments = get_attachment_records(user_id, data.attachment_ids)
    ensure_requested_attachments_available(data.attachment_ids, attachments)
    workflow = get_workflow_spec(data.workflow_id, data.agent_id)
    trace_store = TraceStore()
    agent_run_id = trace_store.create_run(user_id, conversation_id, user_message_id, workflow.agents[0].id if workflow.agents else None, workflow.id)
    active_agent = workflow.agents[0] if workflow.agents else None
    vision_supported = bool(active_agent and active_agent.model_supports_vision)
    attachment_context = build_attachment_context(attachments, vision_supported=vision_supported)
    if vision_supported:
        image_urls = [url for attachment in attachments for url in [attachment_data_url(attachment)] if url]
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
        project_context = build_project_context(project, user_id)
        if project_context:
            provider_messages.append(ChatMessage(role="user", content=project_context))
            trace_store.add_event(agent_run_id, "project_context", f"Project context loaded: {project['name']}")
    mode_directive = build_mode_directive(data.mode)
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
        return _stream_agentic(user_id, conversation_id, agent_run_id, active_agent, provider_messages, trace_store, project_folder=(project or {}).get("folder_path"), user_message=user_message)

    from ..monitoring import otel

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
                save_message(conversation_id, "assistant", complete_response)
                learn_habits_in_background(user_id, conversation_id, active_agent, user_message, complete_response)
                otel.record_assistant_response(getattr(active_agent, "model", "workflow") or "workflow", len(complete_response), complete_response)
        except Exception as error:
            print("OpenRouter streaming error:", repr(error))
            yield "\n\nObsyGPT could not complete the response."

    return StreamingResponse(
        generate(),
        media_type="text/plain",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )


def attachment_data_url(attachment: AttachmentRecord) -> str | None:
    """Encodes a stored image attachment as a data URL; None when missing or too large."""
    from base64 import b64encode

    max_bytes = 4 * 1024 * 1024
    if attachment.mime_type not in IMAGE_MIME_TYPES or attachment.size_bytes > max_bytes:
        return None
    path = Path(attachment.storage_path)
    if not path.exists():
        return None
    encoded = b64encode(path.read_bytes()).decode("ascii")
    return f"data:{attachment.mime_type};base64,{encoded}"


def build_agent_tool_registry(user_id: int | None = None, workspace_root=None, agent_id: int | None = None) -> ToolRegistry:
    workspace = workspace_root or (get_user_workspace(user_id) if user_id is not None else default_workspace_root())
    workspace = Path(workspace).resolve() if not isinstance(workspace, Path) else workspace
    try:
        workspace.mkdir(parents=True, exist_ok=True)
    except OSError:
        pass
    registry = ToolRegistry()
    registry.register_many(FilesTools(workspace_root=workspace).tools())
    registry.register(TerminalTool(workspace_root=workspace))
    registry.register(WebFetchTool())
    from ..agent.tools.web import NewsSearchTool, WebSearchTool

    registry.register(WebSearchTool())
    registry.register(NewsSearchTool())
    registry.register_many(BrowserTools(workspace_root=workspace).tools())
    if user_id is not None or agent_id is not None:
        from ..connectors.bridge import register_connector_tools, register_mcp_agent_tools

        if user_id is not None:
            register_connector_tools(registry, user_id)
        if agent_id is not None:
            register_mcp_agent_tools(registry, agent_id)
    return registry


def get_agent_tool_specs(agent_id: int | None, user_id: int | None = None, workspace_root=None) -> list[ToolSpec]:
    permissions = get_agent_tool_permissions(agent_id)
    if not permissions:
        return []
    registry = build_agent_tool_registry(user_id=user_id, workspace_root=workspace_root, agent_id=agent_id)
    specs = [spec for spec in registry.list_specs() if permissions.get(spec.name, False)]
    from ..agent.subagents import DISPATCH_SPEC

    if permissions.get(DISPATCH_SPEC.name):
        specs.append(DISPATCH_SPEC)
    return specs


def build_approval_aware_executor(user_id: int, conversation_id: int, agent_run_id: int, registry: ToolRegistry):
    preferences = get_user_preferences(user_id)
    policies = preferences.get("tool_policies") or {}

    def execute(name: str, args: dict) -> ToolResult:
        spec = registry.get(name).spec
        default_policy = "ask" if spec.permission == "sensitive" else "allow"
        policy = policies.get(name, default_policy)
        if policy == "block":
            return ToolResult(ok=False, output=f"Tool '{name}' is blocked by your security policy (Ajustes > Seguridad).")
        if spec.permission == "sensitive" and policy == "ask":
            approval_id = create_tool_approval(agent_run_id, user_id, conversation_id, name, args)
            raise ApprovalRequiredError(approval_id=approval_id, tool_name=name, args=args)
        return registry.run(name, args)

    return execute


ACTIVITY_FRAME_OPEN = "\x00ACT\x00"
ACTIVITY_FRAME_CLOSE = "\x00"


def _frame_activity(payload: dict) -> str:
    return ACTIVITY_FRAME_OPEN + json.dumps(payload, ensure_ascii=False) + ACTIVITY_FRAME_CLOSE


def _drive_agent_loop(start_loop) -> Generator[tuple[str, object], None, None]:
    """Runs the blocking agent loop in a worker thread and yields ("token"|"activity"|..., payload).

    ``start_loop`` receives an ``on_activity`` callback and returns the token iterator.
    This lets activity signals (thinking, tool start/end, retries) reach the HTTP stream in
    real time even while a long tool call produces no tokens.
    """
    events: Queue = Queue()

    def on_activity(payload: dict) -> None:
        events.put(("activity", payload))

    def worker() -> None:
        try:
            for token in start_loop(on_activity):
                events.put(("token", token))
            events.put(("done", None))
        except ApprovalRequiredError as error:
            events.put(("approval", error))
        except Exception as error:  # noqa: BLE001
            events.put(("error", error))
        finally:
            events.put(("end", None))

    thread = Thread(target=worker, daemon=True)
    thread.start()
    while True:
        kind, payload = events.get()
        yield kind, payload
        if kind == "end":
            return


def _stream_agentic(
    user_id: int,
    conversation_id: int,
    agent_run_id: int,
    agent: AgentSpec,
    provider_messages: list[ChatMessage],
    trace_store: TraceStore,
    project_folder: str | None = None,
    user_message: str = "",
) -> StreamingResponse:
    registry = build_agent_tool_registry(user_id=user_id, workspace_root=project_folder, agent_id=agent.id)
    from ..agent.subagents import DispatchSubagentsTool

    registry.register(DispatchSubagentsTool(user_id, agent_run_id, project_folder, conversation_id, trace_store, context_message=user_message))
    tool_specs = get_agent_tool_specs(agent.id, user_id=user_id, workspace_root=project_folder)
    executor = build_approval_aware_executor(user_id, conversation_id, agent_run_id, registry)

    def on_before_tool(name: str, args: dict, conversation: list[ChatMessage]) -> None:
        save_run_state(agent_run_id, conversation, iterations=0, tool_call_count=0, thought_text="")

    from ..monitoring import otel

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
                on_before_tool=on_before_tool,
                fallbacks=agent.fallbacks,
                on_activity=on_activity,
            )

        outcome: tuple[str, object] | None = None
        try:
            for kind, payload in _drive_agent_loop(start_loop):
                if kind == "token":
                    complete_response += str(payload)
                    yield str(payload)
                elif kind == "activity":
                    yield _frame_activity(payload)  # type: ignore[arg-type]
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
                    save_message(conversation_id, "assistant", complete_response)
                trace_store.pause_run(agent_run_id, notice)
                return

            if outcome is not None:  # error
                raise outcome[1]  # type: ignore[misc]

            if complete_response:
                save_message(conversation_id, "assistant", complete_response)
                trace_store.complete_run(agent_run_id, complete_response)
                otel.record_assistant_response(agent.model or "unknown", len(complete_response), complete_response)
                if user_message:
                    learn_habits_in_background(user_id, conversation_id, agent, user_message, complete_response)
        except Exception as error:
            print("Agentic loop error:", repr(error))
            yield "\n\nObsyGPT could not complete the response."
            trace_store.fail_run(agent_run_id, str(error))

    return StreamingResponse(
        generate(),
        media_type="text/plain",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )


@router.get("/approvals/pending")
def pending_approvals(conversation_id: int, request: Request):
    user_id = require_user(request)
    conversation = get_conversation(conversation_id, user_id)
    if not conversation:
        raise HTTPException(status_code=404, detail="Conversation not found.")
    approvals = [
        {
            "id": approval["id"],
            "agent_run_id": approval["agent_run_id"],
            "conversation_id": approval["conversation_id"],
            "tool_name": approval["tool_name"],
            "args": approval["args"] if not isinstance(approval["args"], str) else _safe_json(approval["args"]),
            "created_at": serialize_datetime(approval["created_at"]),
        }
        for approval in list_pending_approvals(user_id, conversation_id)
    ]
    return {"approvals": approvals}


def _safe_json(value: str) -> dict:
    try:
        parsed = json.loads(value)
        return parsed if isinstance(parsed, dict) else {}
    except json.JSONDecodeError:
        return {}


@router.post("/approvals/{approval_id}/approve")
def approve_tool(approval_id: int, request: Request):
    return _resume_with_approval(approval_id, request, approved=True)


@router.post("/approvals/{approval_id}/deny")
def deny_tool(approval_id: int, request: Request):
    return _resume_with_approval(approval_id, request, approved=False)


def _resume_with_approval(approval_id: int, request: Request, approved: bool) -> StreamingResponse:
    user_id = require_user(request)
    approval = decide_approval(approval_id, user_id, "approved" if approved else "denied")
    if not approval:
        raise HTTPException(status_code=404, detail="Approval not found or already decided.")

    run_config = get_run_config(approval["agent_run_id"])
    state = load_run_state(approval["agent_run_id"])
    if not run_config or not state:
        raise HTTPException(status_code=404, detail="Run state not found for this approval.")

    conversation_id = approval["conversation_id"]
    run_id = approval["agent_run_id"]
    conversation_messages = [
        ChatMessage(role=item.get("role", "user"), content=item.get("content", ""))
        for item in state.get("messages", [])
        if isinstance(item, dict)
    ]

    registry = build_agent_tool_registry(user_id=user_id, agent_id=run_config.get("agent_id"))
    permissions = get_agent_tool_permissions(run_config.get("agent_id"))
    trace_store = TraceStore()
    from ..agent.subagents import DISPATCH_SPEC, DispatchSubagentsTool

    if permissions.get(DISPATCH_SPEC.name) and not any(spec.name == DISPATCH_SPEC.name for spec in registry.list_specs()):
        from ..agent.subagents import context_for_parent_run

        registry.register(DispatchSubagentsTool(user_id, run_id, None, conversation_id, trace_store, context_message=context_for_parent_run(run_id, state)))
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
                save_message(conversation_id, "assistant", notice)
            trace_store.pause_run(run_id, notice)

        return StreamingResponse(
            paused_generate(),
            media_type="text/plain",
            headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
        )

    resume_messages = [*conversation_messages, ChatMessage(role="user", content=observation)]

    def generate() -> Generator[str, None, None]:
        set_run_status(run_id, "running")
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
                on_before_tool=lambda name, args, conversation: save_run_state(run_id, conversation, iterations=0, tool_call_count=0, thought_text=""),
                fallbacks=get_agent_fallbacks(run_config.get("agent_id")),
                on_activity=on_activity,
            )

        outcome: tuple[str, object] | None = None
        try:
            for kind, payload in _drive_agent_loop(start_loop):
                if kind == "token":
                    complete_response += str(payload)
                    yield str(payload)
                elif kind == "activity":
                    yield _frame_activity(payload)  # type: ignore[arg-type]
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
                    save_message(conversation_id, "assistant", complete_response)
                trace_store.pause_run(run_id, notice)
                from ..agent.subagents import update_dispatch

                update_dispatch(run_id, "awaiting_approval")
                return

            if outcome is not None:
                raise outcome[1]  # type: ignore[misc]

            if complete_response:
                save_message(conversation_id, "assistant", complete_response)
                trace_store.complete_run(run_id, complete_response)
                yield from _cascade_parent_in_chat(user_id, run_id, complete_response)
        except Exception as error:
            print("Approval resume error:", repr(error))
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
    parent_config = get_run_config(parent_run_id)
    parent_state = load_run_state(parent_run_id)
    if not parent_config or not parent_state or not parent_config.get("conversation_id"):
        return
    conversation_id = parent_config["conversation_id"]
    trace_store = TraceStore()
    registry = build_agent_tool_registry(user_id=user_id, agent_id=parent_config.get("agent_id"))
    registry.register(DispatchSubagentsTool(user_id, parent_run_id, None, conversation_id, trace_store, context_message=context_for_parent_run(parent_run_id, parent_state)))
    permissions = get_agent_tool_permissions(parent_config.get("agent_id"))
    tool_specs = [spec for spec in registry.list_specs() if permissions.get(spec.name, False)]
    executor = build_approval_aware_executor(user_id, conversation_id, parent_run_id, registry)
    conversation = [
        ChatMessage(role=item.get("role", "user"), content=item.get("content", ""))
        for item in parent_state.get("messages", [])
        if isinstance(item, dict)
    ]
    messages = [*conversation, ChatMessage(role="user", content=observation)]

    set_run_status(parent_run_id, "running")
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
            on_before_tool=lambda name, args, conversation_state: save_run_state(parent_run_id, conversation_state, iterations=0, tool_call_count=0, thought_text=""),
            fallbacks=get_agent_fallbacks(parent_config.get("agent_id")),
        ):
            complete_response += token
            yield token
        if complete_response:
            save_message(conversation_id, "assistant", complete_response)
            trace_store.complete_run(parent_run_id, complete_response)
    except ApprovalRequiredError as error:
        notice = (
            f"\n\n[ObsyGPT] Aprobacion requerida para ejecutar `{error.tool_name}` "
            f"(aprobacion #{error.approval_id}). Acepta o rechaza la ejecucion para continuar."
        )
        yield notice
        trace_store.pause_run(parent_run_id, notice)
    except Exception as error:  # noqa: BLE001
        print("Parent cascade error:", repr(error))
        yield "\n\nObsyGPT could not resume the parent agent."
        trace_store.fail_run(parent_run_id, str(error))
