import logging
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from starlette.middleware.sessions import SessionMiddleware

from .admin.routes import router as admin_router
from .agent.routes import router as agent_router
from .auth.routes import router as auth_router
from .chat.routes import router as chat_router
from .config import get_settings
from .connectors.routes import router as connectors_router
from .db import connect
from .files.routes import router as files_router
from .memory.routes import router as memory_router
from .projects.routes import router as projects_router
from .tasks.manager import TaskManager
from .tasks.routes import router as tasks_router
from .tasks.routes import set_manager
from .telegram.gateway import get_gateway
from .triggers.engine import get_engine
from .triggers.routes import router as triggers_router
from .v1.routes import router as v1_router
from .workspace.routes import router as workspace_router
from .voice.routes import router as voice_router


logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")
logger = logging.getLogger("obsygpt.main")

settings = get_settings()


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncIterator[None]:
    manager = TaskManager()
    set_manager(manager)
    summary = await manager.start()
    logger.info("TaskManager started: %s", summary)
    # Warm up voice models in the background so the first transcription/TTS is fast.
    def _warm_voice() -> None:
        try:
            from .voice import stt as voice_stt
            from .voice import tts as voice_tts

            voice_stt.get_model()
            voice_tts.get_voice()
            logger.info('Voice models warm')
        except Exception as error:
            logger.warning('Voice warmup skipped: %s', error)

    import threading

    threading.Thread(target=_warm_voice, daemon=True, name='voice-warmup').start()

    # Warm up the embedding model in the background so the first semantic search is fast.
    def _warm_semantic() -> None:
        try:
            from .memory.semantic.embeddings import get_embedding_service

            get_embedding_service().embed_query("warmup")
            logger.info('Semantic embeddings warm')
        except Exception as error:
            logger.warning('Semantic warmup skipped: %s', error)

    threading.Thread(target=_warm_semantic, daemon=True, name='obsygpt-semantic-warmup').start()

    # A previous process may have died mid-reindex; this one starts with no reindex running.
    try:
        from .memory.semantic.reindex import clear_stale_reindex

        clear_stale_reindex()
    except Exception as error:
        logger.warning('Reindex status reset skipped: %s', error)

    gateway = get_gateway()
    await gateway.start()
    engine = get_engine()
    await engine.start()
    try:
        yield
    finally:
        await engine.stop()
        await gateway.stop()
        await manager.stop()
        logger.info("TaskManager stopped")
        from .db import close_pool

        close_pool()


app = FastAPI(title="ObsyGPT API", lifespan=lifespan)

app.add_middleware(
    SessionMiddleware,
    secret_key=settings.session_secret,
    session_cookie="obsygpt_session",
    same_site=settings.cookie_samesite,
    https_only=settings.cookie_secure,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.frontend_origins,
    allow_credentials=True,
    allow_methods=["GET", "POST", "PUT", "PATCH", "DELETE"],
    allow_headers=["Content-Type"],
)


@app.get("/")
def root():
    return {"message": "ObsyGPT API is running"}


@app.get("/api/health")
def health():
    try:
        with connect() as connection:
            with connection.cursor() as cursor:
                cursor.execute("SELECT 1;")
                cursor.fetchone()
        return {"status": "healthy", "database": "ok"}
    except Exception:
        return {"status": "degraded", "database": "error"}


app.include_router(auth_router)
app.include_router(chat_router)
app.include_router(admin_router)
app.include_router(agent_router)
app.include_router(connectors_router)
app.include_router(files_router)
app.include_router(memory_router)
app.include_router(projects_router)
app.include_router(tasks_router)
app.include_router(triggers_router)
app.include_router(v1_router)
app.include_router(voice_router)
app.include_router(workspace_router)
