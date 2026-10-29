import asyncio

import pytest

from app.telegram import gateway as tg_gateway
from app.telegram import store as tg_store
from app.telegram.gateway import (
    TelegramGateway,
    approval_keyboard,
    build_context_note,
    chunk_message,
    format_tool_args,
    parse_allowlist,
    parse_callback_data,
)


class FakeTelegramClient:
    def __init__(self):
        self.sent: list[dict] = []
        self.answered: list[str] = []
        self.cleared: list[tuple[int, int]] = []

    async def send_message(self, chat_id, text, reply_markup=None, parse_mode=None):
        self.sent.append({"chat_id": chat_id, "text": text, "reply_markup": reply_markup, "parse_mode": parse_mode})
        return len(self.sent)

    async def send_chat_action(self, chat_id, action="typing"):
        self.sent.append({"chat_id": chat_id, "action": action})

    async def answer_callback_query(self, callback_query_id, text):
        self.answered.append(text)

    async def clear_reply_markup(self, chat_id, message_id):
        self.cleared.append((chat_id, message_id))


@pytest.fixture
def gateway(monkeypatch):
    return TelegramGateway()


# ---------- pure helpers ----------


def test_parse_allowlist_valid_and_normalization():
    parsed = parse_allowlist("12345:juan, 67890:ana;  42:bot.user-1")
    assert parsed == {12345: "juan", 67890: "ana", 42: "bot.user-1"}


@pytest.mark.parametrize("raw", ["no-colon", "abc:juan", "123:bad user!", "123:", ":juan"])
def test_parse_allowlist_rejects_invalid(raw):
    with pytest.raises(ValueError):
        parse_allowlist(raw)


def test_chunk_message_short_and_long():
    assert chunk_message("hola") == ["hola"]
    assert chunk_message("") == []
    text = "x" * 9500
    chunks = chunk_message(text, limit=4000)
    assert [len(chunk) for chunk in chunks] == [4000, 4000, 1500]
    assert "".join(chunks) == text


def test_build_context_note_includes_history():
    history = [
        {"direction": "inbound", "content": "primera pregunta"},
        {"direction": "outbound", "content": "primera respuesta"},
    ]
    note = build_context_note(history)
    assert "Contexto previo" in note
    assert "- Usuario: primera pregunta" in note
    assert "- Agente: primera respuesta" in note
    assert "seguí con esto" not in note


def test_build_context_note_empty_without_history():
    assert build_context_note([]) == ""


def test_parse_callback_data():
    assert parse_callback_data("appr:12:1") == (12, True)
    assert parse_callback_data("appr:12:0") == (12, False)
    assert parse_callback_data("appr:x:1") is None
    assert parse_callback_data("appr:12") is None
    assert parse_callback_data("other:12:1") is None
    assert parse_callback_data("") is None


def test_approval_keyboard_bounds_and_shape():
    approvals = [{"id": i} for i in range(5)]
    keyboard = approval_keyboard(approvals)
    assert len(keyboard) == 3
    assert keyboard[0] == [
        {"text": "✅ Aprobar", "callback_data": "appr:0:1"},
        {"text": "❌ Rechazar", "callback_data": "appr:0:0"},
    ]


def test_format_tool_args_never_raises():
    assert "a" in format_tool_args({"x": "a"})
    assert len(format_tool_args({"x": object()}, limit=20)) <= 20


def test_markdown_to_telegram_html_converts_and_escapes():
    from app.telegram.gateway import markdown_to_telegram_html

    text = "**negrita** y `codigo` y <script>alert(1)</script>\n# Titulo\n[link](https://x.com)"
    out = markdown_to_telegram_html(text)
    assert "<b>negrita</b>" in out
    assert "<code>codigo</code>" in out
    assert "&lt;script&gt;" in out and "<script>" not in out
    assert "<b>Titulo</b>" in out
    assert '<a href="https://x.com">link</a>' in out


def test_markdown_keeps_bold_out_of_code_blocks():
    from app.telegram.gateway import markdown_to_telegram_html

    out = markdown_to_telegram_html("```\n**no bold**\n```")
    assert "<pre>" in out
    assert "<b>" not in out.split("<pre>")[1].split("</pre>")[0]


# ---------- inbound flow ----------


