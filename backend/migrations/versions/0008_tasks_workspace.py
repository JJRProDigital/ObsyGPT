"""Add background tasks, task events, user settings, task approvals

Revision ID: 0008_tasks_workspace
Revises: 0007_agent_fallbacks
Create Date: 2026-09-16
"""

from collections.abc import Sequence

from alembic import op
import sqlalchemy as sa


revision: str = "0008_tasks_workspace"
down_revision: str | None = "0007_agent_fallbacks"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "tasks",
        sa.Column("id", sa.Integer(), sa.Identity(), primary_key=True),
        sa.Column("user_id", sa.Integer(), sa.ForeignKey("users.id", ondelete="CASCADE"), nullable=False),
        sa.Column("goal", sa.Text(), nullable=False),
        sa.Column("mode", sa.String(length=10), server_default=sa.text("'act'"), nullable=False),
        sa.Column("status", sa.String(length=30), server_default=sa.text("'pending'"), nullable=False),
        sa.Column("scheduled_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("attempts", sa.Integer(), server_default=sa.text("0"), nullable=False),
        sa.Column("next_attempt_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("agent_id", sa.Integer(), sa.ForeignKey("agents.id", ondelete="SET NULL"), nullable=True),
        sa.Column("result", sa.Text(), server_default="", nullable=False),
        sa.Column("error", sa.Text(), server_default="", nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("CURRENT_TIMESTAMP"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("CURRENT_TIMESTAMP"), nullable=False),
    )
    op.create_index("ix_tasks_user_status", "tasks", ["user_id", "status"])

    op.create_table(
        "task_events",
        sa.Column("id", sa.Integer(), sa.Identity(), primary_key=True),
        sa.Column("task_id", sa.Integer(), sa.ForeignKey("tasks.id", ondelete="CASCADE"), nullable=False),
        sa.Column("event_type", sa.String(length=50), nullable=False),
        sa.Column("title", sa.String(length=200), nullable=False),
        sa.Column("content", sa.Text(), server_default="", nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("CURRENT_TIMESTAMP"), nullable=False),
    )
    op.create_index("ix_task_events_task", "task_events", ["task_id"])

    op.create_table(
        "user_settings",
        sa.Column("user_id", sa.Integer(), sa.ForeignKey("users.id", ondelete="CASCADE"), primary_key=True),
        sa.Column("key", sa.String(length=100), primary_key=True),
        sa.Column("value", sa.JSON(), server_default=sa.text("'{}'::json"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("CURRENT_TIMESTAMP"), nullable=False),
    )

    op.alter_column("agent_runs", "conversation_id", existing_type=sa.Integer(), nullable=True)
    op.alter_column("tool_approvals", "conversation_id", existing_type=sa.Integer(), nullable=True)
    op.add_column("tool_approvals", sa.Column("task_id", sa.Integer(), sa.ForeignKey("tasks.id", ondelete="CASCADE"), nullable=True))

    op.execute(
        """
        INSERT INTO app_settings (key, value)
        VALUES ('tasks', '{"max_concurrent_tasks": 1, "auto_resume_tasks": true}'::json)
        ON CONFLICT (key) DO NOTHING;
        """
    )


def downgrade() -> None:
    op.execute("DELETE FROM app_settings WHERE key = 'tasks';")
    op.drop_column("tool_approvals", "task_id")
    op.alter_column("tool_approvals", "conversation_id", existing_type=sa.Integer(), nullable=False)
    op.alter_column("agent_runs", "conversation_id", existing_type=sa.Integer(), nullable=False)
    op.drop_table("user_settings")
    op.drop_index("ix_task_events_task", table_name="task_events")
    op.drop_table("task_events")
    op.drop_index("ix_tasks_user_status", table_name="tasks")
    op.drop_table("tasks")
