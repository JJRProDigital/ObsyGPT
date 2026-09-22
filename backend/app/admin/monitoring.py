"""Admin monitoring endpoints: metrics and diagnostics."""

import os
from typing import Annotated

from fastapi import APIRouter, Query, Request

from ..auth import routes as auth
from . import queries


router = APIRouter()


@router.get("/diagnostics")
def diagnostics(request: Request):
    auth.require_admin(request)
    counts = queries.fetch_one(
        """
        SELECT
            (SELECT COUNT(*) AS users FROM users) AS users,
            (SELECT COUNT(*) AS agents FROM agents) AS agents,
            (SELECT COUNT(*) AS workflows FROM workflows) AS workflows,
            (SELECT COUNT(*) AS mcp_servers FROM mcp_servers) AS mcp_servers;
        """,
        (),
    )
    providers = queries.fetch_all(
        """
        SELECT
            p.id,
            p.name,
            p.provider_type,
            p.enabled,
            p.api_key_env,
            COUNT(m.id) AS configured_models
        FROM providers p
        LEFT JOIN models m ON m.provider_id = p.id
        GROUP BY p.id, p.name, p.provider_type, p.enabled, p.api_key_env
        ORDER BY p.name;
        """
    )
    for provider in providers:
        provider["api_key_configured"] = bool(os.getenv(provider["api_key_env"])) if provider["api_key_env"] else True
        provider["ready"] = bool(provider["enabled"] and provider["configured_models"] > 0 and provider["api_key_configured"])
    return {"counts": counts, "providers": providers}


@router.get("/metrics")
def metrics(request: Request, days: Annotated[int, Query(ge=1, le=90)] = 14):
    auth.require_admin(request)
    interval_where = "WHERE created_at >= NOW() - (%s * INTERVAL '1 day')"
    interval_params = (days,)
    summary = queries.fetch_one(
        f"""
        SELECT
            COUNT(*) AS runs,
            COUNT(*) FILTER (WHERE status = 'completed') AS completed,
            COUNT(*) FILTER (WHERE status = 'failed') AS failed,
            COUNT(*) FILTER (WHERE status NOT IN ('completed', 'failed')) AS other,
            COUNT(DISTINCT user_id) AS active_users,
            COALESCE(AVG(EXTRACT(EPOCH FROM (completed_at - created_at))) FILTER (WHERE status = 'completed' AND completed_at IS NOT NULL), 0) AS avg_duration_seconds
        FROM agent_runs {interval_where};
        """,
        interval_params,
    )
    runs_per_day = queries.fetch_all(
        f"""
        SELECT
            DATE_TRUNC('day', created_at)::date::text AS day,
            COUNT(*) FILTER (WHERE status = 'completed') AS completed,
            COUNT(*) FILTER (WHERE status = 'failed') AS failed,
            COUNT(*) FILTER (WHERE status NOT IN ('completed', 'failed')) AS other
        FROM agent_runs {interval_where}
        GROUP BY 1
        ORDER BY 1;
        """,
        interval_params,
    )
    tool_calls_per_day = queries.fetch_all(
        f"""
        SELECT
            DATE_TRUNC('day', created_at)::date::text AS day,
            COUNT(*) AS total,
            COUNT(*) FILTER (WHERE status = 'failed') AS failed
        FROM tool_calls {interval_where}
        GROUP BY 1
        ORDER BY 1;
        """,
        interval_params,
    )
    top_tools = queries.fetch_all(
        f"""
        SELECT
            skill_name AS name,
            COUNT(*) AS calls,
            COUNT(*) FILTER (WHERE status = 'failed') AS failed
        FROM tool_calls {interval_where}
        GROUP BY 1
        ORDER BY calls DESC
        LIMIT 15;
        """,
        interval_params,
    )
    mcp_calls = queries.fetch_all(
        f"""
        SELECT
            tool_name AS name,
            COUNT(*) AS calls,
            COUNT(*) FILTER (WHERE status = 'failed') AS failed
        FROM mcp_calls {interval_where}
        GROUP BY 1
        ORDER BY calls DESC
        LIMIT 15;
        """,
        interval_params,
    )
    provider_fallbacks = queries.fetch_one(
        f"""
        SELECT COUNT(*) AS fallbacks
        FROM agent_events {interval_where} AND event_type = 'provider_fallback';
        """,
        interval_params,
    )
    agent_activity = queries.fetch_all(
        f"""
        SELECT
            COALESCE(a.name, 'n/a') AS agent,
            COUNT(*) AS runs,
            COUNT(*) FILTER (WHERE r.status = 'failed') AS failed
        FROM agent_runs r
        LEFT JOIN agents a ON a.id = r.agent_id
        {interval_where.replace('created_at', 'r.created_at')}
        GROUP BY 1
        ORDER BY runs DESC
        LIMIT 10;
        """,
        interval_params,
    )
    tool_categories = {"connectors": 0, "mcp": 0, "builtin": 0}
    for tool in top_tools:
        name = tool["name"]
        if name.startswith(("github_", "drive_")):
            tool_categories["connectors"] += tool["calls"]
        elif name.startswith("mcp_") or name.startswith("mcp:"):
            tool_categories["mcp"] += tool["calls"]
        else:
            tool_categories["builtin"] += tool["calls"]
    return {
        "days": days,
        "summary": summary,
        "runs_per_day": runs_per_day,
        "tool_calls_per_day": tool_calls_per_day,
        "top_tools": top_tools,
        "tool_categories": tool_categories,
        "mcp_calls": mcp_calls,
        "provider_fallbacks": provider_fallbacks["fallbacks"] if provider_fallbacks else 0,
        "agent_activity": agent_activity,
    }
