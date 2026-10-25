"""Semantic memory: pgvector extension, message_embeddings, memory vectors

Revision ID: 0022_semantic_memory
Revises: 0021_task_context_note
Create Date: 2026-10-06
"""

from collections.abc import Sequence

from alembic import op


revision: str = "0022_semantic_memory"
down_revision: str | None = "0021_task_context_note"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.execute("CREATE EXTENSION IF NOT EXISTS vector;")
    op.execute(
        """
        CREATE TABLE message_embeddings (
            id BIGSERIAL PRIMARY KEY,
            user_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
            conversation_id INTEGER NOT NULL REFERENCES conversations(id) ON DELETE CASCADE,
            message_id INTEGER NOT NULL REFERENCES messages(id) ON DELETE CASCADE,
            project_id INTEGER REFERENCES projects(id) ON DELETE SET NULL,
            chunk TEXT NOT NULL,
            embedding vector(384) NOT NULL,
            model TEXT NOT NULL,
            created_at TIMESTAMPTZ NOT NULL DEFAULT now()
        );
        """
    )
    op.execute(
        "CREATE INDEX idx_message_embeddings_hnsw ON message_embeddings USING hnsw (embedding vector_cosine_ops);"
    )
    op.execute("CREATE INDEX idx_message_embeddings_user ON message_embeddings (user_id);")
    op.execute("CREATE INDEX idx_message_embeddings_message ON message_embeddings (message_id);")
    op.execute("CREATE INDEX idx_message_embeddings_conversation ON message_embeddings (conversation_id);")
    op.execute("ALTER TABLE memories ADD COLUMN embedding vector(384);")
    op.execute("ALTER TABLE memories ADD COLUMN model TEXT;")


def downgrade() -> None:
    op.execute("ALTER TABLE memories DROP COLUMN IF EXISTS model;")
    op.execute("ALTER TABLE memories DROP COLUMN IF EXISTS embedding;")
    op.execute("DROP INDEX IF EXISTS idx_message_embeddings_conversation;")
    op.execute("DROP INDEX IF EXISTS idx_message_embeddings_message;")
    op.execute("DROP TABLE IF EXISTS message_embeddings;")
