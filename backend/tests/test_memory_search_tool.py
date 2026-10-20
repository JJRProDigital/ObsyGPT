from unittest.mock import patch

from app.agent.tools.memory import MemorySearchTool


def test_run_requires_query():
    result = MemorySearchTool(user_id=1).run({})
    assert result.ok is False and "query" in result.output


def test_run_formats_hits_with_source():
    hits = [{"text": "hablamos de pgvector", "score": 0.9, "source": "conversación", "conversation_id": 3, "title": "Chat DB", "when": "2026-10-01T10:00:00"}]
    with patch("app.agent.tools.memory.search_semantic", return_value=hits):
        result = MemorySearchTool(user_id=1).run({"query": "pgvector"})
    assert result.ok is True
    assert "1." in result.output and "Chat DB" in result.output and "hablamos de pgvector" in result.output


def test_run_degrades_when_service_unavailable():
    with patch("app.agent.tools.memory.search_semantic", side_effect=RuntimeError("down")):
        result = MemorySearchTool(user_id=1).run({"query": "pgvector"})
    assert result.ok is False and "disponible" in result.output


def test_run_reports_no_hits():
    with patch("app.agent.tools.memory.search_semantic", return_value=[]):
        result = MemorySearchTool(user_id=1).run({"query": "nada"})
    assert result.ok is True and "No encontré" in result.output
