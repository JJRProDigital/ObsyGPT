import os

import pytest
from fastapi import HTTPException

from app.voice import stt, tts
from app.voice.routes import MAX_TTS_CHARS, MAX_TTS_TOTAL_CHARS


class FakeSegment:
    def __init__(self, text):
        self.text = text


class FakeModel:
    def __init__(self, segments):
        self._segments = [FakeSegment(s) for s in segments]

    def transcribe(self, path, language=None, initial_prompt=None):
        return self._segments, {"language": language}


def test_transcribe_joins_segments(monkeypatch, tmp_path):
    data = b"fakeaudio"
    monkeypatch.setattr(stt, "get_model", lambda: FakeModel(["Hola", "mundo."]))
    text = stt.transcribe_bytes(data, "note.ogg")
    assert text == "Hola mundo."


def test_transcribe_empty_returns_empty(monkeypatch):
    monkeypatch.setattr(stt, "get_model", lambda: FakeModel(["x"]))
    assert stt.transcribe_bytes(b"", "a.ogg") == ""


def test_transcribe_rejects_oversized(monkeypatch):
    monkeypatch.setattr(stt, "get_model", lambda: FakeModel([]))
    with pytest.raises(ValueError):
        stt.transcribe_bytes(b"x" * (stt.MAX_AUDIO_BYTES + 1), "a.ogg")


def test_transcribe_cleans_temp_file(monkeypatch, tmp_path):
    seen = {}
    real_unlink = os.unlink

    def spy(path):
        seen["removed"] = True
        real_unlink(path)

    monkeypatch.setattr(stt.os, "unlink", spy)
    monkeypatch.setattr(stt, "get_model", lambda: FakeModel(["hola"]))
    stt.transcribe_bytes(b"data", "a.wav")
    assert seen.get("removed") is True


class FakeChunk:
    def __init__(self, data):
        self.audio_int16_bytes = data


class FakeVoice:
    class config:
        sample_rate = 16000

    def synthesize(self, text, syn_config=None):
        yield FakeChunk(b"pcm" * (len(text) + 1))


def test_synthesize_returns_wav(monkeypatch):
    monkeypatch.setattr(tts, "get_voice", lambda: FakeVoice())
    wav = tts.synthesize("Hola")
    assert wav.startswith(b"RIFF")
    assert b"pcm" in wav


def test_synthesize_empty(monkeypatch):
    monkeypatch.setattr(tts, "get_voice", lambda: FakeVoice())
    assert tts.synthesize("") == b""


def test_synthesize_truncates_long_text(monkeypatch):
    monkeypatch.setattr(tts, "get_voice", lambda: FakeVoice())
    long_text = "a" * (MAX_TTS_CHARS + 500)
    wav = tts.synthesize(long_text)
    assert wav.startswith(b"RIFF")


def test_voice_paths_valid_es_voice():
    onnx, js, onnx_url, json_url = tts._voice_paths("es_ES-mls_10246-low")
    assert onnx.endswith("es_ES-mls_10246-low.onnx")
    assert "/es/es_ES/mls_10246/low/" in onnx_url.replace("\\", "/")
    assert json_url.endswith("es_ES-mls_10246-low.onnx.json")


def test_voice_paths_rejects_malformed():
    with pytest.raises(ValueError):
        tts._voice_paths("es")


# ---------- routes ----------


def test_transcribe_route_requires_auth():
    from fastapi.testclient import TestClient
    from fastapi import FastAPI, UploadFile
    from app.voice import routes as voice_routes

    app = FastAPI()
    app.include_router(voice_routes.router)

    def fake_require_user(request):
        raise HTTPException(status_code=401, detail="Not authenticated.")

    voice_routes.require_user = fake_require_user
    client = TestClient(app)
    response = client.post("/api/voice/transcribe", files={"file": ("a.ogg", b"data")})
    assert response.status_code == 401


def test_tts_route_rejects_long_text():
    from fastapi import FastAPI
    from fastapi.testclient import TestClient
    from app.voice import routes as voice_routes

    app = FastAPI()
    app.include_router(voice_routes.router)

    def fake_require_user(request):
        return 1

    voice_routes.require_user = fake_require_user
    client = TestClient(app)
    response = client.post("/api/voice/tts", json={"text": "a" * (MAX_TTS_TOTAL_CHARS + 1)})
    assert response.status_code == 400

def test_synthesize_long_text_single_pass(monkeypatch):
    class LongVoice:
        class config:
            sample_rate = 16000

        def synthesize(self, text, syn_config=None):
            yield FakeChunk(b'f' * (len(text) * 4))

    monkeypatch.setattr(tts, 'get_voice', lambda: LongVoice())
    text = 'ab ' * 1000
    wav = tts.synthesize(text)
    import wave as _wave
    import io as _io
    with _wave.open(_io.BytesIO(wav), 'rb') as r:
        assert r.getnframes() > 5000

def test_synthesize_strips_markdown(monkeypatch):
    captured = {}

    class CapturingVoice:
        class config:
            sample_rate = 16000

        def synthesize(self, text, syn_config=None):
            captured['text'] = text
            yield FakeChunk(b'pcm')

    monkeypatch.setattr(tts, 'get_voice', lambda: CapturingVoice())
    tts.synthesize('**Hola** mundo\n\n# T\u00edtulo\n---\n[link](https://x.com)')
    assert '*' not in captured['text']
    assert '#' not in captured['text']
    assert 'https' not in captured['text']
    assert 'Hola' in captured['text'] and 'T\u00edtulo' in captured['text']

