import asyncio

import pytest

from app.agent.tools.triggers import CancelTriggerTool, MyTriggersTool, ScheduleTriggerTool, MAX_ACTIVE_TRIGGERS
from app.triggers import store as trigger_store
from app.triggers.engine import TriggerEngine


class FakeTriggerStore:
    def __init__(self, active=0):
        self.created: list[dict] = []
        self.active = active
        self.disabled: list[int] = []
        self.triggers: dict[int, dict] = {}

    def count_active_triggers(self, user_id):
        return self.active

    def create_trigger(self, user_id, agent_id, name, trigger_type, config, goal_template, notify_channel="", notify_chat_id=None, cooldown_seconds=0, readonly=True):
        self.created.append({"user_id": user_id, "agent_id": agent_id, "name": name, "trigger_type": trigger_type, "config": config, "goal_template": goal_template, "readonly": readonly})
        trigger = {"id": 100 + len(self.created), "name": name, "goal_template": goal_template, "user_id": user_id, "enabled": True}
        self.triggers[trigger["id"]] = trigger
        return trigger

    def list_triggers(self, user_id):
        return [t for t in self.triggers.values() if t["user_id"] == user_id]

    def get_trigger(self, trigger_id, user_id=None):
        trigger = self.triggers.get(trigger_id)
        if trigger and user_id is not None and trigger["user_id"] != user_id:
            return None
        return trigger

    def set_trigger_enabled(self, trigger_id, user_id, enabled):
        self.disabled.append(trigger_id)
        self.triggers[trigger_id]["enabled"] = enabled
        return self.triggers[trigger_id]

    # engine support
    def mark_fired(self, trigger_id, snapshot):
        pass

    def record_proactive_delivery(self, *a, **k):
        pass


def test_schedule_trigger_creates_interval_trigger():
    store = FakeTriggerStore()
    tool = ScheduleTriggerTool(user_id=7, agent_id=2, store=store)
    result = tool.run({"goal": "Revisa si llegó respuesta", "interval_minutes": 60, "fire_once": True, "name": "seguimiento"})
    assert result.ok
    created = store.created[0]
    assert created["user_id"] == 7 and created["agent_id"] == 2
    assert created["config"] == {"interval_minutes": 60, "fire_once": True}
    assert created["readonly"] is True
    assert "#101" in result.output and "una vez" in result.output


def test_schedule_trigger_requires_goal():
    tool = ScheduleTriggerTool(user_id=7, agent_id=2, store=FakeTriggerStore())
    result = tool.run({"interval_minutes": 30})
    assert not result.ok and "goal" in result.output


def test_schedule_trigger_rejects_bad_interval():
    tool = ScheduleTriggerTool(user_id=7, agent_id=2, store=FakeTriggerStore())
    result = tool.run({"goal": "x", "interval_minutes": 0})
    assert not result.ok and "interval_minutes" in result.output


def test_schedule_trigger_enforces_limit():
    store = FakeTriggerStore(active=MAX_ACTIVE_TRIGGERS)
    tool = ScheduleTriggerTool(user_id=7, agent_id=2, store=store)
    result = tool.run({"goal": "x", "interval_minutes": 10})
    assert not result.ok
    assert not store.created


def test_my_triggers_lists_only_enabled():
    store = FakeTriggerStore()
    store.triggers = {
        1: {"id": 1, "name": "alpha", "user_id": 7, "enabled": True, "config": {"interval_minutes": 5}, "goal_template": "objetivo-alpha"},
        2: {"id": 2, "name": "beta", "user_id": 7, "enabled": False, "config": {"interval_minutes": 5}, "goal_template": "objetivo-beta"},
        3: {"id": 3, "name": "gamma", "user_id": 9, "enabled": True, "config": {"interval_minutes": 5}, "goal_template": "objetivo-gamma"},
    }
    result = MyTriggersTool(user_id=7, store=store).run({})
    output = result.output
    assert result.ok, output
    assert "alpha" in output, output
    assert "beta" not in output, output
    assert "gamma" not in output, output


def test_cancel_trigger_checks_ownership():
    store = FakeTriggerStore()
    store.triggers = {5: {"id": 5, "name": "ajeno", "user_id": 9, "enabled": True}}
    result = CancelTriggerTool(user_id=7, store=store).run({"trigger_id": 5})
    assert not result.ok and store.disabled == []

    store.triggers[6] = {"id": 6, "name": "mio", "user_id": 7, "enabled": True}
    result = CancelTriggerTool(user_id=7, store=store).run({"trigger_id": 6})
    assert result.ok and store.disabled == [6]


def test_fire_once_disables_after_firing(monkeypatch):
    fake_store = FakeTriggerStore()
    fake_manager_enqueued: list[tuple] = []

    class FakeManager:
        def enqueue(self, user_id, goal, mode="act", agent_id=None, readonly=False):
            fake_manager_enqueued.append((user_id, goal, agent_id, readonly))
            return {"id": 50}

    monkeypatch.setattr(trigger_store, "set_trigger_enabled", lambda tid, uid, enabled: fake_store.disabled.append(tid))
    monkeypatch.setattr(trigger_store, "mark_fired", lambda *a, **k: None)
    monkeypatch.setattr(trigger_store, "record_proactive_delivery", lambda *a, **k: None)
    monkeypatch.setattr("app.triggers.engine.trigger_store", trigger_store)
    monkeypatch.setattr("app.tasks.routes.require_manager", lambda: FakeManager())

    engine = TriggerEngine()
    trigger = {"id": 1, "user_id": 7, "agent_id": 2, "name": "recordatorio", "trigger_type": "interval",
               "config": {"interval_minutes": 30, "fire_once": True}, "goal_template": "Revisá X",
               "notify_channel": "", "notify_chat_id": None, "cooldown_seconds": 0, "readonly": True,
               "enabled": True, "webhook_secret": None, "last_fired_at": None, "last_snapshot": None}

    outcome = asyncio.run(engine.evaluate_trigger(trigger))
    assert outcome.fired
    assert 1 in fake_store.disabled, "fire_once trigger must be disabled after firing"
    assert fake_manager_enqueued[0][3] is True
