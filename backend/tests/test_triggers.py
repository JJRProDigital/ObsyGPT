import asyncio
from datetime import datetime, timedelta, timezone

import pytest

from app.triggers import engine as triggers_engine
from app.triggers import store as trigger_store
from app.triggers.engine import FireOutcome, TriggerEngine, is_due, render_goal, rss_titles, source_snapshot
from app.triggers.store import TRIGGER_TYPES


class FakeTriggerStore:
    def __init__(self, triggers=None):
        self.triggers = {t["id"]: dict(t) for t in (triggers or [])}
        self.fired: list[tuple[int, str | None]] = []
        self.deliveries: list[tuple[int, int, int]] = []

    def list_enabled_triggers(self):
        return [dict(t) for t in self.triggers.values() if t.get("enabled")]

    def mark_fired(self, trigger_id, snapshot):
        self.fired.append((trigger_id, snapshot))

    def record_proactive_delivery(self, agent_id, chat_id, content, task_id):
        self.deliveries.append((agent_id, chat_id, task_id))


class FakeManager:
    def __init__(self):
        self.enqueued: list[tuple] = []

    def enqueue(self, user_id, goal, mode="act", scheduled_at=None, agent_id=None, readonly=False):
        self.enqueued.append((user_id, goal, agent_id, readonly))
        return {"id": 100 + len(self.enqueued)}


@pytest.fixture
def engine(monkeypatch):
    fake_store = FakeTriggerStore()
    fake_manager = FakeManager()
    monkeypatch.setattr(trigger_store, "list_enabled_triggers", fake_store.list_enabled_triggers)
    monkeypatch.setattr(trigger_store, "mark_fired", fake_store.mark_fired)
    monkeypatch.setattr(trigger_store, "record_proactive_delivery", fake_store.record_proactive_delivery)
    monkeypatch.setattr(triggers_engine, "trigger_store", fake_store)
    monkeypatch.setattr("app.tasks.routes.require_manager", lambda: fake_manager)
    return fake_store, fake_manager, TriggerEngine()


def _trigger(**overrides):
    base = {
        "id": 1,
        "user_id": 7,
        "agent_id": 2,
        "name": "noticias-ia",
        "trigger_type": "interval",
        "config": {"interval_minutes": 60},
        "goal_template": "Resume las novedades de IA",
        "notify_channel": "",
        "notify_chat_id": None,
        "cooldown_seconds": 0,
        "readonly": True,
        "enabled": True,
        "webhook_secret": None,
        "last_fired_at": None,
        "last_snapshot": None,
    }
    base.update(overrides)
    return base


def test_is_due_interval_and_cooldown():
    now = datetime.now(timezone.utc)
    assert is_due(_trigger(), now)
    fired = _trigger(last_fired_at=now - timedelta(minutes=30))
    assert not is_due(fired, now), "interval config must be respected even with cooldown 0"
    webhook = _trigger(trigger_type="webhook")
    assert not is_due(webhook, now), "webhook triggers never fire from the tick loop"


def test_validate_config_rejects_bad_sources():
    with pytest.raises(ValueError):
        triggers_engine.validate_config("change_detection", {"interval_minutes": 5, "source_type": "ftp", "url": "http://x.com"})
    with pytest.raises(ValueError):
        triggers_engine.validate_config("interval", {"interval_minutes": 0})
    triggers_engine.validate_config("interval", {"interval_minutes": 30})


def test_rss_titles_extracts_and_cleans():
    xml = "<rss><item><title><![CDATA[Noticia 1]]></title></item><item><title>Noticia <b>2</b></title></item></rss>"
    assert rss_titles(xml) == ["Noticia 1", "Noticia 2"]


def test_source_snapshot_stable_and_distinct():
    first, _ = source_snapshot("change_detection", "url", "contenido estable")
    second, _ = source_snapshot("change_detection", "url", "contenido estable  ")
    assert first == second, "whitespace must normalize away"
    changed, _ = source_snapshot("change_detection", "url", "contenido nuevo")
    assert first != changed


def test_render_goal_appends_trigger_context():
    goal = render_goal("Resume novedades", "noticias-ia", "Nueva noticia X")
    assert goal.startswith("Resume novedades")
    assert "noticias-ia" in goal
    assert "Nueva noticia X" in goal


def test_evaluate_fires_interval_trigger(engine):
    store, manager, tg = engine
    outcome = asyncio.run(tg.evaluate_trigger(_trigger()))
    assert outcome.fired and outcome.task_id == 101
    assert manager.enqueued[0][0] == 7 and manager.enqueued[0][2] == 2
    assert manager.enqueued[0][3] is True  # readonly default
    assert "Resume las novedades" in manager.enqueued[0][1]
    assert "noticias-ia" in manager.enqueued[0][1]
    assert (1, None) in [(tid, snap) for tid, snap in store.fired]


def test_evaluate_change_detection_fires_only_on_change(monkeypatch, engine):
    store, manager, tg = engine
    monkeypatch.setattr(triggers_engine, "fetch_source", lambda url: "<rss><item><title>Nueva IA</title></item></rss>")
    trigger = _trigger(trigger_type="change_detection", config={"interval_minutes": 5, "source_type": "rss", "url": "https://example.com/rss"})

    outcome = asyncio.run(tg.evaluate_trigger(dict(trigger)))
    assert outcome.fired
    assert "Nueva IA" in manager.enqueued[0][1]

    # Same snapshot -> no fire
    trigger["last_snapshot"] = store.fired[-1][1]
    outcome = asyncio.run(tg.evaluate_trigger(dict(trigger)))
    assert not outcome.fired and outcome.reason == "snapshot unchanged"
    assert len(manager.enqueued) == 1


def test_readonly_trigger_notifies_telegram_and_never_has_sensitive_tools(engine):
    store, manager, tg = engine
    trigger = _trigger(notify_channel="telegram", notify_chat_id=555)
    outcome = asyncio.run(tg.evaluate_trigger(trigger))
    assert outcome.fired
    assert store.deliveries == [(2, 555, 101)]
    assert manager.enqueued[0][3] is True

    from app.agent.tools.base import ToolRegistry
    from app.agent.tools.base import ToolSpec

    registry = ToolRegistry()

    class FakeTool:
        def __init__(self, spec):
            self.spec = spec

        def run(self, args):
            raise NotImplementedError

    registry.register(FakeTool(ToolSpec(name="write_file", description="", parameters="{}", permission="sensitive")))
    registry.register(FakeTool(ToolSpec(name="read_file", description="", parameters="{}", permission="safe")))
    registry.filter_to({"read_file"})
    with pytest.raises(KeyError):
        registry.get("write_file")


def test_trigger_types_constant_stable():
    assert TRIGGER_TYPES == {"interval", "change_detection", "webhook"}
