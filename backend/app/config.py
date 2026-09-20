import os
from dataclasses import dataclass

from dotenv import load_dotenv


load_dotenv()


@dataclass(frozen=True)
class Settings:
    database_url: str
    openrouter_api_key: str
    frontend_url: str
    frontend_origins: list[str]
    session_secret: str
    cookie_secure: bool
    cookie_samesite: str


def build_frontend_origins(frontend_url: str) -> list[str]:
    origins: list[str] = []
    for origin in [item.strip().rstrip("/") for item in frontend_url.split(",")]:
        if origin and origin not in origins:
            origins.append(origin)

        localhost_pair = None
        if origin.startswith("http://127.0.0.1:"):
            localhost_pair = origin.replace("http://127.0.0.1:", "http://localhost:", 1)
        elif origin.startswith("http://localhost:"):
            localhost_pair = origin.replace("http://localhost:", "http://127.0.0.1:", 1)

        if localhost_pair and localhost_pair not in origins:
            origins.append(localhost_pair)

    return origins


def get_settings() -> Settings:
    database_url = os.getenv("DATABASE_URL")
    openrouter_api_key = os.getenv("OPENROUTER_API_KEY", "")

    if not database_url:
        raise RuntimeError("DATABASE_URL is not configured.")

    frontend_url = os.getenv("FRONTEND_URL", "http://127.0.0.1:5173")

    return Settings(
        database_url=database_url,
        openrouter_api_key=openrouter_api_key,
        frontend_url=frontend_url,
        frontend_origins=build_frontend_origins(frontend_url),
        session_secret=os.getenv("SESSION_SECRET", "local-development-secret-change-me"),
        cookie_secure=os.getenv("COOKIE_SECURE", "false").lower() == "true",
        cookie_samesite=os.getenv("COOKIE_SAMESITE", "lax"),
    )
