"""Telegram voice messages: flag inbound rows originated from voice notes.

Revision ID: 0020_telegram_voice
Revises: 0019_event_triggers
"""

import sqlalchemy as sa
from alembic import op

revision: str = "0020_telegram_voice"
down_revision: str | None = "0019_event_triggers"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("telegram_messages", sa.Column("via_voice", sa.Boolean(), server_default=sa.text("false"), nullable=False))


def downgrade() -> None:
    op.drop_column("telegram_messages", "via_voice")
