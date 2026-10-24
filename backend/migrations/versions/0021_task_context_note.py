"""Telegram context travels in tasks.context_note instead of polluting the goal.

Revision ID: 0021_task_context_note
Revises: 0020_telegram_voice
"""

import sqlalchemy as sa
from alembic import op

revision: str = "0021_task_context_note"
down_revision: str | None = "0020_telegram_voice"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("tasks", sa.Column("context_note", sa.Text(), nullable=True))


def downgrade() -> None:
    op.drop_column("tasks", "context_note")
