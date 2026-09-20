import os

os.environ.setdefault("DATABASE_URL", "postgresql://postgres:pass@localhost:5432/obsygpt")
os.environ.setdefault("OPENROUTER_API_KEY", "test")

from app.main import health


class FakeCursor:
    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc, traceback):
        return False

    def execute(self, query):
        self.query = query

    def fetchone(self):
        return (1,)


class FakeConnection:
    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc, traceback):
        return False

    def cursor(self):
        return FakeCursor()


def test_health_reports_database_ok(monkeypatch):
    monkeypatch.setattr("app.main.connect", lambda: FakeConnection(), raising=False)

    response = health()

    assert response == {"status": "healthy", "database": "ok"}


def test_health_reports_degraded_when_database_fails(monkeypatch):
    def fail_connect():
        raise RuntimeError("db unavailable")

    monkeypatch.setattr("app.main.connect", fail_connect, raising=False)

    response = health()

    assert response == {"status": "degraded", "database": "error"}
