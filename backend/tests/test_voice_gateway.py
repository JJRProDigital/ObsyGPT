import asyncio

import pytest

from app.telegram import store as tg_store
from app.telegram import gateway as tg_gateway
from app.telegram.gateway import TelegramGateway
from app.voice import tts as voice_tts


class FakeTelegramClient:
    def __init__(self, voice_bytes=b"oggdata"):
        self.sent: list[dict] = []
        self.voices: list[bytes] = []
        self.downloads: list[str] = []
        self.voice_bytes = voice_bytes

    async def send_message(self, chat_id, text, reply_markup=None, parse_mode=None):
        self.sent.append({"chat_id": chat_id, "text": text})
        return len(self.sent)

    async def send_chat_action(self, chat_id, action="typing"):
        pass

    async def get_file(self, file_id):
        self.downloads.append(file_id)
        return self.voice_bytes

    async def send_voice(self, chat_id, ogg):
        self.voices.append(ogg)
        return 99


# ---------- inbound voice flow ----------


def test_voice_message_transcribed_and_enqueued(monkeypatch):
    gateway = TelegramGateway()
    client = FakeTelegramClient()
    enqueued: list[tuple] = []
    monkeypatch.setattr(tg_store, "get_agent_telegram_config", lambda agent_id: {"telegram_allowlist": "111:juan"})
    monkeypatch.setattr(tg_store, "resolve_allowlisted_user", lambda raw, sender: "juan")
    monkeypatch.setattr(tg_store, "resolve_user_id_by_username", lambda username: 7)
    monkeypatch.setattr(tg_store, "recent_history", lambda agent_id, chat_id: [])
    recorded: dict = {}
    monkeypatch.setattr(tg_store, "record_inbound", lambda *a, **k: recorded.update(k, args=a) or 77)
    monkeypatch.setattr(tg_store, "attach_task", lambda row_id, task_id: None)
    monkeypatch.setattr(gateway, "_enqueue_task", lambda user_id, goal, agent_id, context_note=None: enqueued.append((user_id, goal, agent_id, True, context_note)) or {"id": 5})
    monkeypatch.setattr(tg_gateway.voice_stt, "transcribe_bytes", lambda data, filename, initial_prompt=None: "dame el informe trimestral", raising=False)

    message = {"message_id": 30, "from": {"id": 111}, "chat": {"id": 222}, "voice": {"file_id": "F1", "duration": 4}}
    asyncio.run(gateway._handle_message(1, client, message))

    assert client.downloads == ["F1"]
    assert enqueued and "dame el informe trimestral" in enqueued[0][1]
    assert recorded.get("via_voice") is True
    assert any("Transcripción" in item.get("text", "") for item in client.sent)


def test_voice_transcription_failure_notifies(monkeypatch):
    monkeypatch.setattr(tg_store, "recent_history", lambda *a, **k: [])
    gateway = TelegramGateway()
    client = FakeTelegramClient()
    monkeypatch.setattr(tg_store, "get_agent_telegram_config", lambda agent_id: {"telegram_allowlist": "111:juan"})
    monkeypatch.setattr(tg_store, "resolve_allowlisted_user", lambda raw, sender: "juan")
    monkeypatch.setattr(tg_store, "resolve_user_id_by_username", lambda username: 7)
    monkeypatch.setattr(tg_store, "record_inbound", lambda *a, **k: 1)

    def boom(data, filename):
        raise RuntimeError("voice service down")

    monkeypatch.setattr(tg_gateway.voice_stt, "transcribe_bytes", boom, raising=False)

    message = {"message_id": 31, "from": {"id": 111}, "chat": {"id": 222}, "voice": {"file_id": "F2"}}
    asyncio.run(gateway._handle_message(1, client, message))

    assert any("No pude transcribir" in item.get("text", "") for item in client.sent)
    assert all("Tarea #" not in item.get("text", "") for item in client.sent)


