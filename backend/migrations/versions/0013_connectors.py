"""Add connectors catalog and user connector accounts.

Revision ID: 0013_connectors
Revises: 0012_mcp_calls_nullable
"""

import sqlalchemy as sa
from alembic import op

revision: str = "0013_connectors"
down_revision: str | None = "0012_mcp_calls_nullable"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "connectors",
        sa.Column("slug", sa.String(length=50), primary_key=True),
        sa.Column("name", sa.String(length=100), nullable=False),
        sa.Column("description", sa.Text(), nullable=False, server_default=""),
        sa.Column("auth_type", sa.String(length=20), nullable=False, server_default="token"),
        sa.Column("token_label", sa.String(length=200), nullable=False, server_default=""),
        sa.Column("enabled", sa.Boolean(), nullable=False, server_default=sa.text("true")),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("CURRENT_TIMESTAMP"), nullable=False),
    )
    op.create_table(
        "connector_accounts",
        sa.Column("id", sa.Integer(), sa.Identity(), primary_key=True),
        sa.Column("user_id", sa.Integer(), sa.ForeignKey("users.id", ondelete="CASCADE"), nullable=False),
        sa.Column("connector_slug", sa.String(length=50), sa.ForeignKey("connectors.slug", ondelete="CASCADE"), nullable=False),
        sa.Column("credentials_encrypted", sa.Text(), nullable=False),
        sa.Column("display_name", sa.Text(), nullable=False, server_default=""),
        sa.Column("status", sa.String(length=20), nullable=False, server_default="connected"),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("CURRENT_TIMESTAMP"), nullable=False),
        sa.UniqueConstraint("user_id", "connector_slug", name="uq_connector_accounts_user_slug"),
    )
    op.execute(
        """
        INSERT INTO connectors (slug, name, description, auth_type, token_label, enabled) VALUES
        ('github', 'GitHub', 'Buscar repos, leer archivos e issues, y crear issues en nombre del usuario.', 'token', 'Personal access token (PAT)', true),
        ('gdrive', 'Google Drive', 'Buscar archivos y leer documentos de Google Drive del usuario (solo lectura).', 'token', 'OAuth access token', true);
        """
    )


def downgrade() -> None:
    op.drop_table("connector_accounts")
    op.drop_table("connectors")
