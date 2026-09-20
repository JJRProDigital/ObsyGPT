"""Cowork-style projects: folder context, archive, project tasks and memory

Revision ID: 0010_cowork_projects
Revises: 0009_projects
Create Date: 2026-09-16
"""

from collections.abc import Sequence

from alembic import op
import sqlalchemy as sa


revision: str = "0010_cowork_projects"
down_revision: str | None = "0009_projects"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column("projects", sa.Column("folder_path", sa.Text(), nullable=True))
    op.add_column("projects", sa.Column("archived", sa.Boolean(), server_default=sa.text("false"), nullable=False))

    op.add_column("tasks", sa.Column("project_id", sa.Integer(), sa.ForeignKey("projects.id", ondelete="SET NULL"), nullable=True))
    op.add_column("tasks", sa.Column("recurrence", sa.String(length=20), nullable=True))
    op.add_column("tasks", sa.Column("last_occurrence_at", sa.DateTime(timezone=True), nullable=True))
    op.create_index("ix_tasks_project", "tasks", ["project_id"])

    op.add_column("memories", sa.Column("project_id", sa.Integer(), sa.ForeignKey("projects.id", ondelete="CASCADE"), nullable=True))
    op.create_index("ix_memories_project", "memories", ["project_id"])


def downgrade() -> None:
    op.drop_index("ix_memories_project", table_name="memories")
    op.drop_column("memories", "project_id")
    op.drop_index("ix_tasks_project", table_name="tasks")
    op.drop_column("tasks", "last_occurrence_at")
    op.drop_column("tasks", "recurrence")
    op.drop_column("tasks", "project_id")
    op.drop_column("projects", "archived")
    op.drop_column("projects", "folder_path")
