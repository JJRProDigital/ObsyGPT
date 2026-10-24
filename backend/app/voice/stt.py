"""Speech-to-text via faster-whisper. Model loads lazily on first use (downloaded once)."""

import logging
import os
import tempfile

logger = logging.getLogger("obsygpt.voice")

_model = None

MAX_AUDIO_BYTES = 20 * 1024 * 1024


def _settings() -> tuple[str, str | None]:
    return os.getenv("VOICE_STT_MODEL", "medium"), os.getenv("VOICE_STT_LANGUAGE", "es") or None


def get_model():
    global _model
    if _model is None:
        from faster_whisper import WhisperModel

        model_name, _ = _settings()
        logger.info("Loading Whisper STT model '%s'...", model_name)
        _model = WhisperModel(model_name, device="cpu", compute_type="int8")
    return _model


def transcribe_bytes(data: bytes, filename: str = "audio.ogg", initial_prompt: str | None = None) -> str:
    """Transcribes an audio clip (ogg/opus, wav, mp3...) to plain text.

    initial_prompt biases recognition toward domain vocabulary (e.g. recent
    conversation context), which measurably improves accuracy.
    """
    if not data:
        return ""
    if len(data) > MAX_AUDIO_BYTES:
        raise ValueError("Audio file too large.")
    _, language = _settings()
    suffix = os.path.splitext(filename)[1] or ".ogg"
    with tempfile.NamedTemporaryFile(suffix=suffix, delete=False) as tmp:
        tmp.write(data)
        tmp_path = tmp.name
    try:
        segments, _info = get_model().transcribe(tmp_path, language=language, initial_prompt=initial_prompt or None)
        text = " ".join(segment.text.strip() for segment in segments).strip()
        return text
    finally:
        try:
            os.unlink(tmp_path)
        except OSError:
            pass
