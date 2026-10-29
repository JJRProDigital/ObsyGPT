"""Initial ObsyGPT schema and seed data.

Revision ID: 0001_initial_obsygpt
Revises: None
Create Date: 2026-09-13
"""
from alembic import op
import sqlalchemy as sa


revision = "0001_initial_obsygpt"
down_revision = None
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table("users",
        sa.Column("id", sa.Integer(), sa.Identity(), primary_key=True),
        sa.Column("username", sa.String(length=50), nullable=False, unique=True),
        sa.Column("email", sa.String(length=255), nullable=False, unique=True),
        sa.Column("role", sa.String(length=20), server_default="user", nullable=False),
        sa.Column("password_hash", sa.Text(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("CURRENT_TIMESTAMP"), nullable=False),
        sa.CheckConstraint("role IN ('admin', 'user')"),
    )
    op.create_table("providers",
        sa.Column("id", sa.Integer(), sa.Identity(), primary_key=True),
        sa.Column("name", sa.String(length=100), nullable=False, unique=True),
        sa.Column("provider_type", sa.String(length=50), nullable=False),
        sa.Column("base_url", sa.Text()),
        sa.Column("api_key_env", sa.String(length=100)),
        sa.Column("enabled", sa.Boolean(), server_default=sa.text("true"), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("CURRENT_TIMESTAMP"), nullable=False),
    )
    op.create_table("models",
        sa.Column("id", sa.Integer(), sa.Identity(), primary_key=True),
        sa.Column("provider_id", sa.Integer(), sa.ForeignKey("providers.id", ondelete="CASCADE"), nullable=False),
        sa.Column("model_name", sa.String(length=200), nullable=False),
        sa.Column("display_name", sa.String(length=200), nullable=False),
        sa.Column("supports_text", sa.Boolean(), server_default=sa.text("true"), nullable=False),
        sa.Column("supports_streaming", sa.Boolean(), server_default=sa.text("true"), nullable=False),
        sa.Column("supports_vision", sa.Boolean(), server_default=sa.text("false"), nullable=False),
        sa.Column("supports_audio", sa.Boolean(), server_default=sa.text("false"), nullable=False),
        sa.Column("supports_tools", sa.Boolean(), server_default=sa.text("false"), nullable=False),
        sa.Column("supports_json", sa.Boolean(), server_default=sa.text("false"), nullable=False),
        sa.Column("context_window", sa.Integer()),
        sa.Column("enabled", sa.Boolean(), server_default=sa.text("true"), nullable=False),
        sa.UniqueConstraint("provider_id", "model_name"),
    )
    op.create_table("conversations",
        sa.Column("id", sa.Integer(), sa.Identity(), primary_key=True),
        sa.Column("user_id", sa.Integer(), sa.ForeignKey("users.id", ondelete="CASCADE"), nullable=False),
        sa.Column("title", sa.String(length=100), server_default="New Chat", nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("CURRENT_TIMESTAMP"), nullable=False),
    )
    op.create_table("messages",
        sa.Column("id", sa.Integer(), sa.Identity(), primary_key=True),
        sa.Column("conversation_id", sa.Integer(), sa.ForeignKey("conversations.id", ondelete="CASCADE"), nullable=False),
        sa.Column("role", sa.String(length=20), nullable=False),
        sa.Column("content", sa.Text(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("CURRENT_TIMESTAMP"), nullable=False),
        sa.CheckConstraint("role IN ('user', 'assistant')"),
    )
    op.create_table("agents",
        sa.Column("id", sa.Integer(), sa.Identity(), primary_key=True),
        sa.Column("name", sa.String(length=100), nullable=False, unique=True),
        sa.Column("description", sa.Text(), server_default="", nullable=False),
        sa.Column("system_prompt", sa.Text(), nullable=False),
        sa.Column("provider_id", sa.Integer(), sa.ForeignKey("providers.id", ondelete="SET NULL")),
        sa.Column("model_id", sa.Integer(), sa.ForeignKey("models.id", ondelete="SET NULL")),
        sa.Column("temperature", sa.Numeric(3, 2), server_default="0.70", nullable=False),
        sa.Column("internet_enabled", sa.Boolean(), server_default=sa.text("false"), nullable=False),
        sa.Column("multimodal_enabled", sa.Boolean(), server_default=sa.text("false"), nullable=False),
        sa.Column("enabled", sa.Boolean(), server_default=sa.text("true"), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("CURRENT_TIMESTAMP"), nullable=False),
    )
    op.create_table("skills",
        sa.Column("id", sa.Integer(), sa.Identity(), primary_key=True),
        sa.Column("name", sa.String(length=100), nullable=False, unique=True),
        sa.Column("description", sa.Text(), server_default="", nullable=False),
        sa.Column("enabled", sa.Boolean(), server_default=sa.text("true"), nullable=False),
    )
    op.create_table("agent_skills",
        sa.Column("agent_id", sa.Integer(), sa.ForeignKey("agents.id", ondelete="CASCADE"), nullable=False),
        sa.Column("skill_id", sa.Integer(), sa.ForeignKey("skills.id", ondelete="CASCADE"), nullable=False),
        sa.PrimaryKeyConstraint("agent_id", "skill_id"),
    )
    op.create_table("mcp_servers",
        sa.Column("id", sa.Integer(), sa.Identity(), primary_key=True),
        sa.Column("name", sa.String(length=100), nullable=False, unique=True),
        sa.Column("description", sa.Text(), server_default="", nullable=False),
        sa.Column("connection_type", sa.String(length=20), nullable=False),
        sa.Column("command", sa.Text()),
        sa.Column("url", sa.Text()),
        sa.Column("enabled", sa.Boolean(), server_default=sa.text("false"), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("CURRENT_TIMESTAMP"), nullable=False),
        sa.CheckConstraint("connection_type IN ('command', 'url')"),
    )
    op.create_table("agent_mcps",
        sa.Column("agent_id", sa.Integer(), sa.ForeignKey("agents.id", ondelete="CASCADE"), nullable=False),
        sa.Column("mcp_server_id", sa.Integer(), sa.ForeignKey("mcp_servers.id", ondelete="CASCADE"), nullable=False),
        sa.PrimaryKeyConstraint("agent_id", "mcp_server_id"),
    )
    op.create_table("workflows",
        sa.Column("id", sa.Integer(), sa.Identity(), primary_key=True),
        sa.Column("name", sa.String(length=100), nullable=False, unique=True),
        sa.Column("workflow_type", sa.String(length=30), nullable=False),
        sa.Column("enabled", sa.Boolean(), server_default=sa.text("true"), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("CURRENT_TIMESTAMP"), nullable=False),
        sa.CheckConstraint("workflow_type IN ('single_agent', 'sequential', 'supervisor', 'reviewer', 'parallel', 'debate')"),
    )
    op.create_table("workflow_steps",
        sa.Column("id", sa.Integer(), sa.Identity(), primary_key=True),
        sa.Column("workflow_id", sa.Integer(), sa.ForeignKey("workflows.id", ondelete="CASCADE"), nullable=False),
        sa.Column("agent_id", sa.Integer(), sa.ForeignKey("agents.id", ondelete="SET NULL")),
        sa.Column("step_order", sa.Integer(), nullable=False),
        sa.Column("step_name", sa.String(length=100), nullable=False),
        sa.UniqueConstraint("workflow_id", "step_order"),
    )
    op.create_table("agent_runs",
        sa.Column("id", sa.Integer(), sa.Identity(), primary_key=True),
        sa.Column("user_id", sa.Integer(), sa.ForeignKey("users.id", ondelete="CASCADE"), nullable=False),
        sa.Column("conversation_id", sa.Integer(), sa.ForeignKey("conversations.id", ondelete="CASCADE"), nullable=False),
        sa.Column("message_id", sa.Integer(), sa.ForeignKey("messages.id", ondelete="SET NULL")),
        sa.Column("agent_id", sa.Integer(), sa.ForeignKey("agents.id", ondelete="SET NULL")),
        sa.Column("workflow_id", sa.Integer(), sa.ForeignKey("workflows.id", ondelete="SET NULL")),
        sa.Column("status", sa.String(length=20), nullable=False),
        sa.Column("final_response", sa.Text()),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("CURRENT_TIMESTAMP"), nullable=False),
        sa.Column("completed_at", sa.DateTime(timezone=True)),
        sa.CheckConstraint("status IN ('running', 'completed', 'failed')"),
    )
    op.create_table("agent_events",
        sa.Column("id", sa.Integer(), sa.Identity(), primary_key=True),
        sa.Column("agent_run_id", sa.Integer(), sa.ForeignKey("agent_runs.id", ondelete="CASCADE"), nullable=False),
        sa.Column("event_type", sa.String(length=50), nullable=False),
        sa.Column("title", sa.String(length=200), nullable=False),
        sa.Column("content", sa.Text(), server_default="", nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("CURRENT_TIMESTAMP"), nullable=False),
    )
    op.create_table("tool_calls",
        sa.Column("id", sa.Integer(), sa.Identity(), primary_key=True),
        sa.Column("agent_run_id", sa.Integer(), sa.ForeignKey("agent_runs.id", ondelete="CASCADE"), nullable=False),
        sa.Column("skill_name", sa.String(length=100), nullable=False),
        sa.Column("input_summary", sa.Text(), server_default="", nullable=False),
        sa.Column("output_summary", sa.Text(), server_default="", nullable=False),
        sa.Column("status", sa.String(length=20), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("CURRENT_TIMESTAMP"), nullable=False),
        sa.CheckConstraint("status IN ('running', 'completed', 'failed')"),
    )
    op.create_table("mcp_calls",
        sa.Column("id", sa.Integer(), sa.Identity(), primary_key=True),
        sa.Column("agent_run_id", sa.Integer(), sa.ForeignKey("agent_runs.id", ondelete="CASCADE"), nullable=False),
        sa.Column("mcp_server_id", sa.Integer(), sa.ForeignKey("mcp_servers.id", ondelete="SET NULL")),
        sa.Column("tool_name", sa.String(length=100), nullable=False),
        sa.Column("input_summary", sa.Text(), server_default="", nullable=False),
        sa.Column("output_summary", sa.Text(), server_default="", nullable=False),
        sa.Column("status", sa.String(length=20), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("CURRENT_TIMESTAMP"), nullable=False),
        sa.CheckConstraint("status IN ('running', 'completed', 'failed')"),
    )
    op.create_table("attachments",
        sa.Column("id", sa.Integer(), sa.Identity(), primary_key=True),
        sa.Column("user_id", sa.Integer(), sa.ForeignKey("users.id", ondelete="CASCADE"), nullable=False),
        sa.Column("message_id", sa.Integer(), sa.ForeignKey("messages.id", ondelete="CASCADE")),
        sa.Column("file_name", sa.Text(), nullable=False),
        sa.Column("mime_type", sa.String(length=150), nullable=False),
        sa.Column("storage_path", sa.Text(), nullable=False),
        sa.Column("size_bytes", sa.Integer(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("CURRENT_TIMESTAMP"), nullable=False),
    )
    op.create_table("artifacts",
        sa.Column("id", sa.Integer(), sa.Identity(), primary_key=True),
        sa.Column("agent_run_id", sa.Integer(), sa.ForeignKey("agent_runs.id", ondelete="CASCADE")),
        sa.Column("attachment_id", sa.Integer(), sa.ForeignKey("attachments.id", ondelete="CASCADE")),
        sa.Column("artifact_type", sa.String(length=50), nullable=False),
        sa.Column("title", sa.String(length=200), nullable=False),
        sa.Column("content", sa.Text(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("CURRENT_TIMESTAMP"), nullable=False),
    )
    op.create_table("sources",
        sa.Column("id", sa.Integer(), sa.Identity(), primary_key=True),
        sa.Column("agent_run_id", sa.Integer(), sa.ForeignKey("agent_runs.id", ondelete="CASCADE")),
        sa.Column("url", sa.Text(), nullable=False),
        sa.Column("title", sa.Text(), server_default="", nullable=False),
        sa.Column("snippet", sa.Text(), server_default="", nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("CURRENT_TIMESTAMP"), nullable=False),
    )
    op.create_table("settings",
        sa.Column("key", sa.String(length=100), primary_key=True),
        sa.Column("value", sa.Text(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("CURRENT_TIMESTAMP"), nullable=False),
    )

    op.execute("""
    INSERT INTO providers (name, provider_type, base_url, api_key_env, enabled) VALUES
        ('OpenRouter', 'openrouter', 'https://openrouter.ai/api/v1', 'OPENROUTER_API_KEY', true),
        ('OpenAI', 'openai', 'https://api.openai.com/v1', 'OPENAI_API_KEY', false),
        ('Anthropic', 'anthropic', 'https://api.anthropic.com', 'ANTHROPIC_API_KEY', false),
        ('Gemini', 'gemini', 'https://generativelanguage.googleapis.com', 'GEMINI_API_KEY', false),
        ('Ollama', 'ollama', 'http://127.0.0.1:11434/v1', NULL, false),
        ('llama.cpp', 'llamacpp', 'http://127.0.0.1:8080/v1', NULL, false),
        ('Custom OpenAI-Compatible', 'openai_compatible', NULL, NULL, false);
    """)
    op.execute("""
    INSERT INTO models (provider_id, model_name, display_name, supports_text, supports_streaming, supports_vision, supports_audio, supports_tools, supports_json, context_window, enabled)
    SELECT p.id, seed.model_name, seed.display_name, seed.supports_text, seed.supports_streaming, seed.supports_vision, seed.supports_audio, seed.supports_tools, seed.supports_json, seed.context_window, seed.enabled
    FROM providers p
    JOIN (VALUES
        ('OpenRouter', 'nvidia/nemotron-3-super-120b-a12b:free', 'NVIDIA Nemotron 3 Super 120B', true, true, false, false, false, false, NULL::integer, true),
        ('OpenAI', 'gpt-4.1-mini', 'GPT-4.1 Mini', true, true, true, true, true, true, 1047576, false),
        ('Anthropic', 'claude-3-5-sonnet-latest', 'Claude 3.5 Sonnet', true, true, true, false, true, false, 200000, false),
        ('Gemini', 'gemini-1.5-pro', 'Gemini 1.5 Pro', true, true, true, true, true, true, 2000000, false),
        ('Ollama', 'llama3.1', 'Ollama llama3.1', true, true, false, false, false, true, NULL::integer, false),
        ('llama.cpp', 'local-model', 'llama.cpp local model', true, true, false, false, false, true, NULL::integer, false)
    ) AS seed(provider_name, model_name, display_name, supports_text, supports_streaming, supports_vision, supports_audio, supports_tools, supports_json, context_window, enabled)
    ON p.name = seed.provider_name;
    """)
    op.execute("""
    INSERT INTO skills (name, description, enabled) VALUES
        ('web_search', 'Search the web and return ranked results.', true),
        ('read_url', 'Read and extract clean content from a URL.', true),
        ('extract_pdf', 'Extract text and metadata from uploaded PDFs.', true),
        ('summarize_document', 'Summarize extracted document content.', true),
        ('analyze_image', 'Analyze an uploaded image with a vision-capable model.', true),
        ('critic_review', 'Review an intermediate answer for quality and accuracy.', true),
        ('final_answer', 'Synthesize a final user-facing answer.', true);
    """)
    op.execute("""
    INSERT INTO agents (name, description, system_prompt, provider_id, model_id, internet_enabled, multimodal_enabled, enabled)
    SELECT 'Default Assistant', 'Default ObsyGPT text assistant.', 'You are ObsyGPT, a helpful multi-agent AI assistant. Answer clearly and accurately.', p.id, m.id, false, false, true
    FROM providers p JOIN models m ON m.provider_id = p.id
    WHERE p.name = 'OpenRouter' AND m.model_name = 'nvidia/nemotron-3-super-120b-a12b:free';
    INSERT INTO agents (name, description, system_prompt, provider_id, model_id, internet_enabled, multimodal_enabled, enabled)
    SELECT seed.name, seed.description, seed.system_prompt, p.id, m.id, seed.internet_enabled, seed.multimodal_enabled, true
    FROM providers p JOIN models m ON m.provider_id = p.id
    JOIN (VALUES
        ('Research Agent', 'Finds useful context and source leads.', 'You are ObsyGPT Research Agent. Identify useful facts, gaps, and source leads. Be concise.', true, false),
        ('Writer Agent', 'Drafts clear final answers.', 'You are ObsyGPT Writer Agent. Turn the available context into a clear answer for the user.', false, false),
        ('Critic Agent', 'Reviews answers for accuracy and omissions.', 'You are ObsyGPT Critic Agent. Improve accuracy, identify missing caveats, and return a corrected final answer.', false, false)
    ) AS seed(name, description, system_prompt, internet_enabled, multimodal_enabled)
    ON p.name = 'OpenRouter' AND m.model_name = 'nvidia/nemotron-3-super-120b-a12b:free';
    """)
    op.execute("""
    INSERT INTO workflows (name, workflow_type, enabled) VALUES
        ('Default Single Agent', 'single_agent', true),
        ('Research Then Write', 'sequential', true),
        ('Writer With Critic', 'reviewer', true),
        ('Parallel Draft Review', 'parallel', true),
        ('Debate Then Judge', 'debate', true);
    INSERT INTO workflow_steps (workflow_id, agent_id, step_order, step_name)
    SELECT w.id, a.id, seed.step_order, seed.step_name
    FROM workflows w
    JOIN (VALUES
        ('Research Then Write', 'Research Agent', 1, 'Research'),
        ('Research Then Write', 'Writer Agent', 2, 'Write'),
        ('Writer With Critic', 'Writer Agent', 1, 'Draft'),
        ('Writer With Critic', 'Critic Agent', 2, 'Review'),
        ('Parallel Draft Review', 'Research Agent', 1, 'Research'),
        ('Parallel Draft Review', 'Writer Agent', 2, 'Draft'),
        ('Parallel Draft Review', 'Critic Agent', 3, 'Critique'),
        ('Debate Then Judge', 'Research Agent', 1, 'Position A'),
        ('Debate Then Judge', 'Writer Agent', 2, 'Position B'),
        ('Debate Then Judge', 'Critic Agent', 3, 'Judge')
    ) AS seed(workflow_name, agent_name, step_order, step_name) ON w.name = seed.workflow_name
    JOIN agents a ON a.name = seed.agent_name;
    INSERT INTO agent_skills (agent_id, skill_id)
    SELECT a.id, s.id
    FROM agents a
    JOIN (VALUES
        ('Research Agent', 'read_url'),
        ('Research Agent', 'web_search'),
        ('Critic Agent', 'critic_review'),
        ('Writer Agent', 'final_answer'),
        ('Default Assistant', 'final_answer')
    ) AS seed(agent_name, skill_name) ON a.name = seed.agent_name
    JOIN skills s ON s.name = seed.skill_name;
    """)


def downgrade() -> None:
    for table_name in [
        "settings", "sources", "artifacts", "attachments", "mcp_calls", "tool_calls",
        "agent_events", "agent_runs", "workflow_steps", "workflows", "agent_mcps",
        "mcp_servers", "agent_skills", "skills", "agents", "messages",
        "conversations", "models", "providers", "users",
    ]:
        op.drop_table(table_name)
