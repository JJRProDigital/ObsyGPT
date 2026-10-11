"""Add chat folders for conversation organization.

Revision ID: 0017_chat_folders
Revises: 0016_agent_runs_awaiting
"""

import sqlalchemy as sa
from alembic import op

revision: str = "0017_chat_folders"
down_revision: str | None = "0016_agent_runs_awaiting"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "chat_folders",
        sa.Column("id", sa.Integer(), sa.Identity(), primary_key=True),
        sa.Column("user_id", sa.Integer(), sa.ForeignKey("users.id", ondelete="CASCADE"), nullable=False),
        sa.Column("name", sa.String(length=100), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("CURRENT_TIMESTAMP"), nullable=False),
    )
    op.add_column("conversations", sa.Column("folder_id", sa.Integer(), sa.ForeignKey("chat_folders.id", ondelete="SET NULL"), nullable=True))
    op.create_index("ix_conversations_user_folder", "conversations", ["user_id", "folder_id"])


def downgrade() -> None:
    op.drop_index("ix_conversations_user_folder", table_name="conversations")
    op.drop_column("conversations", "folder_id")
    op.drop_table("chat_folders")
