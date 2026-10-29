"""Add Higgsfield API connector (Open Higgsfield REST, token auth).

Revision ID: 0026_higgsfield_api_connector
Revises: 0025_connector_oauth_states
"""

from alembic import op

revision: str = "0026_higgsfield_api_connector"
down_revision: str | None = "0025_connector_oauth_states"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute(
        """
        INSERT INTO connectors (slug, name, description, auth_type, token_label, enabled) VALUES
        ('higgsfield_api', 'Higgsfield API', 'Genera imagenes y videos con la API REST de Open Higgsfield (billing en dolares: Kling, Seedance, Wan, Soul).', 'token', 'Credencial API (key_id:key_secret)', true)
        ON CONFLICT (slug) DO UPDATE SET name = EXCLUDED.name, description = EXCLUDED.description, auth_type = EXCLUDED.auth_type, token_label = EXCLUDED.token_label;
        """
    )


def downgrade() -> None:
    op.execute("DELETE FROM connectors WHERE slug = 'higgsfield_api';")
