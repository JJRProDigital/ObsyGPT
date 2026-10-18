import pytest

from app.memory import learning, routes as memory_routes, store
from app.workflows.runtime import AgentSpec


class FakeRequest:
    session = {"user_id": 2, "role": "user"}


def agent_spec() -> AgentSpec:
    return AgentSpec(
        id=1,
        name="Default",
        system_prompt="You are ObsyGPT.",
        provider_type="openrouter",
        provider_base_url=None,
        provider_api_key_env="OPENROUTER_API_KEY",
        model="test-model",
        temperature=0.7,
    )


def test_parse_model_reply_accepts_json():
    assert learning.parse_model_reply('{"habit": "Prefiere respuestas breves"}') == "Prefiere respuestas breves"
    assert learning.parse_model_reply('blah {"habit": "Usa tablas para comparativas"} blah') == "Usa tablas para comparativas"


def test_parse_model_reply_rejects_empty_or_invalid():
    assert learning.parse_model_reply('{"habit": null}') is None
    assert learning.parse_model_reply("NONE") is None
    assert learning.parse_model_reply("") is None
    assert learning.parse_model_reply("no json here") is None
    assert learning.parse_model_reply('{"habit": "   "}') is None


def test_heuristic_skill_habits_requires_three_uses(monkeypatch):
    monkeypatch.setattr(learning, "_recent_user_message_samples", lambda conversation_id: [
        "/web_search compara precios",
        "otra cosa",
        "/web_search busca esto",
        "/web_search busca aquello",
    ])
    monkeypatch.setattr(learning, "list_memories", lambda user_id, kind, limit=100: [])

    proposals = learning._heuristic_skill_habits(2, 7)

    assert proposals == [("Invoca con frecuencia la skill /web_search", "Usada 3 veces en esta conversacion")]


def test_heuristic_skill_habits_skips_known_skill(monkeypatch):
    monkeypatch.setattr(learning, "_recent_user_message_samples", lambda conversation_id: ["/web_search a", "/web_search b", "/web_search c"])
    monkeypatch.setattr(learning, "list_memories", lambda user_id, kind, limit=100: [{"content": "Invoca con frecuencia la skill /web_search"}])

    assert learning._heuristic_skill_habits(2, 7) == []


def test_learn_habits_stores_model_suggestion(monkeypatch):
    created = []
    monkeypatch.setattr(learning, "_count_user_messages", lambda conversation_id: learning.EXTRACT_EVERY_N_MESSAGES)
    monkeypatch.setattr(learning, "list_habit_suggestions", lambda user_id, status="pending": [])
    monkeypatch.setattr(learning, "_heuristic_skill_habits", lambda user_id, conversation_id: [])
    monkeypatch.setattr(learning, "_extract_with_model", lambda agent, user_id, exchange: "Prefiere respuestas en espanol")
    monkeypatch.setattr(learning, "create_habit_suggestion", lambda user_id, content, evidence="", source="model", conversation_id=None: created.append((user_id, content, source)))

    learning.learn_habits(2, 7, agent_spec(), "hola", "Hola, en que te ayudo?")

    assert created == [(2, "Prefiere respuestas en espanol", "model")]


def test_learn_habits_skips_when_not_nth_message(monkeypatch):
    called = []
    monkeypatch.setattr(learning, "_count_user_messages", lambda conversation_id: 2)
    monkeypatch.setattr(learning, "create_habit_suggestion", lambda *args, **kwargs: called.append(args))

    learning.learn_habits(2, 7, agent_spec(), "hola", "respuesta")

    assert called == []


def test_learn_habits_survives_model_failure(monkeypatch):
    monkeypatch.setattr(learning, "_count_user_messages", lambda conversation_id: 3)
    monkeypatch.setattr(learning, "list_habit_suggestions", lambda user_id, status="pending": [])
    monkeypatch.setattr(learning, "_heuristic_skill_habits", lambda user_id, conversation_id: [])

    def boom(agent, user_id, exchange):
        raise RuntimeError("provider down")

    monkeypatch.setattr(learning, "_extract_with_model", boom)

    learning.learn_habits(2, 7, agent_spec(), "hola", "respuesta")


def test_suggestion_endpoints(monkeypatch):
    monkeypatch.setattr(memory_routes.store, "list_habit_suggestions", lambda user_id: [{"id": 4, "content": "Prefiere tablas", "status": "pending"}])
    listed = memory_routes.list_suggestions(FakeRequest())
    assert listed["suggestions"][0]["id"] == 4

    monkeypatch.setattr(memory_routes.store, "decide_habit_suggestion", lambda user_id, suggestion_id, decision: {"id": suggestion_id, "status": "accepted", "content": "Prefiere tablas"})
    accepted = memory_routes.accept_suggestion(4, FakeRequest())
    assert accepted["status"] == "accepted"

    monkeypatch.setattr(memory_routes.store, "decide_habit_suggestion", lambda user_id, suggestion_id, decision: {"id": suggestion_id, "status": "dismissed", "content": "x"})
    dismissed = memory_routes.dismiss_suggestion(4, FakeRequest())
    assert dismissed["status"] == "dismissed"

    monkeypatch.setattr(memory_routes.store, "decide_habit_suggestion", lambda user_id, suggestion_id, decision: None)
    with pytest.raises(Exception):
        memory_routes.accept_suggestion(99, FakeRequest())


def test_build_exchange_truncates():
    exchange = learning._build_exchange("a" * 5000, "b" * 5000)
    assert len(exchange) <= learning.MAX_EXCHANGE_CHARS + 10
    assert exchange.endswith("[...]")
