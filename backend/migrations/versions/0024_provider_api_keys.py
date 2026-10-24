"""Encrypted provider API keys stored in the panel (Fernet), with env var fallback

Revision ID: 0024_provider_api_keys
Revises: 0023_api_keys
Create Date: 2026-10-11

providers.api_key_encrypted holds a Fernet token produced with the same key
scheme as connector credentials (CONNECTOR_ENCRYPTION_KEY or SESSION_SECRET
derivative). The plaintext key is never stored, returned or logged.
"""

from collections.abc import Sequence

from alembic import op


revision: str = "0024_provider_api_keys"
down_revision: str | None = "0023_api_keys"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.execute("ALTER TABLE providers ADD COLUMN IF NOT EXISTS api_key_encrypted TEXT;")


def downgrade() -> None:
    op.execute("ALTER TABLE providers DROP COLUMN IF EXISTS api_key_encrypted;")
