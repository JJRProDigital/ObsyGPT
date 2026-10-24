"""Tests for the optional Google Flow MCP bootstrap seeding (app.mcps.bootstrap)."""

import pytest

from app.mcps import bootstrap


class FakeCursor:
    def __init__(self, store):
        self.store = store

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc, traceback):
        return False

    def execute(self, query, params=()):
        self.store["queries"].append((query.strip(), params))
        normalized = " ".join(query.split())
        if normalized.startswith("SELECT id, url"):
            self.store["last_row"] = self.store.get("existing_row")
        elif normalized.startswith("UPDATE mcp_servers SET url"):
            old = self.store["existing_row"]
            self.store["existing_row"] = (old[0], params[0], old[2] if len(old) > 2 else None)
            self.store["last_row"] = None
        elif normalized.startswith("INSERT INTO mcp_servers"):
            self.store["last_row"] = (7,)

    def fetchone(self):
        return self.store.get("last_row")


class FakeConnection:
    def __init__(self, store):
        self.store = store

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc, traceback):
        return False

    def cursor(self):
        return FakeCursor(self.store)


@pytest.fixture()
def store(monkeypatch):
    state = {"queries": []}
    monkeypatch.setattr("app.db.connect", lambda: FakeConnection(state))
    return state


def test_seed_does_nothing_without_env(store, monkeypatch):
    monkeypatch.delenv("FLOW_MCP_URL", raising=False)
    bootstrap.seed_flow_mcp()
    assert store["queries"] == []


def test_seed_inserts_row_when_missing(store, monkeypatch):
    monkeypatch.setenv("FLOW_MCP_URL", "http://flow-mcp:8808/")
    bootstrap.seed_flow_mcp()
    inserts = [entry for entry in store["queries"] if "INSERT INTO mcp_servers" in entry[0]]
    assert len(inserts) == 1
    assert inserts[0][1] == (
        bootstrap.FLOW_MCP_NAME,
        bootstrap.FLOW_MCP_DESCRIPTION,
        "http://flow-mcp:8808",
    )


def test_seed_updates_url_when_changed(store, monkeypatch):
    store["existing_row"] = (3, "http://old:1", bootstrap.FLOW_MCP_DESCRIPTION)
    monkeypatch.setenv("FLOW_MCP_URL", "http://flow-mcp:8808")
    bootstrap.seed_flow_mcp()
    updates = [entry for entry in store["queries"] if entry[0].startswith("UPDATE mcp_servers SET url")]
    assert updates == [
        ("UPDATE mcp_servers SET url = %s, description = %s WHERE id = %s;", ("http://flow-mcp:8808", bootstrap.FLOW_MCP_DESCRIPTION, 3))
    ]
    assert store["existing_row"] == (3, "http://flow-mcp:8808", bootstrap.FLOW_MCP_DESCRIPTION)


def test_seed_is_noop_when_url_matches(store, monkeypatch):
    store["existing_row"] = (3, "http://flow-mcp:8808", bootstrap.FLOW_MCP_DESCRIPTION)
    monkeypatch.setenv("FLOW_MCP_URL", "http://flow-mcp:8808")
    bootstrap.seed_flow_mcp()
    writes = [entry for entry in store["queries"] if not entry[0].startswith("SELECT")]
    assert writes == []
