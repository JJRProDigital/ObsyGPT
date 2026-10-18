"""Allow mcp_calls without an agent run for manual admin executions.

Revision ID: 0012_mcp_calls_nullable
Revises: 0011_habit_suggestions
"""

import sqlalchemy as sa
from alembic import op

revision: str = "0012_mcp_calls_nullable"
down_revision: str | None = "0011_habit_suggestions"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.alter_column("mcp_calls", "agent_run_id", existing_type=sa.Integer(), nullable=True)


def downgrade() -> None:
    op.execute("DELETE FROM mcp_calls WHERE agent_run_id IS NULL;")
    op.alter_column("mcp_calls", "agent_run_id", existing_type=sa.Integer(), nullable=False)
