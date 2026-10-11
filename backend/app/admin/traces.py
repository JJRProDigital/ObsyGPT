"""Admin trace inspection endpoints: runs, events, sources, tool calls."""

from fastapi import APIRouter, Request

from ..auth import routes as auth
from . import queries


router = APIRouter()


@router.get("/agent-runs/{conversation_id}")
def list_agent_runs(conversation_id: int, request: Request):
    user_id = auth.require_user(request)
    return {"agent_runs": queries.fetch_all("SELECT id, conversation_id, agent_id, workflow_id, parent_run_id, status, final_response, created_at, completed_at FROM agent_runs WHERE user_id = %s AND conversation_id = %s ORDER BY created_at DESC;", (user_id, conversation_id))}


@router.get("/agent-events/{agent_run_id}")
def list_agent_events(agent_run_id: int, request: Request):
    user_id = auth.require_user(request)
    query = """
        SELECT e.id, e.agent_run_id, e.event_type, e.title, e.content, e.created_at
        FROM agent_events e
        JOIN agent_runs r ON r.id = e.agent_run_id
        WHERE r.user_id = %s AND e.agent_run_id = %s
        ORDER BY e.created_at, e.id;
    """
    return {"agent_events": queries.fetch_all(query, (user_id, agent_run_id))}


@router.get("/sources/{agent_run_id}")
def list_sources(agent_run_id: int, request: Request):
    user_id = auth.require_user(request)
    query = """
        SELECT s.id, s.agent_run_id, s.url, s.title, s.snippet, s.created_at
        FROM sources s
        JOIN agent_runs r ON r.id = s.agent_run_id
        WHERE r.user_id = %s AND s.agent_run_id = %s
        ORDER BY s.created_at, s.id;
    """
    return {"sources": queries.fetch_all(query, (user_id, agent_run_id))}


@router.get("/tool-calls/{agent_run_id}")
def list_tool_calls(agent_run_id: int, request: Request):
    user_id = auth.require_user(request)
    query = """
        SELECT t.id, t.agent_run_id, t.skill_name, t.input_summary, t.output_summary, t.status, t.created_at
        FROM tool_calls t
        JOIN agent_runs r ON r.id = t.agent_run_id
        WHERE r.user_id = %s AND t.agent_run_id = %s
        ORDER BY t.created_at, t.id;
    """
    return {"tool_calls": queries.fetch_all(query, (user_id, agent_run_id))}
