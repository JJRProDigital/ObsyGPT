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
from .workspace.routes import router as workspace_router


settings = get_settings()


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncIterator[None]:
    manager = TaskManager()
    set_manager(manager)
    summary = manager.auto_resume()
    print("TaskManager started:", summary)
    yield
    await manager.stop()
    print("TaskManager stopped")


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
app.include_router(workspace_router)
