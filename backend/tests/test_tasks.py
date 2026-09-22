import asyncio
import threading

import pytest

from app.agent.errors import ApprovalRequiredError
from app.tasks import manager as tasks_manager
from app.tasks.manager import TaskManager, build_resume_prompt
from app.tasks.routes import TaskCreatePayload


class FakeRequest:
    session = {"user_id": 1, "role": "admin"}


class FakeStore:
    def __init__(self):
        self.tasks: dict[int, dict] = {}
        self.events: dict[int, list[dict]] = {}
        self.deleted: list[int] = []
        self.next_id = 1

    def create_task(self, user_id, goal, mode="act", scheduled_at=None, agent_id=None, project_id=None, recurrence=None, status=None):
        task_id = self.next_id
        self.next_id += 1
        if status is None:
            status = "scheduled" if scheduled_at else "pending"
        task = {
            "id": task_id,
            "user_id": user_id,
            "goal": goal,
            "mode": mode,
            "status": status,
            "scheduled_at": scheduled_at,
            "attempts": 0,
            "next_attempt_at": None,
            "agent_id": agent_id,
            "project_id": project_id,
            "recurrence": recurrence,
        }
        self.tasks[task_id] = task
        return dict(task)

    def list_tasks_by_status(self, statuses):
        return [dict(task) for task in self.tasks.values() if task["status"] in statuses]

    def get_task(self, task_id, user_id=None):
        task = self.tasks.get(task_id)
        if not task or (user_id is not None and task["user_id"] != user_id):
            return None
        return dict(task)

    def set_task_status(self, task_id, status, result=None, error=None):
        task = self.tasks[task_id]
        task["status"] = status
        if result is not None:
            task["result"] = result
        if error is not None:
            task["error"] = error

    def update_task_fields(self, task_id, attempts=None, next_attempt_at=None):
        task = self.tasks[task_id]
        if attempts is not None:
            task["attempts"] = attempts
        if next_attempt_at is not None:
            task["next_attempt_at"] = next_attempt_at

    def record_event(self, task_id, event_type, title, content=""):
        self.events.setdefault(task_id, []).append({"event_type": event_type, "title": title, "content": content})

    def list_events(self, task_id):
        return list(self.events.get(task_id, []))

    def delete_task(self, task_id):
        self.deleted.append(task_id)
        self.tasks.pop(task_id, None)

    def get_tasks_settings(self):
        return {"max_concurrent_tasks": 1, "auto_resume_tasks": True}

    def now_utc(self):
        from datetime import datetime, timezone

        return datetime.now(timezone.utc)


@pytest.fixture
def manager(monkeypatch):
    fake = FakeStore()
    monkeypatch.setattr(tasks_manager, "task_store", fake)
    tm = TaskManager()
    tm.store = fake
    return tm


def run(coro):
    return asyncio.new_event_loop().run_until_complete(coro)


def test_build_resume_prompt_includes_goal_and_progress():
    prompt = build_resume_prompt(
        "buscar precios",
        [
            {"event_type": "tool_step", "title": "Paso: web_fetch", "content": "https://a.com"},
            {"event_type": "task_update", "title": "Tarea en cola", "content": ""},
        ],
    )

    assert "[REANUDACION]" in prompt
    assert "Objetivo: buscar precios" in prompt
    assert "Paso: web_fetch" in prompt


def test_build_resume_prompt_first_run_returns_goal():
    assert build_resume_prompt("objetivo", []) == "objetivo"


def test_enqueue_creates_pending_task_and_pumps(manager, monkeypatch):
    started = []
    monkeypatch.setattr(manager, "_start", lambda task: started.append(task["id"]))
    task = manager.enqueue(2, "revisa informe")

    assert task["status"] == "pending"
    assert started == [task["id"]]


def test_enqueue_with_schedule_marks_scheduled(manager, monkeypatch):
    monkeypatch.setattr(manager, "_start", lambda task: None)
    from datetime import datetime, timezone

    task = manager.enqueue(2, "informe nocturno", scheduled_at=datetime.now(timezone.utc) + timedelta_hours(1))

    assert task["status"] == "scheduled"


def timedelta_hours(hours):
    from datetime import timedelta

    return timedelta(hours=hours)


def test_pause_pending_marks_paused(manager):
    task = manager.store.create_task(2, "tarea")

    assert manager.pause(task["id"]) is True
    assert manager.store.tasks[task["id"]]["status"] == "paused"


def test_resume_resets_attempts_and_requeues(manager, monkeypatch):
    monkeypatch.setattr(manager, "_start", lambda task: None)
    task = manager.store.create_task(2, "tarea")
    manager.store.set_task_status(task["id"], "failed")
    manager.store.update_task_fields(task["id"], attempts=3)

    assert manager.resume(task["id"]) is True
    assert manager.store.tasks[task["id"]]["status"] == "pending"
    assert manager.store.tasks[task["id"]]["attempts"] == 0


