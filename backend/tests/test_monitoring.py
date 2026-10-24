import json

import pytest

from app.admin.routes import metrics
from app.monitoring import otel


class FakeRequest:
    session = {"user_id": 1, "role": "admin"}


def test_metrics_composes_categories_and_summary(monkeypatch):
    queries = []

    def fake_fetch_one(query, params=()):
        queries.append(query)
        if "agent_events" in query:
            return {"fallbacks": 2}
        return {"runs": 10, "completed": 8, "failed": 1, "other": 1, "active_users": 2, "avg_duration_seconds": 12.5}

    def fake_fetch_all(query, params=()):
        queries.append(query)
        if "skill_name" in query:
            return [
                {"name": "web_fetch", "calls": 30, "failed": 1},
                {"name": "github_search_repos", "calls": 12, "failed": 0},
                {"name": "mcp_filesystem_read", "calls": 4, "failed": 4},
            ]
        if "FROM mcp_calls" in query:
            return [{"name": "tools/list", "calls": 3, "failed": 0}]
        if "agent_runs r" in query:
            return [{"agent": "Default Assistant", "runs": 8, "failed": 1}]
        if "DATE_TRUNC" in query:
            return [{"day": "2026-09-18", "completed": 5, "failed": 1, "other": 0}]
        return []

    monkeypatch.setattr("app.auth.routes.require_admin", lambda request: 1)
    monkeypatch.setattr("app.admin.queries.fetch_one", fake_fetch_one)
    monkeypatch.setattr("app.admin.queries.fetch_all", fake_fetch_all)

    result = metrics(FakeRequest(), days=14)

    assert result["days"] == 14
    assert result["summary"]["runs"] == 10
    assert result["tool_categories"] == {"connectors": 12, "mcp": 4, "builtin": 30}
    assert result["provider_fallbacks"] == 2
    assert result["top_tools"][0]["name"] == "web_fetch"
    assert result["mcp_calls"] == [{"name": "tools/list", "calls": 3, "failed": 0}]
    assert any("provider_fallback" in query for query in queries)


def test_otel_emit_is_noop_without_endpoint(monkeypatch):
    monkeypatch.delenv("OTEL_EXPORTER_OTLP_ENDPOINT", raising=False)
    otel.record_user_prompt(5, "hola")
    assert otel.drain_for_tests() == []


def test_otel_redacts_content_by_default(monkeypatch):
    monkeypatch.setenv("OTEL_EXPORTER_OTLP_ENDPOINT", "http://collector.example.com:4318")
    monkeypatch.delenv("OTEL_CONTENT_CAPTURE", raising=False)
    monkeypatch.setattr(otel, "_ensure_worker", lambda: None)

    otel.record_user_prompt(4, "secreto")
    otel.record_assistant_response("gpt-x", 10, "respuesta secreta")
    otel.record_tool_result(7, "write_file", "completed", "contenido")

    records = otel.drain_for_tests()
    assert len(records) == 3
    by_event = {record["body"]["stringValue"]: record for record in records}
    prompt_attrs = {attribute["key"]: attribute["value"]["stringValue"] for attribute in by_event["user_prompt"]["attributes"]}
    response_attrs = {attribute["key"]: attribute["value"]["stringValue"] for attribute in by_event["assistant_response"]["attributes"]}
    tool_attrs = {attribute["key"]: attribute["value"]["stringValue"] for attribute in by_event["tool_result"]["attributes"]}
    assert prompt_attrs["prompt"] == "<REDACTED>"
    assert response_attrs["response"] == "<REDACTED>"
    assert tool_attrs["tool_output"] == "<REDACTED>"
    assert tool_attrs["run.id"] == "7"
    assert tool_attrs["success"] == "True"


def test_otel_content_capture_flags_include_content(monkeypatch):
    monkeypatch.setenv("OTEL_EXPORTER_OTLP_ENDPOINT", "http://collector.example.com:4318")
    monkeypatch.setenv("OTEL_CONTENT_CAPTURE", "prompts,responses")
    monkeypatch.setattr(otel, "_ensure_worker", lambda: None)

    otel.record_user_prompt(4, "hola contenido")
    otel.record_assistant_response("gpt-x", 10, "respuesta")
    otel.record_tool_result(1, "t", "completed", "detalle")

    records = otel.drain_for_tests()
    by_event = {record["body"]["stringValue"]: record for record in records}
    prompt_attrs = {attribute["key"]: attribute["value"]["stringValue"] for attribute in by_event["user_prompt"]["attributes"]}
    response_attrs = {attribute["key"]: attribute["value"]["stringValue"] for attribute in by_event["assistant_response"]["attributes"]}
    tool_attrs = {attribute["key"]: attribute["value"]["stringValue"] for attribute in by_event["tool_result"]["attributes"]}
    assert prompt_attrs["prompt"] == "hola contenido"
    assert response_attrs["response"] == "respuesta"
    assert tool_attrs["tool_output"] == "<REDACTED>"


def test_otel_post_batch_sends_otlp_logs_json(monkeypatch):
    captured = {}

    class FakeResponse:
        def __enter__(self):
            return self

        def __exit__(self, exc_type, exc, traceback):
            return False

        def read(self):
            return b"{}"

    def fake_urlopen(request, timeout):
        captured.update({"url": request.full_url, "body": json.loads(request.data.decode("utf-8")), "headers": dict(request.headers)})
        return FakeResponse()

    monkeypatch.setenv("OTEL_EXPORTER_OTLP_ENDPOINT", "http://collector.example.com:4318/")
    monkeypatch.setenv("OTEL_EXPORTER_OTLP_HEADERS", "Authorization=Bearer tok")
    monkeypatch.setattr(otel, "urlopen", fake_urlopen)

    record = {"timeUnixNano": "1", "severityText": "INFO", "body": {"stringValue": "user_prompt"}, "attributes": []}
    otel._post_batch([record])

    assert captured["url"] == "http://collector.example.com:4318/v1/logs"
    assert captured["headers"]["Authorization"] == "Bearer tok"
    log_records = captured["body"]["resourceLogs"][0]["scopeLogs"][0]["logRecords"]
    assert log_records == [record]
    service_attrs = captured["body"]["resourceLogs"][0]["resource"]["attributes"]
    assert {"key": "service.name", "value": {"stringValue": "obsygpt"}} in service_attrs


def test_otel_post_batch_swallows_errors(monkeypatch):
    def failing_urlopen(request, timeout):
        raise RuntimeError("collector down")

    monkeypatch.setenv("OTEL_EXPORTER_OTLP_ENDPOINT", "http://collector.example.com:4318")
    monkeypatch.setattr(otel, "urlopen", failing_urlopen)

    otel._post_batch([{"body": {"stringValue": "x"}}])
