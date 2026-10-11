"""Text-to-speech via piper. The Spanish voice model downloads once on first use."""

import io
import logging
import os
import urllib.request
import wave

logger = logging.getLogger("obsygpt.voice")

_voice = None

MAX_TTS_CHARS = 1500
HF_BASE = "https://huggingface.co/rhasspy/piper-voices/resolve/v1.0.0"


def _settings() -> tuple[str, str]:
    data_dir = os.getenv("VOICE_DATA_DIR", os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(__file__))), "voice-data"))
    voice = os.getenv("VOICE_TTS_VOICE", "es_ES-sharvard-medium")
    return data_dir, voice


def _voice_paths(voice: str) -> tuple[str, str, str, str]:
    """Returns (onnx_path, json_path, onnx_url, json_url) for a voice like 'es_ES-mls_10246-low'."""
    parts = voice.split("-")
    if len(parts) < 3:
        raise ValueError(f"Invalid piper voice name: {voice}")
    lang = parts[0].split("_")[0]
    dataset, quality = parts[0], parts[-1]
    model_dir = "-".join(parts[1:-1])
    hf_dir = f"{lang}/{dataset}/{model_dir}/{quality}"
    data_dir, _ = _settings()
    base = os.path.join(data_dir, hf_dir)
    return (
        os.path.join(base, f"{voice}.onnx"),
        os.path.join(base, f"{voice}.onnx.json"),
        f"{HF_BASE}/{hf_dir}/{voice}.onnx",
        f"{HF_BASE}/{hf_dir}/{voice}.onnx.json",
    )


def _download_if_missing(path: str, url: str) -> None:
    if os.path.exists(path):
        return
    os.makedirs(os.path.dirname(path), exist_ok=True)
    logger.info("Downloading voice model %s...", os.path.basename(path))
    urllib.request.urlretrieve(url, path)


def get_voice():
    global _voice
    if _voice is None:
        from piper import PiperVoice

        _, voice_name = _settings()
        onnx_path, json_path, onnx_url, json_url = _voice_paths(voice_name)
        _download_if_missing(onnx_path, onnx_url)
        _download_if_missing(json_path, json_url)
        logger.info("Loading Piper TTS voice '%s'...", voice_name)
        _voice = PiperVoice.load(onnx_path)
    return _voice


def _synthesis_config():
    """Tuned synthesis config: less noise = no babbling, slightly slower = full word formation."""
    from piper.config import SynthesisConfig

    return SynthesisConfig(
        length_scale=float(os.getenv("VOICE_LENGTH_SCALE", "1.05")),
        noise_scale=float(os.getenv("VOICE_NOISE_SCALE", "0.667")),
        noise_w_scale=float(os.getenv("VOICE_NOISE_W_SCALE", "0.6")),
    )


def strip_for_speech(text: str) -> str:
    """Removes markdown syntax so the voice doesn't read symbols aloud."""
    import re as _re

    text = _re.sub(r"```[\s\S]*?```", " (código omitido) ", text)
    text = _re.sub(r"\[([^\]]+)\]\(([^)]+)\)", r"\1", text)
    text = _re.sub(r"^#{1,6}\s+", "", text, flags=_re.MULTILINE)
    text = _re.sub(r"(\*\*|__)(.*?)\1", r"\2", text, flags=_re.DOTALL)
    text = _re.sub(r"(\*|_)([^*_]*?)\1", r"\2", text, flags=_re.DOTALL)
    text = _re.sub(r"`([^`]+)`", r"\1", text)
    text = _re.sub(r"^---+\s*$", "", text, flags=_re.MULTILINE)
    text = text.replace("|", " ")
    text = _re.sub(r"[ \t]{2,}", " ", text)
    text = _re.sub(r"\n{3,}", "\n\n", text)
    return text.strip()


def synthesize(text: str) -> bytes:
    """Synthesizes the full text in a single piper pass (continuous prosody, no chunk jumps)."""
    text = strip_for_speech((text or "").strip())
    if not text:
        return b""
    voice = get_voice()
    buffer = io.BytesIO()
    with wave.open(buffer, "wb") as wav_file:
        wav_file.setframerate(voice.config.sample_rate)
        wav_file.setsampwidth(2)
        wav_file.setnchannels(1)
        for chunk in voice.synthesize(text, syn_config=_synthesis_config()):
            data = getattr(chunk, "audio_int16_bytes", None)
            if data:
                wav_file.writeframes(data)
    return buffer.getvalue()


def synthesize_chunks(text: str, max_chars: int = 1400) -> list[str]:
    """Splits text into TTS-sized chunks at sentence boundaries."""
    text = (text or "").strip()
    if not text:
        return []
    if len(text) <= max_chars:
        return [text]
    import re as _re

    sentences = _re.split(r"(?<=[.!?…])\s+", text)
    chunks: list[str] = []
    current = ""
    for sentence in sentences:
        if len(current) + len(sentence) + 1 <= max_chars:
            current = (current + " " + sentence).strip()
            continue
        if current:
            chunks.append(current)
        while len(sentence) > max_chars:
            chunks.append(sentence[:max_chars])
            sentence = sentence[max_chars:]
        current = sentence
    if current:
        chunks.append(current)
    return chunks


def wav_to_ogg(wav: bytes) -> bytes:
    """Converts wav (PCM) to ogg/opus via ffmpeg — the format Telegram sendVoice expects."""
    import subprocess
    import tempfile

    with tempfile.NamedTemporaryFile(suffix=".wav", delete=False) as wav_tmp:
        wav_tmp.write(wav)
        wav_path = wav_tmp.name
    ogg_path = wav_path + ".ogg"
    try:
        subprocess.run(
            ["ffmpeg", "-y", "-i", wav_path, "-c:a", "libopus", "-b:a", "32k", ogg_path],
            capture_output=True,
            check=True,
        )
        with open(ogg_path, "rb") as ogg_file:
            return ogg_file.read()
    finally:
        for cleanup in (wav_path, ogg_path):
            try:
                os.unlink(cleanup)
            except OSError:
                pass
