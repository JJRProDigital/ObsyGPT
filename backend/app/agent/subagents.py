"""Sub-agent dispatch: parallel delegated workstreams with pausable approvals."""

from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass

from ..db import connect
from ..providers import ChatMessage
from ..traces.store import TraceStore
from .errors import ApprovalRequiredError
from .runtime import AgentLoop
from .settings import load_guardrail_config
from .store import create_tool_approval, save_run_state
from .tools.base import ToolResult, ToolSpec

MAX_SUBAGENTS = 3
SUBAGENT_TIMEOUT_SECONDS = 240

DISPATCH_TOOL_NAME = "dispatch_subagents"

MAX_CONTEXT_CHARS = 24000

DISPATCH_SPEC = ToolSpec(
    name=DISPATCH_TOOL_NAME,
    description=(
        "Delega subtareas a otros agentes configurados (max 3). Corren en paralelo y cada uno devuelve su resultado final. "
        "El usuario aprueba antes de despachar. IMPORTANTE: el mensaje original del usuario se adjunta automaticamente "
        "como contexto a cada sub-agente, asi que escribe goals BREVES (una instruccion corta); NUNCA incrustes codigo, "
        "HTML ni documentos largos dentro del JSON del goal."
    ),
    parameters='{"tasks": [{"agent": "Research Agent", "goal": "busca X y resume en 3 puntos"}]}',
    permission="sensitive",
)


@dataclass(frozen=True)
class ChildSpec:
    id: int
    name: str
    system_prompt: str
    provider_type: str
    provider_base_url: str | None
    provider_api_key_env: str | None
    model: str
    temperature: float
    fallbacks: list


def get_agent_spec_by_name(agent_name: str) -> ChildSpec | None:
    from ..chat import specs as chat_specs

    with connect() as connection:
        with connection.cursor() as cursor:
            cursor.execute(
                """
                SELECT
                    a.id, a.name, a.system_prompt, p.provider_type, p.base_url, p.api_key_env,
                    m.model_name, a.temperature
                FROM agents a
                LEFT JOIN providers p ON p.id = a.provider_id
                LEFT JOIN models m ON m.id = a.model_id
                WHERE a.name = %s AND a.enabled = true;
                """,
                (agent_name,),
            )
            row = cursor.fetchone()
            if not row:
                return None
            agent_id, name, system_prompt, provider_type, base_url, api_key_env, model, temperature = row
            if provider_type is None or model is None:
                cursor.execute(
                    """
                    SELECT p.provider_type, p.base_url, p.api_key_env, m.model_name
                    FROM providers p
                    JOIN models m ON m.provider_id = p.id
                    WHERE p.enabled = true AND m.enabled = true
                    ORDER BY p.id, m.id
                    LIMIT 1;
                    """
                )
                fallback = cursor.fetchone()
                if not fallback:
                    return None
                provider_type, base_url, api_key_env, model = fallback
            return ChildSpec(
                id=agent_id,
                name=name,
                system_prompt=system_prompt,
                provider_type=provider_type,
                provider_base_url=base_url,
                provider_api_key_env=api_key_env,
                model=model,
                temperature=float(temperature),
                fallbacks=chat_specs.get_agent_fallbacks(agent_id),
            )


def create_dispatch(parent_run_id: int, child_run_id: int, agent_name: str, goal: str) -> None:
    with connect() as connection:
        with connection.cursor() as cursor:
            cursor.execute(
                "INSERT INTO subagent_dispatches (parent_run_id, child_run_id, agent_name, goal) VALUES (%s, %s, %s, %s);",
                (parent_run_id, child_run_id, agent_name, goal),
            )


def update_dispatch(child_run_id: int, status: str, result: str = "") -> None:
    with connect() as connection:
        with connection.cursor() as cursor:
            cursor.execute(
                "UPDATE subagent_dispatches SET status = %s, result = %s WHERE child_run_id = %s;",
                (status, result[:10000], child_run_id),
            )


def list_dispatches(parent_run_id: int) -> list[dict]:
    with connect() as connection:
        with connection.cursor() as cursor:
            cursor.execute(
                """
                SELECT child_run_id, agent_name, goal, status, result
                FROM subagent_dispatches
                WHERE parent_run_id = %s
                ORDER BY child_run_id;
                """,
                (parent_run_id,),
            )
            columns = [column.name for column in cursor.description]
            return [dict(zip(columns, row)) for row in cursor.fetchall()]


def context_for_parent_run(parent_run_id: int, fallback_state: dict | None = None) -> str | None:
    """Best-effort context for dispatched children: the user message that triggered the parent run."""
    with connect() as connection:
        with connection.cursor() as cursor:
            cursor.execute("SELECT message_id FROM agent_runs WHERE id = %s;", (parent_run_id,))
            row = cursor.fetchone()
            if row and row[0]:
                cursor.execute("SELECT content FROM messages WHERE id = %s;", (row[0],))
                message = cursor.fetchone()
                if message and str(message[0]).strip():
                    return str(message[0])
    for item in (fallback_state or {}).get("messages", []):
        if isinstance(item, dict) and item.get("role") == "user":
            content = str(item.get("content", "")).strip()
            if content and not content.startswith(("SYSTEM NOTE", "Attachment context", "Instrucciones", "Memorias", "MODE")):
                return content
    return None


