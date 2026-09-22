import pytest
from datetime import datetime, timezone
from fastapi import HTTPException

from app.chat.specs import build_project_context
from app.projects import routes as projects_routes
from app.projects.routes import ProjectPayload, ProjectUpdatePayload


class FakeRequest:
    session = {"user_id": 2, "role": "user"}


def test_project_payload_strips_and_validates():
    payload = ProjectPayload(name="  Web Redesign  ", description="desc", instructions="sé conciso")

    assert payload.name == "Web Redesign"

    with pytest.raises(Exception):
        ProjectPayload(name="   ")


def test_project_update_payload_allows_partial():
    payload = ProjectUpdatePayload(instructions="nuevas instrucciones")

    assert payload.name is None
    assert payload.instructions == "nuevas instrucciones"


def test_create_project_returns_stored_project(monkeypatch):
    captured = {}

    def fake_create(user_id, name, description="", instructions="", folder_path=None):
        captured.update({"user_id": user_id, "name": name})
        return {"id": 1, "name": name, "description": description, "instructions": instructions, "created_at": "t", "updated_at": "t"}

    monkeypatch.setattr(projects_routes.store, "create_project", fake_create)

    result = projects_routes.create_project(ProjectPayload(name="Proyecto Alfa"), FakeRequest())

    assert result["project"]["id"] == 1
    assert captured == {"user_id": 2, "name": "Proyecto Alfa"}


def test_get_project_404_when_not_owned(monkeypatch):
    monkeypatch.setattr(projects_routes.store, "get_project_detail", lambda project_id, user_id: None)

    with pytest.raises(HTTPException) as error:
        projects_routes.get_project(9, FakeRequest())

    assert error.value.status_code == 404


def test_link_conversation_404_when_missing(monkeypatch):
    monkeypatch.setattr(projects_routes.store, "link_conversation", lambda project_id, user_id, conversation_id: False)

    with pytest.raises(HTTPException) as error:
        projects_routes.add_conversation(9, 5, FakeRequest())

    assert error.value.status_code == 404


def test_build_project_context_includes_instructions_and_files(monkeypatch):
    monkeypatch.setattr(
        "app.chat.attachments.get_attachment_records",
        lambda user_id, attachment_ids: [type("Record", (), {"file_name": "brief.md", "content": "requisitos del proyecto"})()],
    )
    monkeypatch.setattr(
        "app.chat.attachments.build_attachment_context",
        lambda records: "brief.md\nrequisitos del proyecto",
    )

    context = build_project_context(
        {"name": "Alfa", "instructions": "Responde en espanol.", "attachment_ids": [3]},
        user_id=2,
    )

    assert "Instrucciones del proyecto 'Alfa'" in context
    assert "Responde en espanol." in context
    assert "Conocimiento del proyecto" in context
    assert "requisitos del proyecto" in context


def test_build_project_context_empty_when_nothing_configured():
    assert build_project_context({"name": "Alfa", "instructions": "", "attachment_ids": []}, user_id=2) == ""


def test_validate_folder_path_accepts_real_dir(tmp_path):
    from app.projects.routes import _validate_folder_path

    assert _validate_folder_path(str(tmp_path)) == str(tmp_path.resolve())


def test_validate_folder_path_rejects_relative_and_missing():
    from fastapi import HTTPException as HTTPExceptionAlias
    from app.projects.routes import _validate_folder_path

    with pytest.raises(HTTPExceptionAlias):
        _validate_folder_path("carpeta/relativa")
    with pytest.raises(HTTPExceptionAlias):
        _validate_folder_path(r"C:\no\existe\seguro")


def test_update_project_archives_and_unarchives(monkeypatch):
    captured = {}

    def fake_update(project_id, user_id, name=None, description=None, instructions=None, folder_path=None, archived=None):
        captured["archived"] = archived
        return {"id": project_id, "archived": archived}

    monkeypatch.setattr(projects_routes.store, "update_project", fake_update)

    result = projects_routes.update_project(5, ProjectUpdatePayload(archived=True), FakeRequest())

    assert result["project"]["archived"] is True
    assert captured["archived"] is True


def test_task_payload_accepts_project_and_recurrence():
    from app.tasks.routes import TaskCreatePayload

    payload = TaskCreatePayload(goal="informe", project_id=3, recurrence="daily")

    assert payload.project_id == 3
    assert payload.recurrence == "daily"

    with pytest.raises(Exception):
        TaskCreatePayload(goal="x", recurrence="mensual")


def test_recurrence_clones_next_occurrence(monkeypatch):
    from app.tasks import manager as tasks_manager_module
    from app.tasks.manager import TaskManager

    fake = FakeTaskStore()
    monkeypatch.setattr(tasks_manager_module, "task_store", fake)
    manager = TaskManager()

    completed = fake.create_task(2, "informe diario", recurrence="daily", project_id=7)
    fake.set_task_status(completed["id"], "completed")

    manager._maybe_schedule_recurrence(completed["id"])

    clones = [task for task in fake.tasks.values() if task["id"] != completed["id"]]
    assert len(clones) == 1
    clone = clones[0]
    assert clone["status"] == "scheduled"
    assert clone["recurrence"] == "daily"
    assert clone["project_id"] == 7
    assert clone["scheduled_at"] is not None
    assert fake.tasks[completed["id"]]["last_occurrence_at"] is not None


class FakeTaskStore:
    def __init__(self):
        self.tasks: dict[int, dict] = {}
        self.next_id = 1

    def create_task(self, user_id, goal, mode="act", scheduled_at=None, agent_id=None, project_id=None, recurrence=None):
        task_id = self.next_id
        self.next_id += 1
        task = {
            "id": task_id,
            "user_id": user_id,
            "goal": goal,
            "mode": mode,
            "status": "scheduled" if scheduled_at else "pending",
            "scheduled_at": scheduled_at or datetime.now(timezone.utc),
            "attempts": 0,
            "agent_id": agent_id,
            "project_id": project_id,
            "recurrence": recurrence,
            "last_occurrence_at": None,
        }
        self.tasks[task_id] = task
        return dict(task)

    def get_task(self, task_id, user_id=None):
        return dict(self.tasks[task_id]) if task_id in self.tasks else None

    def set_task_status(self, task_id, status, result=None, error=None):
        self.tasks[task_id]["status"] = status

    def mark_last_occurrence(self, task_id):
        self.tasks[task_id]["last_occurrence_at"] = datetime.now(timezone.utc)

    def record_event(self, task_id, event_type, title, content=""):
        pass


def test_memory_context_includes_project_memories(monkeypatch):
    from app.memory.context import build_memory_context

    def fake_list(user_id, kind=None, limit=30, project_id=None):
        if project_id == 7:
            return [{"content": "regla del proyecto"}]
        if kind == "memory":
            return [{"content": "memoria global"}]
        return []

    monkeypatch.setattr("app.memory.context.list_memories", fake_list)

    context = build_memory_context(2, project_id=7)

    assert "Memorias del proyecto" in context
    assert "regla del proyecto" in context
    assert "memoria global" in context
