"""Add agent loop tables

Revision ID: 0005_agent_loop
Revises: 0004_seed_standard_skill_bodies
Create Date: 2026-09-16
"""

from collections.abc import Sequence

from alembic import op
import sqlalchemy as sa


revision: str = "0005_agent_loop"
down_revision: str | None = "0004_seed_standard_skill_bodies"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column("agents", sa.Column("agentic_mode", sa.Boolean(), server_default=sa.text("false"), nullable=False))

    op.create_table(
        "agent_tool_permissions",
        sa.Column("agent_id", sa.Integer(), sa.ForeignKey("agents.id", ondelete="CASCADE"), primary_key=True),
        sa.Column("tool_name", sa.String(length=100), primary_key=True),
        sa.Column("allowed", sa.Boolean(), server_default=sa.text("true"), nullable=False),
    )

    op.create_table(
        "tool_approvals",
        sa.Column("id", sa.Integer(), sa.Identity(), primary_key=True),
        sa.Column("agent_run_id", sa.Integer(), sa.ForeignKey("agent_runs.id", ondelete="CASCADE"), nullable=False),
        sa.Column("user_id", sa.Integer(), sa.ForeignKey("users.id", ondelete="CASCADE"), nullable=False),
        sa.Column("conversation_id", sa.Integer(), sa.ForeignKey("conversations.id", ondelete="CASCADE"), nullable=False),
        sa.Column("tool_name", sa.String(length=100), nullable=False),
        sa.Column("args", sa.JSON(), server_default=sa.text("'{}'::json"), nullable=False),
        sa.Column("status", sa.String(length=20), server_default=sa.text("'pending'"), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("CURRENT_TIMESTAMP"), nullable=False),
        sa.Column("decided_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.create_index("ix_tool_approvals_pending", "tool_approvals", ["status", "user_id"])

    op.create_table(
        "agent_run_state",
        sa.Column("agent_run_id", sa.Integer(), sa.ForeignKey("agent_runs.id", ondelete="CASCADE"), primary_key=True),
        sa.Column("messages", sa.JSON(), server_default=sa.text("'[]'::json"), nullable=False),
        sa.Column("iterations", sa.Integer(), server_default=sa.text("0"), nullable=False),
        sa.Column("tool_call_count", sa.Integer(), server_default=sa.text("0"), nullable=False),
        sa.Column("thought_text", sa.Text(), server_default="", nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("CURRENT_TIMESTAMP"), nullable=False),
    )

    op.create_table(
        "app_settings",
        sa.Column("key", sa.String(length=100), primary_key=True),
        sa.Column("value", sa.JSON(), server_default=sa.text("'{}'::json"), nullable=False),
    )

    op.execute(
        """
        INSERT INTO app_settings (key, value)
        VALUES (
            'guardrails',
            '{"max_iterations": 12, "max_tool_calls": 25, "max_duration_seconds": 180, "max_tool_output_chars": 10000, "max_total_chars": 50000, "loop_repeat_limit": 3}'::json
        )
        ON CONFLICT (key) DO NOTHING;
        """
    )

    op.execute(
        """
        INSERT INTO agent_tool_permissions (agent_id, tool_name, allowed)
        SELECT a.id, seed.tool_name, true
        FROM agents a
        CROSS JOIN (VALUES
            ('read_file'),
            ('list_dir'),
            ('web_fetch')
        ) AS seed(tool_name)
        ON CONFLICT (agent_id, tool_name) DO NOTHING;
        """
    )


def downgrade() -> None:
    op.execute("DELETE FROM agent_tool_permissions WHERE tool_name IN ('read_file', 'list_dir', 'web_fetch');")
    op.drop_table("app_settings")
    op.drop_table("agent_run_state")
    op.drop_index("ix_tool_approvals_pending", table_name="tool_approvals")
    op.drop_table("tool_approvals")
    op.drop_table("agent_tool_permissions")
    op.drop_column("agents", "agentic_mode")
