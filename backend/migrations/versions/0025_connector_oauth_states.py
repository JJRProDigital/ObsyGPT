"""Add Higgsfield connector and OAuth state table.

Revision ID: 0025_connector_oauth_states
Revises: 0024_provider_api_keys
"""

import sqlalchemy as sa
from alembic import op

revision: str = "0025_connector_oauth_states"
down_revision: str | None = "0024_provider_api_keys"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "connector_oauth_states",
        sa.Column("id", sa.Integer(), sa.Identity(), primary_key=True),
        sa.Column("user_id", sa.Integer(), sa.ForeignKey("users.id", ondelete="CASCADE"), nullable=False),
        sa.Column("connector_slug", sa.String(length=50), sa.ForeignKey("connectors.slug", ondelete="CASCADE"), nullable=False),
        sa.Column("state", sa.String(length=128), nullable=False, unique=True),
        sa.Column("code_verifier", sa.String(length=256), nullable=False),
        sa.Column("redirect_uri", sa.Text(), nullable=False),
        sa.Column("client_id", sa.Text(), nullable=False, server_default=""),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("CURRENT_TIMESTAMP"), nullable=False),
    )
    op.execute(
        """
        INSERT INTO connectors (slug, name, description, auth_type, token_label, enabled) VALUES
        ('higgsfield', 'Higgsfield', 'Genera imagenes y videos con los modelos de Higgsfield a traves de su servidor MCP.', 'oauth', '', true)
        ON CONFLICT (slug) DO UPDATE SET name = EXCLUDED.name, description = EXCLUDED.description, auth_type = EXCLUDED.auth_type, token_label = EXCLUDED.token_label;
        """
    )


def downgrade() -> None:
    op.drop_table("connector_oauth_states")
    op.execute("DELETE FROM connectors WHERE slug = 'higgsfield';")