def get_parent_run_id(child_run_id: int) -> int | None:
    with connect() as connection:
        with connection.cursor() as cursor:
            cursor.execute(
                "SELECT parent_run_id FROM agent_runs WHERE id = %s;",
                (child_run_id,),
            )
            row = cursor.fetchone()
            return row[0] if row else None


def dispatch_complete_observation(parent_run_id: int) -> str | None:
    dispatches = list_dispatches(parent_run_id)
    if not dispatches or any(dispatch["status"] in {"pending", "running", "awaiting_approval"} for dispatch in dispatches):
        return None
    sections = []
    for dispatch in dispatches:
        label = f"{dispatch['agent_name']} (goal: {dispatch['goal'][:120]})"
        if dispatch["status"] == "completed":
            sections.append(f"## {label}\n{dispatch['result'] or '(sin salida)'}")
        else:
            sections.append(f"## {label}\nFALLO: {dispatch['result'] or 'error desconocido'}")
    body = "\n\n".join(sections)[:30000]
    return f"TOOL RESULT ({DISPATCH_TOOL_NAME}):\n{body}"


def mark_child_completed_and_cascade(child_run_id: int, final_text: str) -> tuple[int, str] | None:
    """Records the child result; returns (parent_run_id, observation) when the whole dispatch finished."""
    update_dispatch(child_run_id, "completed", final_text)
    parent_run_id = get_parent_run_id(child_run_id)
    if parent_run_id is None:
        return None
    observation = dispatch_complete_observation(parent_run_id)
    if observation is None:
        return None
    return parent_run_id, observation


def build_child_approval_executor(user_id: int, conversation_id: int | None, child_run_id: int, registry):
    from ..workspace.routes import get_user_preferences

    preferences = get_user_preferences(user_id)
    policies = preferences.get("tool_policies") or {}

    def execute(name: str, args: dict) -> ToolResult:
        spec = registry.get(name).spec
        default_policy = "ask" if spec.permission == "sensitive" else "allow"
        policy = policies.get(name, default_policy)
        if policy == "block":
            return ToolResult(ok=False, output=f"Tool '{name}' is blocked by the user security policy.")
        if spec.permission == "sensitive" and policy == "ask":
            approval_id = create_tool_approval(child_run_id, user_id, conversation_id, name, args)
            raise ApprovalRequiredError(approval_id=approval_id, tool_name=name, args=args)
        return registry.run(name, args)

    return execute


def run_child(user_id: int, child_run_id: int, agent: ChildSpec, goal: str, workspace_root, conversation_id: int | None, trace_store: TraceStore) -> dict:
    from ..chat import specs as chat_specs

    registry = chat_specs.build_agent_tool_registry(user_id=user_id, workspace_root=workspace_root, agent_id=agent.id)
    tool_specs = chat_specs.get_agent_tool_specs(agent.id, user_id=user_id, workspace_root=workspace_root)
    executor = build_child_approval_executor(user_id, conversation_id, child_run_id, registry)
    loop = AgentLoop(trace_store=trace_store, execute_tool=executor)
    messages = [ChatMessage(role="user", content=goal)]

    def on_before_tool(name: str, args: dict, conversation) -> None:
        save_run_state(child_run_id, conversation, iterations=0, tool_call_count=0, thought_text="")

    try:
        response = "".join(
            loop.run(
                agent_run_id=child_run_id,
                system_prompt=agent.system_prompt,
                provider_type=agent.provider_type,
                provider_base_url=agent.provider_base_url,
                provider_api_key_env=agent.provider_api_key_env,
                model=agent.model,
                temperature=agent.temperature,
                tool_specs=tool_specs,
                messages=messages,
                guardrail_config=load_guardrail_config(),
                on_before_tool=on_before_tool,
                fallbacks=agent.fallbacks,
            )
        )
        trace_store.complete_run(child_run_id, response)
        return {"status": "completed", "result": response}
    except ApprovalRequiredError as error:
        trace_store.pause_run(child_run_id, f"awaiting approval #{error.approval_id} for {error.tool_name}")
        return {"status": "awaiting_approval", "approval_id": error.approval_id, "result": ""}
    except Exception as error:  # noqa: BLE001
        trace_store.fail_run(child_run_id, str(error))
        return {"status": "failed", "result": str(error)}


def available_agent_names() -> list[str]:
    """Enabled agent names, for corrective feedback when a model invents one."""
    try:
        with connect() as connection:
            with connection.cursor() as cursor:
                cursor.execute("SELECT name FROM agents WHERE enabled = true ORDER BY name;")
                return [row[0] for row in cursor.fetchall()]
    except Exception:  # noqa: BLE001 - best effort context for the model
        return []


