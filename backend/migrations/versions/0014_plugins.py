"""Add plugin marketplaces and installed plugins.

Revision ID: 0014_plugins
Revises: 0013_connectors
"""

import sqlalchemy as sa
from alembic import op

revision: str = "0014_plugins"
down_revision: str | None = "0013_connectors"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "plugin_marketplaces",
        sa.Column("name", sa.String(length=100), primary_key=True),
        sa.Column("url", sa.Text(), nullable=False, unique=True),
        sa.Column("added_at", sa.DateTime(timezone=True), server_default=sa.text("CURRENT_TIMESTAMP"), nullable=False),
    )
    op.create_table(
        "plugins",
        sa.Column("slug", sa.String(length=80), primary_key=True),
        sa.Column("name", sa.String(length=150), nullable=False),
        sa.Column("version", sa.String(length=30), nullable=False, server_default="1.0.0"),
        sa.Column("description", sa.Text(), nullable=False, server_default=""),
        sa.Column("source", sa.String(length=20), nullable=False, server_default="local"),
        sa.Column("marketplace_name", sa.String(length=100), sa.ForeignKey("plugin_marketplaces.name", ondelete="SET NULL"), nullable=True),
        sa.Column("manifest", sa.JSON(), nullable=False),
        sa.Column("installed_refs", sa.JSON(), nullable=False),
        sa.Column("installed_at", sa.DateTime(timezone=True), server_default=sa.text("CURRENT_TIMESTAMP"), nullable=False),
    )


def downgrade() -> None:
    op.drop_table("plugins")
    op.drop_table("plugin_marketplaces")