def test_handle_message_enqueues_task_for_allowlisted_user(monkeypatch, gateway):
    client = FakeTelegramClient()
    enqueued: list[tuple] = []

    monkeypatch.setattr(tg_store, "get_agent_telegram_config", lambda agent_id: {"telegram_allowlist": "111:juan"})
    monkeypatch.setattr(tg_store, "resolve_allowlisted_user", lambda raw, sender: "juan")
    monkeypatch.setattr(tg_store, "resolve_user_id_by_username", lambda username: 7)
    monkeypatch.setattr(tg_store, "recent_history", lambda agent_id, chat_id: [{"direction": "inbound", "content": "previo"}])
    monkeypatch.setattr(tg_store, "record_inbound", lambda *args, **kwargs: 55)
    monkeypatch.setattr(tg_store, "attach_task", lambda row_id, task_id: enqueued.append(("attach", row_id, task_id)))
    monkeypatch.setattr(gateway, "_enqueue_task", lambda user_id, goal, agent_id, context_note=None: enqueued.append(("enqueue", user_id, goal, agent_id, context_note)) or {"id": 99})

    message = {"message_id": 10, "from": {"id": 111}, "chat": {"id": 222}, "text": "hacé el informe"}
    asyncio.run(gateway._handle_message(1, client, message))

    assert enqueued[0][0] == "enqueue"
    assert enqueued[0][1] == 7
    assert enqueued[0][3] == 1
    assert "hacé el informe" in enqueued[0][2]
    assert "previo" in enqueued[0][4]
    assert enqueued[1] == ("attach", 55, 99)
    texts = [item.get("text", "") for item in client.sent]
    assert any("Tarea #99" in text for text in texts)


def test_handle_message_ignores_non_allowlisted(monkeypatch, gateway):
    client = FakeTelegramClient()
    monkeypatch.setattr(tg_store, "get_agent_telegram_config", lambda agent_id: {"telegram_allowlist": ""})
    monkeypatch.setattr(tg_store, "resolve_allowlisted_user", lambda raw, sender: None)
    monkeypatch.setattr(tg_store, "record_inbound", lambda *args, **kwargs: 1)

    message = {"message_id": 10, "from": {"id": 999}, "chat": {"id": 222}, "text": "hola"}
    asyncio.run(gateway._handle_message(1, client, message))
    assert client.sent == []


def test_handle_message_skips_duplicates(monkeypatch, gateway):
    client = FakeTelegramClient()
    monkeypatch.setattr(tg_store, "get_agent_telegram_config", lambda agent_id: {"telegram_allowlist": "111:juan"})
    monkeypatch.setattr(tg_store, "resolve_allowlisted_user", lambda raw, sender: "juan")
    monkeypatch.setattr(tg_store, "resolve_user_id_by_username", lambda username: 7)
    monkeypatch.setattr(tg_store, "recent_history", lambda agent_id, chat_id: [])
    monkeypatch.setattr(tg_store, "record_inbound", lambda *args, **kwargs: None)

    message = {"message_id": 10, "from": {"id": 111}, "chat": {"id": 222}, "text": "hola"}
    asyncio.run(gateway._handle_message(1, client, message))
    assert client.sent == []


def test_handle_message_reports_unknown_obsygpt_user(monkeypatch, gateway):
    client = FakeTelegramClient()
    monkeypatch.setattr(tg_store, "get_agent_telegram_config", lambda agent_id: {"telegram_allowlist": "111:juan"})
    monkeypatch.setattr(tg_store, "resolve_allowlisted_user", lambda raw, sender: "juan")
    monkeypatch.setattr(tg_store, "resolve_user_id_by_username", lambda username: None)

    message = {"message_id": 10, "from": {"id": 111}, "chat": {"id": 222}, "text": "hola"}
    asyncio.run(gateway._handle_message(1, client, message))
    assert any("no existe" in item.get("text", "") for item in client.sent)


# ---------- approval callback flow ----------