def test_cancel_running_sets_flag(manager):
    task = manager.store.create_task(2, "tarea")
    manager.store.set_task_status(task["id"], "running")
    manager.cancel_flags[task["id"]] = threading.Event()

    assert manager.cancel(task["id"]) is True
    assert manager.cancel_flags[task["id"]].is_set()


def test_apply_outcome_completed(manager):
    task = manager.store.create_task(2, "tarea")
    manager._apply_outcome(task["id"], {"outcome": "completed", "text": "resultado"})

    assert manager.store.tasks[task["id"]]["status"] == "completed"
    assert manager.store.tasks[task["id"]]["result"] == "resultado"


def test_apply_outcome_awaiting_approval(manager):
    task = manager.store.create_task(2, "tarea")
    manager._apply_outcome(task["id"], {"outcome": "awaiting_approval", "tool_name": "run_command"})

    assert manager.store.tasks[task["id"]]["status"] == "awaiting_approval"


def test_note_failure_increments_attempts_with_backoff(manager):
    task = manager.store.create_task(2, "tarea")

    manager._note_failure(task["id"], "boom")
    manager._note_failure(task["id"], "boom 2")

    stored = manager.store.tasks[task["id"]]
    assert stored["attempts"] == 2
    assert stored["status"] == "failed"
    assert stored["next_attempt_at"] is not None


def test_auto_resume_recovers_interrupted_and_abandons_exhausted(manager, monkeypatch):
    monkeypatch.setattr(manager, "pump", lambda: None)
    recovered = manager.store.create_task(2, "recuperable")
    manager.store.set_task_status(recovered["id"], "interrupted")

    exhausted = manager.store.create_task(2, "agotada")
    manager.store.set_task_status(exhausted["id"], "interrupted")
    manager.store.update_task_fields(exhausted["id"], attempts=3)

    summary = manager.auto_resume()

    assert summary == {"resumed": 1, "abandoned": 1}
    assert manager.store.tasks[recovered["id"]]["status"] == "pending"
    assert manager.store.tasks[exhausted["id"]]["status"] == "failed"


def test_execute_task_sync_awaits_approval_on_sensitive_tool(manager, monkeypatch):
    class FakeAgentSpec:
        id = 1
        system_prompt = "s"
        provider_type = "llamacpp"
        provider_base_url = None
        provider_api_key_env = None
        model = "gemma"
        temperature = 0.7
        fallbacks = None

    class FakeRegistry:
        class _Spec:
            def __init__(self, permission):
                self.permission = permission

        def get(self, name):
            return type("Tool", (), {"spec": FakeRegistry._Spec("sensitive")})()

        def run(self, name, args):
            raise AssertionError("no debe ejecutarse")

    class FakeTraceStore:
        def create_run(self, *args, **kwargs):
            return 99

        def add_event(self, *args, **kwargs):
            return None

        def add_tool_call(self, *args, **kwargs):
            return None

    captured = {}

    def fake_create_approval(agent_run_id, user_id, conversation_id, tool_name, args, task_id=None):
        captured.update({"tool_name": tool_name, "task_id": task_id})
        return 7

    import app.tasks.manager as m

    monkeypatch.setattr("app.chat.specs.get_agent_spec", lambda agent_id: FakeAgentSpec(), raising=False)
    monkeypatch.setattr("app.chat.specs.build_agent_tool_registry", lambda user_id=None, workspace_root=None, agent_id=None: FakeRegistry(), raising=False)

    from app.agent.tools.base import ToolSpec

    monkeypatch.setattr(
        "app.chat.specs.get_agent_tool_specs",
        lambda agent_id, user_id=None, workspace_root=None: [ToolSpec(name="run_command", description="ejecuta", parameters="{}", permission="sensitive")],
        raising=False,
    )
    monkeypatch.setattr("app.chat.specs.build_mode_directive", lambda mode: None, raising=False)
    monkeypatch.setattr("app.agent.store.create_tool_approval", fake_create_approval)
    monkeypatch.setattr("app.agent.store.save_run_state", lambda *args, **kwargs: None)
    monkeypatch.setattr("app.traces.store.TraceStore.create_run", lambda self, *args, **kwargs: 99)
    monkeypatch.setattr("app.traces.store.TraceStore.add_event", lambda self, *args, **kwargs: None)

    from app.agent.protocol import PROTOCOL_MARKER_CLOSE, PROTOCOL_MARKER_OPEN

    class FakeProviderRegistry:
        def stream_chat_with_config(self, provider_type, request, api_key_env=None, base_url=None):
            yield "Paso previo. "
            yield PROTOCOL_MARKER_OPEN + '\n{"tool": "run_command", "args": {"command": "dir"}}\n' + PROTOCOL_MARKER_CLOSE

    from app.agent.runtime import AgentLoop

    original_init = AgentLoop.__init__

    def patched_init(self, provider_registry=None, trace_store=None, execute_tool=None):
        original_init(self, provider_registry=FakeProviderRegistry(), trace_store=FakeTraceStore(), execute_tool=execute_tool)

    monkeypatch.setattr(AgentLoop, "__init__", patched_init)

    task = manager.store.create_task(2, "ejecuta dir")
    outcome = manager._execute_task_sync(
        task_id=task["id"],
        user_id=2,
        agent_id=1,
        goal="ejecuta dir",
        mode="act",
        flag=threading.Event(),
    )

    assert outcome["outcome"] == "awaiting_approval", outcome
    assert captured["tool_name"] == "run_command"
    assert captured["task_id"] == task["id"]


