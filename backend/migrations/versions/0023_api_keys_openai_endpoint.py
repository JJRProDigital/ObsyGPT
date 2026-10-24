"""API keys for the OpenAI-compatible endpoint and stateless run tracing

Revision ID: 0023_api_keys
Revises: 0022_semantic_memory
Create Date: 2026-10-07

agent_runs.conversation_id has been nullable since 0008_tasks_workspace and
agent_runs.message_id since 0001, so the DROP NOT NULL statements below are
idempotent no-ops kept for spec fidelity. The downgrade therefore does not
re-add NOT NULL: that would revert a state this migration never created.
"""

from collections.abc import Sequence

from alembic import op


revision: str = "0023_api_keys"
down_revision: str | None = "0022_semantic_memory"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.execute(
        """
        CREATE TABLE api_keys (
            id BIGSERIAL PRIMARY KEY,
            user_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
            key_hash TEXT NOT NULL UNIQUE,
            prefix TEXT NOT NULL,
            name TEXT NOT NULL,
            created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
            last_used_at TIMESTAMPTZ,
            revoked_at TIMESTAMPTZ
        );
        """
    )
    op.execute("CREATE INDEX idx_api_keys_user ON api_keys (user_id);")
    op.execute("ALTER TABLE agent_runs ALTER COLUMN conversation_id DROP NOT NULL;")
    op.execute("ALTER TABLE agent_runs ALTER COLUMN message_id DROP NOT NULL;")


def downgrade() -> None:
    op.execute("DROP INDEX IF EXISTS idx_api_keys_user;")
    op.execute("DROP TABLE IF EXISTS api_keys;")
