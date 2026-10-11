"""Allow awaiting_approval status on agent_runs.

Revision ID: 0016_agent_runs_awaiting
Revises: 0015_subagents
"""

from alembic import op

revision: str = "0016_agent_runs_awaiting"
down_revision: str | None = "0015_subagents"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("ALTER TABLE agent_runs DROP CONSTRAINT agent_runs_status_check;")
    op.execute(
        "ALTER TABLE agent_runs ADD CONSTRAINT agent_runs_status_check "
        "CHECK (status IN ('running', 'completed', 'failed', 'awaiting_approval'));"
    )


def downgrade() -> None:
    op.execute("UPDATE agent_runs SET status = 'failed' WHERE status = 'awaiting_approval';")
    op.execute("ALTER TABLE agent_runs DROP CONSTRAINT agent_runs_status_check;")
    op.execute(
        "ALTER TABLE agent_runs ADD CONSTRAINT agent_runs_status_check "
        "CHECK (status IN ('running', 'completed', 'failed'));"
    )
