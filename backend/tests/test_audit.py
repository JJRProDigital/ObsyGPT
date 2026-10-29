from pathlib import Path

from app.audit.store import AuditStore


def test_audit_migration_creates_audit_logs_table():
    migration = Path("migrations/versions/0002_audit_logs.py").read_text(encoding="utf-8")

    assert "audit_logs" in migration
    assert "actor_user_id" in migration
    assert "action" in migration
    assert "target_type" in migration
    assert "metadata" in migration


def test_audit_store_add_log_inserts_expected_values(monkeypatch):
    captured = {}

    class FakeCursor:
        def __enter__(self):
            return self

        def __exit__(self, exc_type, exc, traceback):
            return False

        def execute(self, query, params):
            captured["query"] = query
            captured["params"] = params

    class FakeConnection:
        def __enter__(self):
            return self

        def __exit__(self, exc_type, exc, traceback):
            return False

        def cursor(self):
            return FakeCursor()

    monkeypatch.setattr("app.audit.store.connect", lambda: FakeConnection())

    AuditStore().add_log(
        actor_user_id=1,
        action="user.role_updated",
        target_type="user",
        target_id=2,
        metadata={"role": "admin"},
    )

    assert "INSERT INTO audit_logs" in captured["query"]
    assert captured["params"][:4] == (1, "user.role_updated", "user", 2)
    assert '"role": "admin"' in captured["params"][4]
