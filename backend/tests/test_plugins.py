import pytest

from app.plugins import manifest as manifest_module
from app.plugins import service


def _valid_manifest() -> dict:
    return {
        "slug": "demo-pack",
        "name": "Demo Pack",
        "version": "1.0.0",
        "description": "Plugin de prueba",
        "skills": [{"name": "greet", "description": "Saluda", "body": "# Saluda\n\nDi hola."}],
        "mcps": [],
        "agents": [],
        "connectors": [],
    }


def test_validate_manifest_accepts_valid_manifest():
    normalized = manifest_module.validate_manifest(_valid_manifest())
    assert normalized["slug"] == "demo-pack"
    assert normalized["skills"][0]["triggers"] == ["user"]


def test_validate_manifest_rejects_bad_slug():
    manifest = _valid_manifest()
    manifest["slug"] = "Bad Slug!"
    with pytest.raises(ValueError, match="slug"):
        manifest_module.validate_manifest(manifest)


def test_validate_manifest_requires_skill_body():
    manifest = _valid_manifest()
    manifest["skills"][0]["body"] = "  "
    with pytest.raises(ValueError, match="skills\\[0\\].body is required"):
        manifest_module.validate_manifest(manifest)


def test_validate_manifest_rejects_bad_mcp_connection_type():
    manifest = _valid_manifest()
    manifest["mcps"] = [{"name": "x", "connection_type": "carrier-pigeon"}]
    with pytest.raises(ValueError, match="connection_type"):
        manifest_module.validate_manifest(manifest)


def test_validate_manifest_requires_agent_system_prompt():
    manifest = _valid_manifest()
    manifest["agents"] = [{"name": "Helper", "system_prompt": ""}]
    with pytest.raises(ValueError, match="agents\\[0\\].system_prompt is required"):
        manifest_module.validate_manifest(manifest)


def test_namespaced_skill_name_uses_hyphen():
    assert service.namespaced_skill_name("demo-pack", "greet") == "demo-pack-greet"


def _fake_connect(script):
    class FakeColumn:
        def __init__(self, name):
            self.name = name

    class FakeCursor:
        def __init__(self):
            self.rowcount = 0
            self._result = None
            self.description = None

        def __enter__(self):
            return self

        def __exit__(self, exc_type, exc, traceback):
            return False

        def execute(self, query, params=()):
            self.rowcount = 1 if query.strip().startswith("DELETE") else 0
            self._result = script(query, params)
            if "SELECT name, url" in query:
                self.description = [FakeColumn("name"), FakeColumn("url")]

        def fetchone(self):
            return self._result

        def fetchall(self):
            rows = self._result if isinstance(self._result, list) else ([self._result] if self._result else [])
            return [tuple(row) if not isinstance(row, tuple) else row for row in rows]

    class FakeConnection:
        def __enter__(self):
            return self

        def __exit__(self, exc_type, exc, traceback):
            return False

        def cursor(self):
            return FakeCursor()

    return FakeConnection


def test_install_plugin_creates_namespaced_components(monkeypatch):
    written = []
    manifest = _valid_manifest()
    manifest["agents"] = [{"name": "Helper Agent", "system_prompt": "Ayuda."}]

    def script(query, params):
        if "SELECT slug FROM plugins" in query:
            return None
        if "SELECT id FROM skills" in query:
            return None
        if "INSERT INTO skills" in query:
            return (51,)
        if "INSERT INTO agents" in query:
            return (7,)
        return None

    monkeypatch.setattr(service, "connect", _fake_connect(script))
    monkeypatch.setattr("app.admin.skill_files.write_skill_files", lambda skill, previous_name=None: written.append(skill["name"]))
    monkeypatch.setattr("app.mcps.gateway.McpGateway.validate", lambda self, config: {"valid": True})

    entry = {"manifest": manifest_module.validate_manifest(manifest), "source": "local", "marketplace_name": None}
    result = service.install_plugin(entry)

    assert result["slug"] == "demo-pack"
    assert result["refs"]["skill_ids"] == [51]
    assert result["refs"]["agent_ids"] == [7]
    assert written == ["demo-pack-greet"]


def test_install_plugin_rejects_duplicate_install(monkeypatch):
    monkeypatch.setattr(service, "connect", _fake_connect(lambda query, params: ("existing",) if "SELECT slug FROM plugins" in query else None))

    entry = {"manifest": manifest_module.validate_manifest(_valid_manifest()), "source": "local", "marketplace_name": None}
    with pytest.raises(ValueError, match="already installed"):
        service.install_plugin(entry)


def test_uninstall_plugin_removes_components_and_files(monkeypatch):
    deleted_files = []

    def script(query, params):
        if "SELECT installed_refs" in query:
            return ({"skill_ids": [51], "mcp_ids": [], "agent_ids": [7]},)
        if "DELETE FROM skills" in query:
            return ("demo-pack-greet",)
        return None

    monkeypatch.setattr(service, "connect", _fake_connect(script))
    monkeypatch.setattr("app.admin.skill_files.delete_skill_files", lambda name: deleted_files.append(name))

    result = service.uninstall_plugin("demo-pack")

    assert result["removed"]["skills"] == 1
    assert result["removed"]["agents"] == 1
    assert deleted_files == ["demo-pack-greet"]


def test_uninstall_plugin_fails_when_not_installed(monkeypatch):
    monkeypatch.setattr(service, "connect", _fake_connect(lambda query, params: None))
    with pytest.raises(ValueError, match="not installed"):
        service.uninstall_plugin("nope")


def test_add_marketplace_clones_public_https_repo(monkeypatch):
    captured = {}

    class FakeResult:
        returncode = 0
        stderr = ""

    def fake_run(args, capture_output, text, timeout, shell):
        captured.update({"args": args, "timeout": timeout, "shell": shell})
        return FakeResult()

    def script(query, params):
        if query.startswith("SELECT name, url"):
            return None
        return None

    monkeypatch.setattr(service.subprocess, "run", fake_run)
    monkeypatch.setattr(service, "connect", _fake_connect(script))
    monkeypatch.setattr(service, "MARKETPLACES_ROOT", service.PLUGINS_ROOT / "_test_marketplaces")

    result = service.add_marketplace("https://github.com/acme/plugins")

    assert result["name"] == "acme-plugins"
    assert captured["args"][0:4] == ["git", "clone", "--depth", "1"]
    assert captured["shell"] is False


def test_add_marketplace_rejects_duplicate_url(monkeypatch):
    def script(query, params):
        if query.startswith("SELECT name, url"):
            return ("acme-plugins", "https://github.com/acme/plugins")
        return None

    monkeypatch.setattr(service, "connect", _fake_connect(script))

    with pytest.raises(ValueError, match="already registered"):
        service.add_marketplace("https://github.com/acme/plugins")


def test_remove_marketplace_deletes_row(monkeypatch, tmp_path):
    import shutil as shutil_module

    class FakeCursor:
        rowcount = 1

        def __enter__(self):
            return self

        def __exit__(self, exc_type, exc, traceback):
            return False

        def execute(self, query, params=()):
            pass

        def fetchone(self):
            return None

    class FakeConnection:
        def __enter__(self):
            return self

        def __exit__(self, exc_type, exc, traceback):
            return False

        def cursor(self):
            return FakeCursor()

    monkeypatch.setattr(service, "connect", FakeConnection)
    monkeypatch.setattr(service, "MARKETPLACES_ROOT", tmp_path)
    (tmp_path / "acme-plugins").mkdir()

    assert service.remove_marketplace("acme-plugins") is True
    assert not (tmp_path / "acme-plugins").exists()
