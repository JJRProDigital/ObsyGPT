"""Add sub-agent dispatch support: parent run linkage and dispatch registry.

Revision ID: 0015_subagents
Revises: 0014_plugins
"""

import sqlalchemy as sa
from alembic import op

revision: str = "0015_subagents"
down_revision: str | None = "0014_plugins"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("agent_runs", sa.Column("parent_run_id", sa.Integer(), sa.ForeignKey("agent_runs.id", ondelete="CASCADE"), nullable=True))
    op.create_index("ix_agent_runs_parent", "agent_runs", ["parent_run_id"])
    op.create_table(
        "subagent_dispatches",
        sa.Column("id", sa.Integer(), sa.Identity(), primary_key=True),
        sa.Column("parent_run_id", sa.Integer(), sa.ForeignKey("agent_runs.id", ondelete="CASCADE"), nullable=False),
        sa.Column("child_run_id", sa.Integer(), sa.ForeignKey("agent_runs.id", ondelete="CASCADE"), nullable=False, unique=True),
        sa.Column("agent_name", sa.String(length=100), nullable=False),
        sa.Column("goal", sa.Text(), nullable=False),
        sa.Column("status", sa.String(length=20), nullable=False, server_default="pending"),
        sa.Column("result", sa.Text(), nullable=False, server_default=""),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("CURRENT_TIMESTAMP"), nullable=False),
    )
    op.create_index("ix_subagent_dispatches_parent", "subagent_dispatches", ["parent_run_id"])


def downgrade() -> None:
    op.drop_index("ix_subagent_dispatches_parent", table_name="subagent_dispatches")
    op.drop_table("subagent_dispatches")
    op.drop_index("ix_agent_runs_parent", table_name="agent_runs")
    op.drop_column("agent_runs", "parent_run_id")