def test_voice_silence_reported(monkeypatch):
    monkeypatch.setattr(tg_store, "recent_history", lambda *a, **k: [])
    gateway = TelegramGateway()
    client = FakeTelegramClient()
    monkeypatch.setattr(tg_store, "get_agent_telegram_config", lambda agent_id: {"telegram_allowlist": "111:juan"})
    monkeypatch.setattr(tg_store, "resolve_allowlisted_user", lambda raw, sender: "juan")
    monkeypatch.setattr(tg_store, "resolve_user_id_by_username", lambda username: 7)
    monkeypatch.setattr(tg_gateway.voice_stt, "transcribe_bytes", lambda data, filename, initial_prompt=None: "", raising=False)

    message = {"message_id": 32, "from": {"id": 111}, "chat": {"id": 222}, "voice": {"file_id": "F3"}}
    asyncio.run(gateway._handle_message(1, client, message))
    assert any("No escuché nada" in item.get("text", "") for item in client.sent)


# ---------- outgoing voice delivery ----------


async def fake_send_voice(self, chat_id, ogg):
    global _sent_voices
    _sent_voices.append(ogg)
    return 99

_sent_voices: list[bytes] = []


def _patch_voice_client(monkeypatch):
    _sent_voices.clear()
    monkeypatch.setattr(tg_gateway.TelegramClient, 'send_voice', fake_send_voice)


def test_voice_result_delivered_as_voice_note(monkeypatch):
    _patch_voice_client(monkeypatch)
    gateway = TelegramGateway()
    client = FakeTelegramClient()
    monkeypatch.setattr(tg_store, "get_agent_bot_token", lambda agent_id: "token")
    monkeypatch.setattr(tg_store, "record_outbound", lambda *a, **k: None)
    monkeypatch.setattr(voice_tts, "synthesize_chunks", lambda text, max_chars=1400: ["primera parte", "segunda parte"])
    monkeypatch.setattr(voice_tts, "synthesize", lambda text: b"wav")
    monkeypatch.setattr(voice_tts, "wav_to_ogg", lambda wav: b"ogg")

    row = {"id": 1, "agent_id": 1, "chat_id": 222, "task_id": 5, "notified_status": None,
           "task_status": "completed", "result": "resultado", "error": "", "user_id": 7, "via_voice": True}
    monkeypatch.setattr(tg_store, "pending_deliveries", lambda: [row])
    marked: list[tuple] = []
    monkeypatch.setattr(tg_store, "mark_notified", lambda row_id, status, delivered=False: marked.append((row_id, status, delivered)))

    asyncio.run(gateway._deliver_outcomes())
    assert len(_sent_voices) == 2
    assert _sent_voices == [b"ogg", b"ogg"]
    assert not [s for s in client.sent if "resultado" in s.get("text", "")]
    assert marked == [(1, "completed", True)]


def test_voice_result_falls_back_to_text_when_tts_fails(monkeypatch):
    texts: list[str] = []
    async def fake_send_message(self, chat_id, text, reply_markup=None, parse_mode=None):
        texts.append(text)
    monkeypatch.setattr(tg_gateway.TelegramClient, "send_message", fake_send_message)
    _patch_voice_client(monkeypatch)
    gateway = TelegramGateway()
    client = FakeTelegramClient()
    monkeypatch.setattr(tg_store, "get_agent_bot_token", lambda agent_id: "token")
    monkeypatch.setattr(tg_store, "record_outbound", lambda *a, **k: None)
    monkeypatch.setattr(voice_tts, "synthesize_chunks", lambda text, max_chars=1400: ["parte uno"])

    def boom(text):
        raise RuntimeError("piper down")

    monkeypatch.setattr(voice_tts, "synthesize", boom)
    row = {"id": 2, "agent_id": 1, "chat_id": 222, "task_id": 6, "notified_status": None,
           "task_status": "completed", "result": "resultado en texto", "error": "", "user_id": 7, "via_voice": True}
    monkeypatch.setattr(tg_store, "pending_deliveries", lambda: [row])
    monkeypatch.setattr(tg_store, "mark_notified", lambda *a, **k: None)

    asyncio.run(gateway._deliver_outcomes())
    assert _sent_voices == []
    assert texts == ["parte uno"]


