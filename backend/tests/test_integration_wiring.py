"""Integration tests with a real TestClient: app wiring, lifespan, HTTP endpoints.

These exist because unit tests with fakes missed real bugs (the TaskManager
scheduler never being started, sync endpoints crashing on the event loop).
"""

import threading

import pytest
from fastapi.testclient import TestClient

from app import main as app_main
from app.tasks import routes as tasks_routes


class FakeTaskStore:
    """In-memory task store so the manager never touches the database."""

    def __init__(self):
        self.tasks: dict[int, dict] = {}
        self.next_id = 1

    def create_task(self, user_id, goal, mode="act", scheduled_at=None, agent_id=None, project_id=None, recurrence=None, status=None):
        task_id = self.next_id
        self.next_id += 1
        if status is None:
            status = "scheduled" if scheduled_at is not None else "pending"
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
        return [dict(t) for t in self.tasks.values() if t["status"] in statuses]

    def get_task(self, task_id, user_id=None):
        task = self.tasks.get(task_id)
        if not task or (user_id is not None and task["user_id"] != user_id):
            return None
        return dict(task)

    def set_task_status(self, task_id, status, result=None, error=None):
        task = self.tasks[task_id]
        task["status"] = status

    def update_task_fields(self, task_id, attempts=None, next_attempt_at=None):
        pass

    def record_event(self, task_id, event_type, title, content=""):
        pass

    def delete_task(self, task_id):
        self.tasks.pop(task_id, None)

    def get_tasks_settings(self):
        return {"max_concurrent_tasks": 1, "auto_resume_tasks": True}

    def now_utc(self):
        from datetime import datetime, timezone

        return datetime.now(timezone.utc)


@pytest.fixture
def client(monkeypatch):
    fake_store = FakeTaskStore()
    monkeypatch.setattr("app.tasks.manager.task_store", fake_store)
    # The background runner would try to load agents from the DB; that path is
    # irrelevant here (failures are absorbed by the manager).
    with TestClient(app_main.app) as test_client:
        yield test_client
    manager = tasks_routes._manager
    if manager is not None:
        manager.runners.clear()


def test_lifespan_starts_task_scheduler(client):
    """Regression: lifespan used to never call TaskManager.start(), so the
    scheduler tick loop was dead and scheduled tasks never became pending."""
    manager = tasks_routes._manager
    assert manager is not None
    assert manager._loop is not None, "manager must capture the running loop"
    assert manager._tick_task is not None, "lifespan must start the tick loop"
    assert not manager._tick_task.done()


def test_create_task_endpoint_does_not_crash(client, monkeypatch):
    """Regression: POST /api/tasks used asyncio.get_event_loop() from a sync
    endpoint worker thread -> RuntimeError -> 500 and a task stuck in running."""
    monkeypatch.setattr("app.tasks.routes.require_user", lambda request: 7)
    manager = tasks_routes._manager
    started = []
    monkeypatch.setattr(manager, "_start", lambda task: started.append(task["id"]))

    response = client.post("/api/tasks", json={"goal": "revisar informe", "mode": "act"})

    assert response.status_code == 200, response.text
    assert response.json()["task"]["goal"] == "revisar informe"
    assert started, "enqueue must pump the task into the manager"


def test_create_task_endpoint_schedules_without_start(client, monkeypatch):
    monkeypatch.setattr("app.tasks.routes.require_user", lambda request: 7)

    response = client.post("/api/tasks", json={"goal": "informe nocturno", "scheduled_at": "2030-01-01T03:00:00+00:00"})

    assert response.status_code == 200, response.text
    assert response.json()["task"]["status"] == "scheduled"


def test_health_endpoint_responds(client):
    response = client.get("/api/health")
    assert response.status_code == 200
    assert response.json()["status"] in {"healthy", "degraded"}


def test_memory_requires_session(client):
    response = client.get("/api/memory")
    assert response.status_code == 401


def test_admin_delete_unknown_model_returns_404(client, monkeypatch):
    """Regression: DELETEs with unknown ids raised TypeError (dict(zip(columns, None))) -> 500."""
    monkeypatch.setattr("app.auth.routes.require_admin", lambda request: 1)
    monkeypatch.setattr("app.admin.queries.execute_returning", lambda query, params: None)

    response = client.delete("/api/admin/models/99999")

    assert response.status_code == 404
    assert response.json()["detail"] == "Model not found."


def test_admin_delete_unknown_skill_and_mcp_return_404(client, monkeypatch):
    monkeypatch.setattr("app.auth.routes.require_admin", lambda request: 1)
    monkeypatch.setattr("app.admin.queries.execute_returning", lambda query, params: None)

    assert client.delete("/api/admin/skills/99999").status_code == 404
    assert client.delete("/api/admin/mcp-servers/99999").status_code == 404


