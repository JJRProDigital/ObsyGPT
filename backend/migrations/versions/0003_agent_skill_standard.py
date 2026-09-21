"""Add Agent Skills standard fields.

Revision ID: 0003_agent_skill_standard
Revises: 0002_audit_logs
Create Date: 2026-09-15
"""

from alembic import op
import sqlalchemy as sa


revision = "0003_agent_skill_standard"
down_revision = "0002_audit_logs"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("skills", sa.Column("argument_hint", sa.Text(), server_default="", nullable=False))
    op.add_column("skills", sa.Column("triggers", sa.ARRAY(sa.String(length=20)), server_default=sa.text("ARRAY['user']::varchar[]"), nullable=False))
    op.add_column(
        "skills",
        sa.Column(
            "body",
            sa.Text(),
            server_default="# Instrucciones principales\n1. Describe el flujo de trabajo de la skill.\n\n## Restricciones\n* No ejecutes acciones destructivas sin confirmacion explicita.",
            nullable=False,
        ),
    )
    op.add_column("skills", sa.Column("resources", sa.Text(), server_default="", nullable=False))


def downgrade() -> None:
    op.drop_column("skills", "resources")
    op.drop_column("skills", "body")
    op.drop_column("skills", "triggers")
    op.drop_column("skills", "argument_hint")
