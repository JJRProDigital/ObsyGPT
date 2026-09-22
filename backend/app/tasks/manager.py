"""Background task manager: queue, concurrency, scheduling, pause/cancel/resume.

Each task runs the existing AgentLoop with its own guardrails and tool
permissions. Sensitive tools pause the task as 'awaiting_approval' and the
user decides from the Tareas view; approving resumes exactly where it stopped.
"""

import asyncio
import json
import threading
from datetime import timedelta

from ..agent.errors import ApprovalRequiredError, RunCancelledError
from . import store as task_store


TICK_SECONDS = 20
MAX_AUTO_ATTEMPTS = 3
RETRY_BACKOFF_SECONDS = 60
RESUME_TAIL = 12


def build_resume_prompt(goal: str, events: list[dict]) -> str:
    """Rebuilds task context so a resumed task never repeats completed work."""
    history = [
        event
        for event in events
        if event.get("event_type") == "tool_step" or event.get("event_type") == "task_update"
    ]
    if not history:
        return goal

    done_lines = []
    for event in history[-RESUME_TAIL:]:
        summary = str(event.get("content") or "").replace("\n", " ")[:160]
        mark = "ok" if event.get("event_type") == "tool_step" else "info"
        done_lines.append(f"- {event.get('title', 'paso')} [{mark}]" + (f": {summary}" if summary else ""))

    parts = [
        "[REANUDACION] Esta tarea ya se estaba ejecutando y ahora se retoma. NO repitas acciones ya completadas; continua desde donde se quedo.",
        f"Objetivo: {goal}",
    ]
    if done_lines:
        parts.append("Progreso registrado (lo mas reciente):\n" + "\n".join(done_lines))
    return "\n\n".join(parts)


