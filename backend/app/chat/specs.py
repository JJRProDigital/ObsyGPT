"""Agent and context assembly: specs, tool registries, prompts, project context.

Consumers (tasks manager, subagents, streaming) call these through the module
(``specs.get_agent_spec(...)``) so tests can patch ``app.chat.specs.*`` once.
"""

from pathlib import Path
from typing import Literal

from fastapi import HTTPException

from .. import db as app_db
from ..admin import skill_files
from ..agent.tools.base import ToolRegistry, ToolSpec
from ..agent.tools.browser import BrowserTools
from ..agent.tools.files import FilesTools, default_workspace_root
from ..agent.tools.terminal import TerminalTool
from ..agent.tools.web import WebFetchTool
from ..files import build_attachment_context  # noqa: F401 - re-exported convenience
from ..projects.store import get_project_for_conversation
from ..workspace import routes as workspace_routes
from ..workflows import AgentSpec, FallbackSpec, McpSpec, WorkflowSpec
from . import attachments as chat_attachments


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
        records = chat_attachments.get_attachment_records(user_id, attachment_ids)
        attachment_context = chat_attachments.build_attachment_context(records)
        if attachment_context:
            blocks.append(f"Conocimiento del proyecto '{project['name']}':\n\n{attachment_context}")

    if not blocks:
        return ""
    return "CONTEXTO DE PROYECTO OBSYGPT\n\n" + "\n\n".join(blocks)


def get_allowed_skill_names(agent_id: int | None) -> list[str]:
    if agent_id is None:
        return []

    with app_db.connect() as connection:
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
    with app_db.connect() as connection:
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
    skill_md = skill_files.render_skill_md(skill)
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

    with app_db.connect() as connection:
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
    with app_db.connect() as connection:
        with connection.cursor() as cursor:
            cursor.execute(
                """
                SELECT p.provider_type, p.base_url, p.api_key_env, m.model_name
                FROM agent_fallbacks af
                JOIN providers p ON p.id = af.provider_id
                JOIN models m ON m.id = af.model_id
                WHERE af.agent_id = %s
                ORDER BY af.priority;
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
    with app_db.connect() as connection:
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

    with app_db.connect() as connection:
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

    with app_db.connect() as connection:
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


def workspace_root_for_run(run_config: dict) -> str | None:
    """Re-derives the project workspace of a run so resumes keep the same sandbox."""
    conversation_id = run_config.get("conversation_id")
    user_id = run_config.get("user_id")
    if not conversation_id or not user_id:
        return None
    project = get_project_for_conversation(conversation_id, user_id)
    return (project or {}).get("folder_path")


def build_agent_tool_registry(user_id: int | None = None, workspace_root=None, agent_id: int | None = None) -> ToolRegistry:
    workspace = workspace_root or (workspace_routes.get_user_workspace(user_id) if user_id is not None else default_workspace_root())
    workspace = Path(workspace).resolve() if not isinstance(workspace, Path) else workspace
    try:
        workspace.mkdir(parents=True, exist_ok=True)
    except OSError:
        pass
    registry = ToolRegistry()
    browser_session = f"user:{user_id}" if user_id is not None else "default"
    registry.register_many(FilesTools(workspace_root=workspace).tools())
    registry.register(TerminalTool(workspace_root=workspace))
    registry.register(WebFetchTool())
    from ..agent.tools.web import NewsSearchTool, WebSearchTool

    registry.register(WebSearchTool())
    registry.register(NewsSearchTool())
    registry.register_many(BrowserTools(workspace_root=workspace, session_key=browser_session).tools())
    if user_id is not None or agent_id is not None:
        from ..connectors.bridge import register_connector_tools, register_mcp_agent_tools

        if user_id is not None:
            register_connector_tools(registry, user_id)
        if agent_id is not None:
            register_mcp_agent_tools(registry, agent_id)
    return registry


def get_agent_tool_specs(agent_id: int | None, user_id: int | None = None, workspace_root=None) -> list[ToolSpec]:
    from ..agent import store as agent_store

    permissions = agent_store.get_agent_tool_permissions(agent_id)
    if not permissions:
        return []
    registry = build_agent_tool_registry(user_id=user_id, workspace_root=workspace_root, agent_id=agent_id)
    specs = [spec for spec in registry.list_specs() if permissions.get(spec.name, False)]
    from ..agent.subagents import DISPATCH_SPEC

    if permissions.get(DISPATCH_SPEC.name):
        specs.append(DISPATCH_SPEC)
    return specs