def test_spawn_from_thread_schedules_on_manager_loop(client):
    """The manager must accept work submitted from non-async threads (sync routes)."""
    manager = tasks_routes._manager
    executed = threading.Event()

    async def marker():
        executed.set()

    future = manager._spawn(marker())
    future.result(timeout=5)
    assert executed.is_set(), "coroutine must run on the manager loop"


def test_db_connect_is_a_context_manager():
    """Regression: db.connect() was once a bare generator — `with connect() as ...`
    crashed at runtime ('generator object does not support the context manager
    protocol') and no unit test executed a real store call, so the app failed to boot."""
    from contextlib import contextmanager as _cm  # noqa: F401 - sanity for the reader

    from app import db

    connection_cm = db.connect()
    assert hasattr(connection_cm, "__enter__"), "db.connect() must be usable as `with connect() as conn:`"
    assert hasattr(connection_cm, "__exit__"), "db.connect() must be usable as `with connect() as conn:`"


def test_lifespan_boots_with_real_task_store(monkeypatch):
    """The real task store path (not a fake) must survive startup: auto_resume
    reads app_settings through the pooled connection during lifespan."""
    from app import main as app_main_real

    with TestClient(app_main_real.app) as test_client:
        response = test_client.get("/api/health")
        assert response.status_code == 200
    manager = tasks_routes._manager
    if manager is not None:
        manager.runners.clear()

def test_sanitized_str_dumper_strips_nul_without_db():
    """Regression: web-scraped content (HTML/RSS) can carry NUL bytes, which
    PostgreSQL rejects in text fields - a scheduled news-search task failed
    with 'PostgreSQL text fields cannot contain NUL (0x00) bytes'."""
    from app.db import _SanitizedStrDumper

    dumper = _SanitizedStrDumper(str, None)
    assert dumper.dump("noticia\x00con byte nulo") == "noticiacon byte nulo".encode("utf-8")
    assert dumper.dump("texto limpio") == "texto limpio".encode("utf-8")


def _postgres_available() -> bool:
    try:
        from app.db import connect

        with connect() as connection:
            with connection.cursor() as cursor:
                cursor.execute("SELECT 1;")
        return True
    except Exception:  # noqa: BLE001
        return False


def test_task_events_survive_nul_bytes_end_to_end():
    """End-to-end with a real PostgreSQL: a task event whose content carries a
    NUL byte must be stored (sanitized) instead of failing the whole task."""
    import pytest

    from app.db import close_pool, connect
    from app.tasks import store as task_store

    if not _postgres_available():
        pytest.skip("requires a reachable PostgreSQL")

    try:
        with connect() as connection:
            with connection.cursor() as cursor:
                cursor.execute("SELECT id FROM users ORDER BY id LIMIT 1;")
                row = cursor.fetchone()
        if not row:
            pytest.skip("requires at least one existing user")
        existing_user_id = row[0]
        task = task_store.create_task(existing_user_id, "tarea de prueba NUL")
        task_store.record_event(
            task["id"],
            "task_update",
            "evento con NUL",
            "contenido\x00con byte nulo",
        )
        events = task_store.list_events(task["id"])
        assert any("contenidocon byte nulo" == event["content"] for event in events)
        task_store.delete_task(task["id"])
    finally:
        close_pool()

def test_json_columns_accept_text_params_end_to_end():
    """Regression: psycopg3 sends str params as text; JSON columns need explicit
    casts. save_run_state crashed agentic/scheduled runs with 'column "messages"
    is of type json but expression is of type text' (psycopg2 tolerated the
    implicit cast, psycopg3 does not)."""
    import json as _json

    import pytest

    from app.audit.store import AuditStore
    from app.db import close_pool, connect

    if not _postgres_available():
        pytest.skip("requires a reachable PostgreSQL")

    try:
        with connect() as connection:
            with connection.cursor() as cursor:
                cursor.execute("SELECT id FROM users ORDER BY id LIMIT 1;")
                row = cursor.fetchone()
                if not row:
                    pytest.skip("requires at least one existing user")
                existing_user_id = row[0]
                # The exact SQL shape save_run_state uses: str param + ::json cast.
                cursor.execute("SELECT %s::json;", (_json.dumps([{"role": "user", "content": "hola \u00e9"}]),))
                roundtrip = cursor.fetchone()[0]
        assert roundtrip == [{"role": "user", "content": "hola \u00e9"}]

        AuditStore().add_log(
            actor_user_id=existing_user_id,
            action="test.json_cast",
            target_type="test",
            target_id=None,
            metadata={"probe": True, "note": "con acentos \u00e1\u00e9"},
        )
        with connect() as connection:
            with connection.cursor() as cursor:
                cursor.execute("SELECT metadata FROM audit_logs WHERE action = 'test.json_cast' ORDER BY id DESC LIMIT 1;")
                metadata = cursor.fetchone()[0]
                cursor.execute("DELETE FROM audit_logs WHERE action = 'test.json_cast';")
        assert metadata.get("probe") is True
    finally:
        close_pool()
