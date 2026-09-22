"""Admin API composition: mounts every domain router under /api/admin.

Domain logic lives in the sibling modules (providers, models, agents, skills,
mcps, workflows, plugins, users, audit, traces, settings, monitoring); shared
helpers live in `queries` and `skill_files`. This module only composes the
router and re-exports public names for backwards compatibility.
"""

from fastapi import APIRouter

from . import (
    agents,
    audit,
    mcps,
    models,
    monitoring,
    plugins,
    providers,
    settings,
    skills,
    traces,
    users,
    workflows,
)


router = APIRouter(prefix="/api/admin", tags=["admin"])

for _domain in (users, providers, models, agents, settings, skills, mcps, workflows, plugins, audit, monitoring, traces):
    router.include_router(_domain.router)


# --- Backwards-compatible re-exports (tests and other modules import these) ---

from .providers import ProviderPayload, ProviderType, detect_provider_models  # noqa: E402,F401
from .models import ModelPayload, check_model_config, create_model, delete_model, list_models, update_model  # noqa: E402,F401
from .agents import (  # noqa: E402,F401
    AgentFallbackPayload,
    AgentPayload,
    AgentToolsPayload,
    assign_agent_skill,
    create_agent,
    list_agent_fallbacks,
    list_agent_skills,
    list_agent_tools,
    list_agents,
    remove_agent_skill,
    set_agent_fallbacks,
    set_agent_tools,
    update_agent,
)
from .users import UserRolePayload, ensure_admin_role_change_allowed, list_users, update_user_role  # noqa: E402,F401
from .skills import SkillGeneratePayload, SkillPayload, SkillRunPayload, create_skill, delete_skill, generate_skill, list_skills, run_skill, update_skill  # noqa: E402,F401
from .workflows import WorkflowPayload, create_workflow, list_workflows, update_workflow  # noqa: E402,F401
from .mcps import McpRunPayload, McpServerPayload, assign_agent_mcp, create_mcp_server, delete_mcp_server, inspect_mcp_server, list_agent_mcps, list_mcp_servers, remove_agent_mcp, run_mcp_server, update_mcp_server, validate_mcp_server  # noqa: E402,F401
from .plugins import PluginInstallPayload, PluginMarketplacePayload  # noqa: E402,F401
from .audit import list_audit_logs  # noqa: E402,F401
from .monitoring import diagnostics, metrics  # noqa: E402,F401
from .traces import list_agent_events, list_agent_runs, list_sources, list_tool_calls  # noqa: E402,F401
from .providers import create_provider, list_provider_definitions, list_providers, update_provider  # noqa: E402,F401
from .settings import GuardrailSettingsPayload, TasksSettingsPayload, list_guardrail_settings, list_tasks_settings, update_guardrail_settings, update_tasks_settings  # noqa: E402,F401
from .queries import ensure_positive_id, execute_returning, fetch_all, fetch_one  # noqa: E402,F401
from .skill_files import (  # noqa: E402,F401
    SKILLS_ROOT,
    build_skill_draft,
    delete_skill_files,
    ensure_safe_skill_name,
    render_skill_md,
    resource_paths,
    with_skill_md,
    write_skill_files,
)
