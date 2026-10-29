"""Event triggers: proactive agent wake-ups (interval, change detection, webhook).

Revision ID: 0019_event_triggers
Revises: 0018_telegram_gateway
"""

import sqlalchemy as sa
from alembic import op

revision: str = "0019_event_triggers"
down_revision: str | None = "0018_telegram_gateway"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("tasks", sa.Column("readonly", sa.Boolean(), server_default=sa.text("false"), nullable=False))
    op.create_table(
        "event_triggers",
        sa.Column("id", sa.Integer(), sa.Identity(), primary_key=True),
        sa.Column("user_id", sa.Integer(), sa.ForeignKey("users.id", ondelete="CASCADE"), nullable=False),
        sa.Column("agent_id", sa.Integer(), sa.ForeignKey("agents.id", ondelete="CASCADE"), nullable=False),
        sa.Column("name", sa.String(length=120), nullable=False),
        sa.Column("trigger_type", sa.String(length=30), nullable=False),
        sa.Column("config", sa.Text(), server_default="{}", nullable=False),
        sa.Column("goal_template", sa.Text(), nullable=False),
        sa.Column("notify_channel", sa.String(length=20), server_default="", nullable=False),
        sa.Column("notify_chat_id", sa.BigInteger(), nullable=True),
        sa.Column("cooldown_seconds", sa.Integer(), server_default="0", nullable=False),
        sa.Column("readonly", sa.Boolean(), server_default=sa.text("true"), nullable=False),
        sa.Column("enabled", sa.Boolean(), server_default=sa.text("true"), nullable=False),
        sa.Column("webhook_secret", sa.String(length=64), nullable=True),
        sa.Column("last_fired_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("last_snapshot", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("CURRENT_TIMESTAMP"), nullable=False),
    )
    op.create_index("ix_event_triggers_user", "event_triggers", ["user_id"])
    op.create_index("ix_event_triggers_enabled", "event_triggers", ["enabled"])


def downgrade() -> None:
    op.drop_index("ix_event_triggers_enabled", table_name="event_triggers")
    op.drop_index("ix_event_triggers_user", table_name="event_triggers")
    op.drop_table("event_triggers")
    op.drop_column("tasks", "readonly")