class TaskManager:
    def __init__(self):
        self.runners: dict[int, object] = {}
        self.cancel_flags: dict[int, threading.Event] = {}
        self.pause_requested: set[int] = set()
        self._tick_task: asyncio.Task | None = None
        self._loop: asyncio.AbstractEventLoop | None = None

    # ---------- lifecycle ----------

    async def start(self) -> dict:
        self._loop = asyncio.get_running_loop()
        self._tick_task = asyncio.create_task(self._tick_loop())
        return self.auto_resume()

    def _require_loop(self) -> asyncio.AbstractEventLoop:
        loop = self._loop
        if loop is None or loop.is_closed():
            raise RuntimeError("TaskManager is not started; call await manager.start() from the app lifespan.")
        return loop

    def _spawn(self, coro) -> object:  # noqa: ANN001
        """Schedules a coroutine on the manager loop; safe to call from sync worker threads."""
        return asyncio.run_coroutine_threadsafe(coro, self._require_loop())

    async def stop(self) -> None:
        if self._tick_task:
            self._tick_task.cancel()
            self._tick_task = None
        for task_id, runner in list(self.runners.items()):
            runner.cancel()
            flag = self.cancel_flags.get(task_id)
            if flag:
                flag.set()
        self.runners.clear()
        self.cancel_flags.clear()

    # ---------- public API ----------

    def enqueue(self, user_id: int, goal: str, mode: str = "act", scheduled_at=None, agent_id: int | None = None, project_id: int | None = None, recurrence: str | None = None) -> dict:
        status = "pending"
        if scheduled_at is not None:
            status = "scheduled"
        task = task_store.create_task(user_id, goal, mode=mode, scheduled_at=scheduled_at, agent_id=agent_id, project_id=project_id, recurrence=recurrence, status=status)
        task_store.record_event(task["id"], "task_update", f"Tarea {'programada' if status == 'scheduled' else 'en cola'}")
        self.pump()
        return task

    def pause(self, task_id: int) -> bool:
        task = task_store.get_task(task_id)
        if not task:
            return False
        status = task["status"]
        if status == "running":
            self.pause_requested.add(task_id)
            flag = self.cancel_flags.get(task_id)
            if flag:
                flag.set()
            return True
        if status in {"pending", "scheduled"}:
            task_store.set_task_status(task_id, "paused")
            task_store.record_event(task_id, "task_update", "Tarea pausada (estaba en cola)")
            return True
        if status == "paused":
            return True
        return False

    def resume(self, task_id: int) -> bool:
        task = task_store.get_task(task_id)
        if not task:
            return False
        if task["status"] not in {"paused", "interrupted", "failed", "pending"}:
            return False
        task_store.update_task_fields(task_id, attempts=0, next_attempt_at=None)
        # A paused task that still has a future schedule goes back to
        # "scheduled" instead of jumping the queue as "pending".
        scheduled_at = task.get("scheduled_at")
        if isinstance(scheduled_at, str):
            try:
                scheduled_at = datetime.fromisoformat(scheduled_at)
            except ValueError:
                scheduled_at = None
        if scheduled_at is not None:
            if scheduled_at.tzinfo is None:
                scheduled_at = scheduled_at.replace(tzinfo=timezone.utc)
            if scheduled_at > datetime.now(timezone.utc):
                task_store.set_task_status(task_id, "scheduled")
                task_store.record_event(task_id, "task_update", "Tarea reanudada - mantiene su programacion")
                return True
        task_store.set_task_status(task_id, "pending")
        task_store.record_event(task_id, "task_update", "Tarea reanudada - en cola")
        self.pump()
        return True

    def cancel(self, task_id: int, reason: str = "Cancelada por el usuario") -> bool:
        task = task_store.get_task(task_id)
        if not task or task["status"] in {"completed", "failed", "cancelled"}:
            return False
        if task["status"] == "running":
            flag = self.cancel_flags.get(task_id)
            if flag:
                flag.set()
            return True
        task_store.set_task_status(task_id, "cancelled", error=reason)
        task_store.record_event(task_id, "task_update", "Tarea cancelada")
        return True

    def remove(self, task_id: int) -> bool:
        task = task_store.get_task(task_id)
        if not task:
            return False
        if task["status"] == "running":
            flag = self.cancel_flags.get(task_id)
            if flag:
                flag.set()
        task_store.delete_task(task_id)
        return True

    def pump(self) -> None:
        max_concurrent = int(task_store.get_tasks_settings().get("max_concurrent_tasks", 1))
        max_concurrent = max(1, min(4, max_concurrent))
        if len(self.runners) >= max_concurrent:
            return
        pendings = [t for t in task_store.list_tasks_by_status(["pending"]) if t["id"] not in self.runners]
        for task in pendings:
            if len(self.runners) >= max_concurrent:
                break
            self._start(task)

    def auto_resume(self) -> dict:
        settings = task_store.get_tasks_settings()
        resumed = 0
        abandoned = 0
        if settings.get("auto_resume_tasks", True):
            for task in task_store.list_tasks_by_status(["interrupted"]):
                if int(task.get("attempts") or 0) >= MAX_AUTO_ATTEMPTS:
                    task_store.set_task_status(task["id"], "failed", error="Sin reanudar: reintentos automaticos agotados")
                    task_store.record_event(task["id"], "task_update", "Tarea no reanudada: reintentos agotados")
                    abandoned += 1
                    continue
                if task.get("next_attempt_at") is not None:
                    from datetime import datetime, timezone

                    next_at = task["next_attempt_at"]
                    if isinstance(next_at, str):
                        try:
                            next_at = datetime.fromisoformat(next_at)
                        except ValueError:
                            next_at = None
                    if next_at and next_at.tzinfo is None:
                        next_at = next_at.replace(tzinfo=timezone.utc)
                    if next_at and next_at > datetime.now(timezone.utc):
                        continue
                attempts = int(task.get("attempts") or 0) + 1
                backoff = RETRY_BACKOFF_SECONDS * (2 ** min(attempts - 1, 6))
                task_store.update_task_fields(
                    task["id"],
                    attempts=attempts,
                    next_attempt_at=task_store.now_utc() + timedelta(seconds=backoff),
                )
                task_store.set_task_status(task["id"], "pending")
                task_store.record_event(task["id"], "task_update", "Tarea interrumpida recuperada - en cola")
                resumed += 1
        self.pump()
        return {"resumed": resumed, "abandoned": abandoned}

    # ---------- internal engine ----------

    def _start(self, task: dict) -> None:
        task_id = task["id"]
        task_store.set_task_status(task_id, "running")
        flag = threading.Event()
        self.cancel_flags[task_id] = flag
        self.runners[task_id] = self._spawn(self._run_task(task, flag))

    async def _run_task(self, task: dict, flag: threading.Event) -> None:
        task_id = task["id"]
        try:
            project = None
            if task.get("project_id"):
                from ..projects.store import get_project

                project = get_project(task["project_id"], task["user_id"])
            outcome = await asyncio.to_thread(
                self._execute_task_sync,
                task_id=task_id,
                user_id=task["user_id"],
                agent_id=task.get("agent_id"),
                goal=task["goal"],
                mode=task.get("mode", "act"),
                flag=flag,
                project=project,
            )
            self._apply_outcome(task_id, outcome)
        except asyncio.CancelledError:
            task_store.set_task_status(task_id, "interrupted", error="Detenida al cerrar la aplicacion")
        except Exception as error:  # noqa: BLE001
            self._note_failure(task_id, str(error))
        finally:
            self.cancel_flags.pop(task_id, None)
            self.runners.pop(task_id, None)
            self.pause_requested.discard(task_id)
            self.pump()

    def _apply_outcome(self, task_id: int, outcome: dict) -> None:
        kind = outcome.get("outcome")
        if kind == "completed":
            task_store.set_task_status(task_id, "completed", result=outcome.get("text", ""))
            task_store.record_event(task_id, "task_update", "Tarea completada")
            self._maybe_schedule_recurrence(task_id)
        elif kind == "awaiting_approval":
            task_store.set_task_status(task_id, "awaiting_approval")
            task_store.record_event(task_id, "task_update", f"Esperando aprobacion: {outcome.get('tool_name', 'herramienta')}")
        elif kind == "cancelled":
            if task_id in self.pause_requested:
                self.pause_requested.discard(task_id)
                task_store.set_task_status(task_id, "paused")
                task_store.record_event(task_id, "task_update", "Tarea pausada")
            else:
                task_store.set_task_status(task_id, "cancelled", error="Cancelada por el usuario")
                task_store.record_event(task_id, "task_update", "Tarea cancelada")
        elif kind == "failed":
            self._note_failure(task_id, outcome.get("error", "Error desconocido"))

    def _note_failure(self, task_id: int, message: str) -> None:
        task = task_store.get_task(task_id)
        if not task or task["status"] in {"cancelled", "completed"}:
            return
        attempts = int(task.get("attempts") or 0) + 1
        backoff = RETRY_BACKOFF_SECONDS * (2 ** min(attempts - 1, 6))
        task_store.update_task_fields(
            task_id,
            attempts=attempts,
            next_attempt_at=task_store.now_utc() + timedelta(seconds=backoff),
        )
        task_store.set_task_status(task_id, "failed", error=message[:2000])
        task_store.record_event(task_id, "task_update", f"Tarea fallo: {message[:160]}")

    # ---------- sync execution (runs in a worker thread) ----------

    def _maybe_schedule_recurrence(self, task_id: int) -> None:
        """Clones a completed recurring task as its next scheduled occurrence."""
        task = task_store.get_task(task_id)
        if not task or not task.get("recurrence"):
            return
        from datetime import datetime, timedelta, timezone

        recurrence = task["recurrence"]
        now = datetime.now(timezone.utc)
        next_at = now + (timedelta(days=1) if recurrence == "daily" else timedelta(days=7))
        task_store.mark_last_occurrence(task_id)
        clone = task_store.create_task(
            task["user_id"],
            task["goal"],
            mode=task.get("mode", "act"),
            scheduled_at=next_at,
            agent_id=task.get("agent_id"),
            project_id=task.get("project_id"),
            recurrence=recurrence,
        )
        task_store.record_event(clone["id"], "task_update", f"Tarea recurrente ({recurrence}) programada para la siguiente ocurrencia")

    def _execute_task_sync(self, task_id: int, user_id: int, agent_id, goal: str, mode: str, flag: threading.Event, project: dict | None = None) -> dict:
        from ..agent.runtime import AgentLoop
        from ..agent.settings import load_guardrail_config
        from ..agent.store import create_tool_approval, save_run_state
        from ..agent import store as agent_store
        from ..chat import specs as chat_specs
        from ..providers import ChatMessage
        from ..traces.store import TraceStore

        agent = chat_specs.get_agent_spec(agent_id)
        project_folder = (project or {}).get("folder_path") or None
        registry = chat_specs.build_agent_tool_registry(user_id=user_id, workspace_root=project_folder, agent_id=agent.id)
        tool_specs = chat_specs.get_agent_tool_specs(agent.id, user_id=user_id, workspace_root=project_folder)
        trace_store = TraceStore()
        agent_run_id = trace_store.create_run(user_id, None, None, agent.id, None)
        from ..agent.subagents import DispatchSubagentsTool

        if any(spec.name == "dispatch_subagents" for spec in tool_specs):
            registry.register(DispatchSubagentsTool(user_id, agent_run_id, project_folder, None, trace_store, context_message=goal))

        from ..monitoring import otel

        otel.bind_context(**{"user.id": user_id, "session.id": f"task:{task_id}", "prompt.id": agent_run_id})
        otel.record_user_prompt(len(goal), goal)

        prompt = build_resume_prompt(goal, task_store.list_events(task_id))
        project_instructions = ((project or {}).get("instructions") or "").strip()
        if project_instructions:
            project_name = (project or {}).get("name", "proyecto")
            prompt = f"{prompt}\n\nInstrucciones del proyecto '{project_name}' (aplicalas en esta tarea):\n{project_instructions}"
        messages = [ChatMessage(role="user", content=prompt)]
        directive = chat_specs.build_mode_directive(mode)
        if directive:
            messages.append(ChatMessage(role="user", content=directive))

        def execute(name: str, args: dict):
            spec = registry.get(name).spec
            if spec.permission == "sensitive":
                approval_id = create_tool_approval(agent_run_id, user_id, None, name, args, task_id=task_id)
                raise ApprovalRequiredError(approval_id=approval_id, tool_name=name, args=args)
            return registry.run(name, args)

        def on_before_tool(name: str, args: dict, conversation) -> None:
            task_store.record_event(task_id, "tool_step", f"Paso: {name}", json.dumps(args, default=str)[:400])
            save_run_state(agent_run_id, conversation, iterations=0, tool_call_count=0, thought_text="")

        loop = AgentLoop(trace_store=trace_store, execute_tool=execute)
        chunks: list[str] = []
        try:
            for token in loop.run(
                agent_run_id=agent_run_id,
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
                should_continue=lambda: not flag.is_set(),
            ):
                chunks.append(token)
        except ApprovalRequiredError as error:
            return {"outcome": "awaiting_approval", "approval_id": error.approval_id, "tool_name": error.tool_name, "partial": "".join(chunks)}
        except RunCancelledError:
            return {"outcome": "cancelled"}
        except Exception as error:  # noqa: BLE001
            return {"outcome": "failed", "error": str(error)}

        return {"outcome": "completed", "text": "".join(chunks)}

    def _execute_approval_resume_sync(self, user_id: int, approval: dict, approved: bool) -> dict:
        from ..agent.runtime import AgentLoop
        from ..agent.settings import load_guardrail_config
        from ..agent.store import get_run_config, load_run_state, save_run_state, set_run_status
        from ..agent import store as agent_store
        from ..chat import specs as chat_specs
        from ..providers import ChatMessage
        from ..traces.store import TraceStore

        def _last_user_message(state: dict | None) -> str | None:
            for item in (state or {}).get("messages", []):
                if isinstance(item, dict) and item.get("role") == "user":
                    return str(item.get("content", ""))
            return None

        task_id = approval["task_id"]
        run_config = get_run_config(approval["agent_run_id"])
        state = load_run_state(approval["agent_run_id"])
        if not run_config or not state:
            return {"outcome": "failed", "error": "Run state not found for this task approval."}

        def _task_workspace() -> str | None:
            """Re-derives the task's project folder so resumes keep the same sandbox."""
            from ..projects.store import get_project

            task_row = task_store.get_task(task_id)
            if task_row and task_row.get("project_id"):
                project = get_project(task_row["project_id"], task_row["user_id"])
                return (project or {}).get("folder_path")
            return None

        task_workspace = _task_workspace()
        registry = chat_specs.build_agent_tool_registry(user_id=user_id, workspace_root=task_workspace, agent_id=run_config.get("agent_id"))
        permissions = agent_store.get_agent_tool_permissions(run_config.get("agent_id"))
        trace_store = TraceStore()
        from ..agent.subagents import DISPATCH_SPEC, DispatchSubagentsTool

        if permissions.get(DISPATCH_SPEC.name) and not any(spec.name == DISPATCH_SPEC.name for spec in registry.list_specs()):
            registry.register(DispatchSubagentsTool(user_id, approval["agent_run_id"], task_workspace, None, trace_store, context_message=_last_user_message(state)))
        tool_specs = [spec for spec in registry.list_specs() if permissions.get(spec.name, False)]

        tool_name = approval["tool_name"]
        tool_args = approval["args"] if isinstance(approval["args"], dict) else {}
        if approved:
            try:
                result = registry.get(tool_name).run(tool_args)
            except ApprovalRequiredError as child_error:
                return {"outcome": "awaiting_approval", "approval_id": child_error.approval_id, "tool_name": child_error.tool_name}
            except Exception as error:  # noqa: BLE001 - tool crash must not leave a zombie task: report it to the model
                trace_store.add_event(approval["agent_run_id"], "tool_failed", f"{tool_name} failed after approval", repr(error)[:500])
                result = type("FailedTool", (), {"output": f"The approved tool call FAILED to execute: {error}. Explain the problem and propose an alternative."})()
            observation = f"TOOL RESULT ({tool_name}):\n{result.output[:10000]}"
        else:
            observation = f"TOOL RESULT ({tool_name}):\nEl usuario rechazo esta herramienta. Explica la limitacion y propone una alternativa."

        conversation = [
            ChatMessage(role=item.get("role", "user"), content=item.get("content", ""))
            for item in state.get("messages", [])
            if isinstance(item, dict)
        ]
        messages = [*conversation, ChatMessage(role="user", content=observation)]
        flag = self.cancel_flags.setdefault(task_id, threading.Event())

        def execute(name: str, args: dict):
            from ..agent.store import create_tool_approval

            spec = registry.get(name).spec
            if spec.permission == "sensitive":
                approval_id = create_tool_approval(approval["agent_run_id"], user_id, None, name, args, task_id=task_id)
                raise ApprovalRequiredError(approval_id=approval_id, tool_name=name, args=args)
            return registry.run(name, args)

        def on_before_tool(name: str, args: dict, convo) -> None:
            task_store.record_event(task_id, "tool_step", f"Paso: {name}", json.dumps(args, default=str)[:400])
            save_run_state(approval["agent_run_id"], convo, iterations=0, tool_call_count=0, thought_text="")

        loop = AgentLoop(trace_store=trace_store, execute_tool=execute)
        chunks: list[str] = []
        try:
            for token in loop.run(
                agent_run_id=approval["agent_run_id"],
                system_prompt=run_config["system_prompt"],
                provider_type=run_config["provider_type"],
                provider_base_url=run_config["base_url"],
                provider_api_key_env=run_config["api_key_env"],
                model=run_config["model_name"],
                temperature=float(run_config["temperature"]),
                tool_specs=tool_specs,
                messages=messages,
                guardrail_config=load_guardrail_config(),
                on_before_tool=on_before_tool,
                should_continue=lambda: not flag.is_set(),
            ):
                chunks.append(token)
        except ApprovalRequiredError as error:
            from ..agent.subagents import update_dispatch

            update_dispatch(approval["agent_run_id"], "awaiting_approval")
            return {"outcome": "awaiting_approval", "approval_id": error.approval_id, "tool_name": error.tool_name}
        except RunCancelledError:
            return {"outcome": "cancelled"}
        except Exception as error:  # noqa: BLE001
            return {"outcome": "failed", "error": str(error)}

        child_text = "".join(chunks)
        from ..agent.subagents import mark_child_completed_and_cascade

        cascade = mark_child_completed_and_cascade(approval["agent_run_id"], child_text)
        if cascade:
            parent_run_id, observation = cascade
            parent_config = get_run_config(parent_run_id)
            parent_state = load_run_state(parent_run_id)
            if parent_config and parent_state:
                from ..agent.subagents import DispatchSubagentsTool

                parent_registry = chat_specs.build_agent_tool_registry(user_id=user_id, workspace_root=task_workspace, agent_id=parent_config.get("agent_id"))
                parent_registry.register(DispatchSubagentsTool(user_id, parent_run_id, task_workspace, None, trace_store, context_message=_last_user_message(parent_state)))
                parent_permissions = agent_store.get_agent_tool_permissions(parent_config.get("agent_id"))
                parent_specs = [spec for spec in parent_registry.list_specs() if parent_permissions.get(spec.name, False)]
                parent_conversation = [
                    ChatMessage(role=item.get("role", "user"), content=item.get("content", ""))
                    for item in parent_state.get("messages", [])
                    if isinstance(item, dict)
                ]
                parent_messages = [*parent_conversation, ChatMessage(role="user", content=observation)]
                set_run_status(parent_run_id, "running")

                def parent_execute(name: str, args: dict):
                    from ..agent.store import create_tool_approval as create_approval

                    spec = parent_registry.get(name).spec
                    if spec.permission == "sensitive":
                        approval_id = create_approval(parent_run_id, user_id, None, name, args, task_id=task_id)
                        raise ApprovalRequiredError(approval_id=approval_id, tool_name=name, args=args)
                    return parent_registry.run(name, args)

                def parent_before_tool(name: str, args: dict, conversation) -> None:
                    save_run_state(parent_run_id, conversation, iterations=0, tool_call_count=0, thought_text="")

                parent_loop = AgentLoop(trace_store=trace_store, execute_tool=parent_execute)
                parent_chunks: list[str] = []
                try:
                    for token in parent_loop.run(
                        agent_run_id=parent_run_id,
                        system_prompt=parent_config["system_prompt"],
                        provider_type=parent_config["provider_type"],
                        provider_base_url=parent_config["base_url"],
                        provider_api_key_env=parent_config["api_key_env"],
                        model=parent_config["model_name"],
                        temperature=float(parent_config["temperature"]),
                        tool_specs=parent_specs,
                        messages=parent_messages,
                        guardrail_config=load_guardrail_config(),
                        on_before_tool=parent_before_tool,
                        should_continue=lambda: not flag.is_set(),
                    ):
                        parent_chunks.append(token)
                except ApprovalRequiredError as error:
                    return {"outcome": "awaiting_approval", "approval_id": error.approval_id, "tool_name": error.tool_name}
                except RunCancelledError:
                    return {"outcome": "cancelled"}
                except Exception as error:  # noqa: BLE001
                    return {"outcome": "failed", "error": str(error)}
                return {"outcome": "completed", "text": "".join(parent_chunks)}

        return {"outcome": "completed", "text": child_text}

    def resume_after_approval(self, user_id: int, task_id: int, approval: dict, approved: bool) -> None:
        task_store.set_task_status(task_id, "running")
        task_store.record_event(task_id, "task_update", "Aprobacion decidida - continuando tarea")
        flag = self.cancel_flags.setdefault(task_id, threading.Event())

        async def runner() -> None:
            try:
                outcome = await asyncio.to_thread(self._execute_approval_resume_sync, user_id, approval, approved)
                self._apply_outcome(task_id, outcome)
            except asyncio.CancelledError:
                task_store.set_task_status(task_id, "interrupted", error="Detenida al cerrar la aplicacion")
            except Exception as error:  # noqa: BLE001
                self._note_failure(task_id, str(error))
            finally:
                self.cancel_flags.pop(task_id, None)
                self.runners.pop(task_id, None)
                self.pump()

        self.runners[task_id] = self._spawn(runner())

    async def _tick_loop(self) -> None:
        while True:
            try:
                await asyncio.sleep(TICK_SECONDS)
                due = False
                for task in task_store.list_tasks_by_status(["scheduled"]):
                    scheduled_at = task.get("scheduled_at")
                    if scheduled_at is None:
                        continue
                    from datetime import datetime, timezone

                    if isinstance(scheduled_at, str):
                        try:
                            scheduled_at = datetime.fromisoformat(scheduled_at)
                        except ValueError:
                            continue
                    if scheduled_at.tzinfo is None:
                        scheduled_at = scheduled_at.replace(tzinfo=timezone.utc)
                    if scheduled_at <= datetime.now(timezone.utc):
                        task_store.set_task_status(task["id"], "pending")
                        task_store.record_event(task["id"], "task_update", "Tarea programada: llega la hora")
                        due = True
                if due or task_store.list_tasks_by_status(["pending"]):
                    self.pump()
            except asyncio.CancelledError:
                return
            except Exception:  # noqa: BLE001
                continue