def test_task_create_payload_validates_mode_and_schedule():
    payload = TaskCreatePayload(goal="informe", mode="plan", scheduled_at="2026-09-16T10:00:00")

    assert payload.mode == "plan"
    assert payload.parsed_scheduled_at() is not None

    with pytest.raises(Exception):
        TaskCreatePayload(goal="x", mode="vago")

    with pytest.raises(Exception):
        TaskCreatePayload(goal="x", scheduled_at="no-fecha").parsed_scheduled_at()


def test_tasks_settings_roundtrip(monkeypatch):
    from app.admin.routes import TasksSettingsPayload, list_tasks_settings, update_tasks_settings

    monkeypatch.setattr("app.auth.routes.require_admin", lambda request: 1)
    monkeypatch.setattr(
        "app.admin.queries.fetch_one",
        lambda query, params=(): ({"value": {"max_concurrent_tasks": 2, "auto_resume_tasks": False}} if "tasks" in query else None),
    )

    result = list_tasks_settings(FakeRequest())

    assert result == {"tasks": {"max_concurrent_tasks": 2, "auto_resume_tasks": False}}

    import json as json_module

    def fake_execute_returning(query, params):
        return {"value": json_module.loads(params[0])}

    monkeypatch.setattr("app.admin.queries.execute_returning", fake_execute_returning)
    monkeypatch.setattr(
        "app.audit.AuditStore",
        lambda: type("FakeAuditStore", (), {"add_log": lambda self, *args, **kwargs: None})(),
    )

    updated = update_tasks_settings(TasksSettingsPayload(max_concurrent_tasks=4, auto_resume_tasks=True), FakeRequest())

    assert updated == {"tasks": {"max_concurrent_tasks": 4, "auto_resume_tasks": True}}


def test_build_resume_prompt_builds_from_task_events():
    events = [
        {"event_type": "task_update", "title": "Tarea en cola", "content": ""},
        {"event_type": "tool_step", "title": "Paso: read_file", "content": "leido README"},
    ]

    prompt = tasks_manager.build_resume_prompt("revisa el proyecto", events)

    assert "Objetivo: revisa el proyecto" in prompt
    assert "Paso: read_file" in prompt
    assert "leido README" in prompt

def test_enqueue_passes_status_to_store(monkeypatch):
    """Regression: enqueue computed status="scheduled" but never passed it to
    create_task, whose INSERT hardcoded "pending" - scheduled tasks ran immediately."""
    captured = {}

    class CapturingStore:
        def create_task(self, user_id, goal, mode="act", scheduled_at=None, agent_id=None, project_id=None, recurrence=None, status="pending"):
            captured["status"] = status
            captured["scheduled_at"] = scheduled_at
            return {"id": 1, "status": status}

        def record_event(self, task_id, event_type, title, content=""):
            pass

        def get_tasks_settings(self):
            return {"max_concurrent_tasks": 1}

        def list_tasks_by_status(self, statuses):
            return []

    monkeypatch.setattr(tasks_manager, "task_store", CapturingStore())
    manager = TaskManager()

    from datetime import datetime, timedelta, timezone

    future = datetime.now(timezone.utc) + timedelta(hours=1)
    manager.enqueue(1, "informe nocturno", scheduled_at=future)
    assert captured["status"] == "scheduled"

    manager.enqueue(1, "tarea inmediata")
    assert captured["status"] == "pending"


def test_parsed_scheduled_at_uses_local_timezone_for_naive_datetimes():
    """Regression: datetime-local inputs (no offset) were interpreted as UTC,
    shifting every scheduled task by the server timezone offset."""
    from datetime import datetime, timezone

    payload = TaskCreatePayload(goal="x", scheduled_at="2030-06-01T18:30")
    parsed = payload.parsed_scheduled_at()
    local_offset = datetime.now().astimezone().utcoffset()
    assert parsed.tzinfo is not None
    assert parsed.utcoffset() == local_offset
