"""Add habit_suggestions for user-approved habit learning.

Revision ID: 0011_habit_suggestions
Revises: 0010_cowork_projects
"""

import sqlalchemy as sa
from alembic import op

revision: str = "0011_habit_suggestions"
down_revision: str | None = "0010_cowork_projects"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "habit_suggestions",
        sa.Column("id", sa.Integer(), sa.Identity(), primary_key=True),
        sa.Column("user_id", sa.Integer(), sa.ForeignKey("users.id", ondelete="CASCADE"), nullable=False),
        sa.Column("content", sa.Text(), nullable=False),
        sa.Column("evidence", sa.Text(), nullable=False, server_default=""),
        sa.Column("source", sa.String(length=20), nullable=False, server_default="model"),
        sa.Column("status", sa.String(length=20), nullable=False, server_default="pending"),
        sa.Column("conversation_id", sa.Integer(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("CURRENT_TIMESTAMP"), nullable=False),
        sa.Column("decided_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.create_index("ix_habit_suggestions_user_status", "habit_suggestions", ["user_id", "status"])


def downgrade() -> None:
    op.drop_index("ix_habit_suggestions_user_status", table_name="habit_suggestions")
    op.drop_table("habit_suggestions")
