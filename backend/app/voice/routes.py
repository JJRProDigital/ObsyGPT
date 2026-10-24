"""Voice endpoints: transcribe audio files, synthesize speech."""

import logging

from fastapi import APIRouter, File, HTTPException, Query, Request, Response, UploadFile
from pydantic import BaseModel

from ..auth.routes import require_user

logger = logging.getLogger("obsygpt.voice")

router = APIRouter(prefix="/api/voice", tags=["voice"])

MAX_UPLOAD_BYTES = 20 * 1024 * 1024
MAX_TTS_CHARS = 1500  # per synthesis chunk
MAX_TTS_TOTAL_CHARS = 20000


@router.post("/transcribe")
def transcribe_audio(request: Request, file: UploadFile = File(...)):
    require_user(request)
    from . import stt

    data = file.file.read(MAX_UPLOAD_BYTES + 1)
    if len(data) > MAX_UPLOAD_BYTES:
        raise HTTPException(status_code=413, detail="Audio file too large (max 20 MB).")
    try:
        text = stt.transcribe_bytes(data, file.filename or "audio.ogg")
    except ValueError as error:
        raise HTTPException(status_code=400, detail=str(error)) from error
    except Exception as error:  # noqa: BLE001 - model/ffmpeg failures surface as 503
        logger.warning("Transcription failed: %s", error)
        raise HTTPException(status_code=503, detail=f"Speech-to-text unavailable: {error}") from error
    return {"text": text}


class TtsPayload(BaseModel):
    text: str


@router.post("/tts")
def tts_audio(request: Request, payload: TtsPayload):
    require_user(request)
    text = payload.text.strip()
    if not text:
        raise HTTPException(status_code=400, detail="Empty text.")
    if len(text) > MAX_TTS_TOTAL_CHARS:
        raise HTTPException(status_code=400, detail=f"Text too long for speech (max {MAX_TTS_TOTAL_CHARS} characters).")
    from . import tts

    try:
        wav = tts.synthesize(text)
    except Exception as error:  # noqa: BLE001
        logger.warning("TTS failed: %s", error)
        raise HTTPException(status_code=503, detail=f"Text-to-speech unavailable: {error}") from error
    if not wav:
        raise HTTPException(status_code=400, detail="Empty text.")
    return Response(content=wav, media_type="audio/wav")
