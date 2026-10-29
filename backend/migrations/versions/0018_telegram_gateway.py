"""Telegram gateway: per-agent bot config and message log.

Revision ID: 0018_telegram_gateway
Revises: 0017_chat_folders
"""

import sqlalchemy as sa
from alembic import op

revision: str = "0018_telegram_gateway"
down_revision: str | None = "0017_chat_folders"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("agents", sa.Column("telegram_enabled", sa.Boolean(), server_default=sa.text("false"), nullable=False))
    op.add_column("agents", sa.Column("telegram_bot_token", sa.Text(), nullable=True))
    op.add_column("agents", sa.Column("telegram_allowlist", sa.Text(), server_default="", nullable=False))
    op.create_table(
        "telegram_messages",
        sa.Column("id", sa.Integer(), sa.Identity(), primary_key=True),
        sa.Column("agent_id", sa.Integer(), sa.ForeignKey("agents.id", ondelete="CASCADE"), nullable=False),
        sa.Column("chat_id", sa.BigInteger(), nullable=False),
        sa.Column("message_id", sa.BigInteger(), nullable=True),
        sa.Column("direction", sa.String(length=10), nullable=False),
        sa.Column("sender_tg_id", sa.BigInteger(), nullable=True),
        sa.Column("content", sa.Text(), server_default="", nullable=False),
        sa.Column("task_id", sa.Integer(), sa.ForeignKey("tasks.id", ondelete="SET NULL"), nullable=True),
        sa.Column("delivered", sa.Boolean(), server_default=sa.text("true"), nullable=False),
        sa.Column("notified_status", sa.String(length=20), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("CURRENT_TIMESTAMP"), nullable=False),
    )
    op.create_index(
        "uq_telegram_inbound",
        "telegram_messages",
        ["agent_id", "chat_id", "message_id"],
        unique=True,
        postgresql_where=sa.text("direction = 'inbound' AND message_id IS NOT NULL"),
    )


def downgrade() -> None:
    op.drop_index("uq_telegram_inbound", table_name="telegram_messages")
    op.drop_table("telegram_messages")
    op.drop_column("agents", "telegram_allowlist")
    op.drop_column("agents", "telegram_bot_token")
    op.drop_column("agents", "telegram_enabled")