def test_handle_callback_approves_and_resumes(monkeypatch, gateway):
    client = FakeTelegramClient()
    from app.agent import store as agent_store

    approval = {"id": 12, "tool_name": "run_command", "task_id": 33, "agent_run_id": 5, "user_id": 7, "args": {}}
    monkeypatch.setattr(tg_store, "get_agent_telegram_config", lambda agent_id: {"telegram_allowlist": "111:juan"})
    monkeypatch.setattr(tg_store, "resolve_allowlisted_user", lambda raw, sender: "juan")
    monkeypatch.setattr(tg_store, "resolve_user_id_by_username", lambda username: 7)
    monkeypatch.setattr(tg_store, "record_outbound", lambda *args, **kwargs: None)
    monkeypatch.setattr(agent_store, "decide_approval", lambda approval_id, user_id, status: approval if status == "approved" else None)

    resumed: list[tuple] = []

    class FakeManager:
        def resume_after_approval(self, user_id, task_id, approval_dict, approved):
            resumed.append((user_id, task_id, approved))

    from app.tasks import routes as tasks_routes

    monkeypatch.setattr(tasks_routes, "require_manager", lambda: FakeManager())

    callback = {
        "id": "cb1",
        "data": "appr:12:1",
        "from": {"id": 111},
        "message": {"message_id": 20, "chat": {"id": 222}},
    }
    asyncio.run(gateway._handle_callback(1, client, callback))

    assert client.answered == ["Aprobada"]
    assert resumed == [(7, 33, True)]
    assert (222, 20) in client.cleared


def test_handle_callback_ignores_unauthorized(monkeypatch, gateway):
    client = FakeTelegramClient()
    monkeypatch.setattr(tg_store, "get_agent_telegram_config", lambda agent_id: {"telegram_allowlist": "111:juan"})
    monkeypatch.setattr(tg_store, "resolve_allowlisted_user", lambda raw, sender: None)

    callback = {"id": "cb1", "data": "appr:12:1", "from": {"id": 999}, "message": {"message_id": 20, "chat": {"id": 222}}}
    asyncio.run(gateway._handle_callback(1, client, callback))
    assert client.answered == ["No autorizado"]


# ---------- outcome delivery ----------


def test_deliver_outcomes_sends_completed_results(monkeypatch, gateway):
    rows = [{"id": 1, "agent_id": 1, "chat_id": 222, "task_id": 33, "notified_status": None, "task_status": "completed", "result": "informe listo", "error": "", "user_id": 7}]
    monkeypatch.setattr(tg_store, "pending_deliveries", lambda: rows)
    monkeypatch.setattr(tg_store, "get_agent_bot_token", lambda agent_id: "token")
    monkeypatch.setattr(tg_store, "record_outbound", lambda *args, **kwargs: None)
    marked: list[tuple] = []
    monkeypatch.setattr(tg_store, "mark_notified", lambda row_id, status, delivered=False: marked.append((row_id, status, delivered)))

    async def fake_send_message(self, chat_id, text, reply_markup=None):
        assert text == "informe listo"

    monkeypatch.setattr(tg_gateway.TelegramClient, "send_message", fake_send_message)

    asyncio.run(gateway._deliver_outcomes())
    assert marked == [(1, "completed", True)]


def test_deliver_outcomes_sends_approval_keyboard(monkeypatch, gateway):
    rows = [{"id": 2, "agent_id": 1, "chat_id": 222, "task_id": 33, "notified_status": None, "task_status": "awaiting_approval", "result": "", "error": "", "user_id": 7}]
    monkeypatch.setattr(tg_store, "pending_deliveries", lambda: rows)
    monkeypatch.setattr(tg_store, "get_agent_bot_token", lambda agent_id: "token")
    from app.agent import store as agent_store

    monkeypatch.setattr(agent_store, "list_pending_task_approvals", lambda user_id, task_id: [{"id": 12, "tool_name": "write_file", "args": {"path": "x.txt"}}])

    sent: list[dict] = []

    async def fake_send_message(self, chat_id, text, reply_markup=None):
        sent.append({"text": text, "reply_markup": reply_markup})

    monkeypatch.setattr(tg_gateway.TelegramClient, "send_message", fake_send_message)
    marked: list[tuple] = []
    monkeypatch.setattr(tg_store, "mark_notified", lambda row_id, status, delivered=False: marked.append((row_id, status, delivered)))

    asyncio.run(gateway._deliver_outcomes())
    assert len(sent) == 1
    assert "write_file" in sent[0]["text"]
    keyboard = sent[0]["reply_markup"]["inline_keyboard"]
    assert {"text": "✅ Aprobar", "callback_data": "appr:12:1"} in keyboard[0]
    assert marked == [(2, "awaiting_approval", False)]