def test_voice_result_long_text_falls_back_after_two_notes(monkeypatch):
    texts: list[str] = []
    async def fake_send_message(self, chat_id, text, reply_markup=None, parse_mode=None):
        texts.append(text)
    monkeypatch.setattr(tg_gateway.TelegramClient, "send_message", fake_send_message)
    _patch_voice_client(monkeypatch)
    gateway = TelegramGateway()
    client = FakeTelegramClient()
    monkeypatch.setattr(tg_store, "get_agent_bot_token", lambda agent_id: "token")
    monkeypatch.setattr(tg_store, "record_outbound", lambda *a, **k: None)
    chunks = ["c1", "c2", "c3", "c4"]
    monkeypatch.setattr(voice_tts, "synthesize_chunks", lambda text, max_chars=1400: chunks)
    monkeypatch.setattr(voice_tts, "synthesize", lambda text: b"wav")
    monkeypatch.setattr(voice_tts, "wav_to_ogg", lambda wav: b"ogg")

    row = {"id": 3, "agent_id": 1, "chat_id": 222, "task_id": 7, "notified_status": None,
           "task_status": "completed", "result": "x", "error": "", "user_id": 7, "via_voice": True}
    monkeypatch.setattr(tg_store, "pending_deliveries", lambda: [row])
    monkeypatch.setattr(tg_store, "mark_notified", lambda *a, **k: None)

    asyncio.run(gateway._deliver_outcomes())
    assert len(_sent_voices) == 2
    assert any("c3" in t and "c4" in t for t in texts)


# ---------- pure helpers ----------


def test_synthesize_chunks_sentence_boundaries():
    text = ". ".join(f"Oración número {i} algo más larga" for i in range(1, 60))
    chunks = voice_tts.synthesize_chunks(text, max_chars=300)
    assert all(len(c) <= 300 for c in chunks)
    assert "".join(chunks).replace(" ", "").startswith("Oraciónnúmero1".replace(" ", ""))


def test_synthesize_chunks_short_passthrough():
    assert voice_tts.synthesize_chunks("hola") == ["hola"]
    assert voice_tts.synthesize_chunks("") == []


def test_synthesize_chunks_hard_split_long_sentence():
    chunks = voice_tts.synthesize_chunks("a" * 3500, max_chars=1000)
    assert [len(c) for c in chunks] == [1000, 1000, 1000, 500]

def test_deleted_task_notifies_telegram_user(monkeypatch):
    gateway = TelegramGateway()
    client = FakeTelegramClient()
    texts: list[str] = []
    async def fake_send_message(self, chat_id, text, reply_markup=None, parse_mode=None):
        texts.append(text)
    monkeypatch.setattr(tg_gateway.TelegramClient, 'send_message', fake_send_message)
    monkeypatch.setattr(tg_store, 'get_agent_bot_token', lambda agent_id: 'token')
    monkeypatch.setattr(tg_store, 'record_outbound', lambda *a, **k: None)
    row = {'id': 9, 'agent_id': 1, 'chat_id': 222, 'task_id': None, 'notified_status': 'running',
           'task_status': None, 'result': '', 'error': '', 'user_id': 7, 'via_voice': True}
    monkeypatch.setattr(tg_store, 'pending_deliveries', lambda: [row])
    marked: list[tuple] = []
    monkeypatch.setattr(tg_store, 'mark_notified', lambda row_id, status, delivered=False: marked.append((row_id, status, delivered)))

    asyncio.run(gateway._deliver_outcomes())
    assert any('eliminada' in t for t in texts)
    assert marked == [(9, 'deleted', True)]