def parse_tasks_arg(value) -> list | None:  # noqa: ANN001
    """Accepts the tasks argument as a list or as a JSON string.

    Local models running the XML tool-call format stringify nested structures
    (<arg_value>[{"agent": ...}]</arg_value> arrives as a raw string).
    Returns a list or None when unusable.
    """
    if isinstance(value, str):
        import json as _json

        try:
            parsed = _json.loads(value)
        except _json.JSONDecodeError:
            return None
        return parsed if isinstance(parsed, list) else None
    return value if isinstance(value, list) else None


class DispatchSubagentsTool:
    spec = DISPATCH_SPEC

    def __init__(self, user_id: int, parent_run_id: int, workspace_root, conversation_id: int | None, trace_store: TraceStore | None = None, context_message: str | None = None):
        self.user_id = user_id
        self.parent_run_id = parent_run_id
        self.workspace_root = workspace_root
        self.conversation_id = conversation_id
        self.trace_store = trace_store or TraceStore()
        self.context_message = (context_message or "").strip() or None

    def _goal_with_context(self, goal: str) -> str:
        if not self.context_message:
            return goal
        context = self.context_message
        if len(context) > MAX_CONTEXT_CHARS:
            context = context[:MAX_CONTEXT_CHARS] + "\n...[documento truncado: solo se muestran los primeros caracteres]"
        return (
            f"{goal}\n\n---\nContexto: mensaje original del usuario en la conversacion que delego esta tarea "
            f"(el sub-agente no ve la conversacion):\n{context}"
        )

    def run(self, args: dict) -> ToolResult:
        tasks = parse_tasks_arg(args.get("tasks"))
        if not isinstance(tasks, list) or not tasks:
            return ToolResult(ok=False, output="Missing required argument: tasks (list of {agent, goal}).")
        tasks = tasks[:MAX_SUBAGENTS]

        children: list[tuple[ChildSpec, str, int]] = []
        unknown_agents: list[str] = []
        for task in tasks:
            if not isinstance(task, dict):
                continue
            agent_name = str(task.get("agent", "")).strip()
            goal = str(task.get("goal", "")).strip()
            if not agent_name or not goal:
                continue
            agent = get_agent_spec_by_name(agent_name)
            if not agent:
                # A single hallucinated agent name must not abort the whole
                # dispatch: skip it and tell the model which agents exist.
                unknown_agents.append(agent_name)
                continue
            child_run_id = self.trace_store.create_run(
                self.user_id,
                self.conversation_id,
                None,
                agent.id,
                None,
                parent_run_id=self.parent_run_id,
            )
            create_dispatch(self.parent_run_id, child_run_id, agent_name, goal)
            self.trace_store.add_event(self.parent_run_id, "subagent_started", f"Sub-agent {agent_name} started", goal[:200])
            children.append((agent, self._goal_with_context(goal), child_run_id))

        if not children:
            return ToolResult(
                ok=False,
                output=(
                    f"None of the requested agents exist: {', '.join(unknown_agents) or 'none valid'}. "
                    f"Available agents: {', '.join(available_agent_names())}. "
                    "Retry dispatch_subagents with one task per existing agent."
                ),
            )

        if not children:
            return ToolResult(ok=False, output="No valid sub-agent tasks after filtering.")

        outcomes: dict[int, dict] = {}
        with ThreadPoolExecutor(max_workers=len(children)) as pool:
            futures = {
                pool.submit(run_child, self.user_id, child_run_id, agent, goal, self.workspace_root, self.conversation_id, self.trace_store): child_run_id
                for agent, goal, child_run_id in children
            }
            for future, child_run_id in futures.items():
                try:
                    outcomes[child_run_id] = future.result(timeout=SUBAGENT_TIMEOUT_SECONDS)
                except TimeoutError:
                    outcomes[child_run_id] = {"status": "failed", "result": f"Sub-agent timed out after {SUBAGENT_TIMEOUT_SECONDS}s."}

        pending_approval_id = None
        for agent, goal, child_run_id in children:
            outcome = outcomes.get(child_run_id, {"status": "failed", "result": "no outcome"})
            update_dispatch(child_run_id, outcome["status"], outcome.get("result", ""))
            self.trace_store.add_event(
                self.parent_run_id,
                "subagent_completed" if outcome["status"] != "failed" else "subagent_failed",
                f"Sub-agent {agent.name} {outcome['status']}",
                (outcome.get("result") or "")[:300],
            )
            if outcome["status"] == "awaiting_approval" and pending_approval_id is None:
                pending_approval_id = outcome.get("approval_id")

        if pending_approval_id is not None:
            raise ApprovalRequiredError(
                approval_id=pending_approval_id,
                tool_name=DISPATCH_TOOL_NAME,
                args=args,
            )

        observation = dispatch_complete_observation(self.parent_run_id)
        if not observation:
            observation = "Sub-agentes finalizados sin resultados."
        if unknown_agents:
            observation += (
                f"\n\nNOTA: estos agentes no existen y fueron omitidos: {', '.join(unknown_agents)}. "
                f"Agentes disponibles: {', '.join(available_agent_names())}."
            )
        return ToolResult(ok=True, output=observation[:30000])
