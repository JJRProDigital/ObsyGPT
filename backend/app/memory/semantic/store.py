"""SQL persistence and search for semantic memory vectors."""

from ...db import connect  # noqa: I001


def _as_text(value) -> str:
    """Returns DB text values as str, decoding bytes if the driver returns them."""
    return value.decode("utf-8") if isinstance(value, bytes) else value


def vector_literal(vector: list[float]) -> str:
    """Formats a float vector as a pgvector string literal ('[0.1,0.2]')."""
    return "[" + ",".join(f"{float(value):.6f}" for value in vector) + "]"


def fetch_message_for_indexing(conversation_id: int, message_id: int) -> dict | None:
    with connect() as connection:
        with connection.cursor() as cursor:
            cursor.execute(
                """
                SELECT c.user_id, m.conversation_id, m.id, proj.project_id, m.role, m.content
                FROM messages m
                JOIN conversations c ON c.id = m.conversation_id
                LEFT JOIN LATERAL (
                    SELECT pc.project_id
                    FROM project_conversations pc
                    WHERE pc.conversation_id = c.id
                    ORDER BY pc.project_id
                    LIMIT 1
                ) proj ON true
                WHERE m.conversation_id = %s AND m.id = %s;
                """,
                (conversation_id, message_id),
            )
            row = cursor.fetchone()
    if not row:
        return None
    return {"user_id": row[0], "conversation_id": row[1], "message_id": row[2], "project_id": row[3], "role": row[4], "content": row[5]}


def get_memory_for_indexing(memory_id: int) -> dict | None:
    with connect() as connection:
        with connection.cursor() as cursor:
            cursor.execute("SELECT id, user_id, content FROM memories WHERE id = %s;", (memory_id,))
            row = cursor.fetchone()
    return {"id": row[0], "user_id": row[1], "content": row[2]} if row else None


def save_message_embeddings(
    user_id: int,
    conversation_id: int,
    message_id: int,
    project_id: int | None,
    chunks: list[str],
    vectors: list[list[float]],
    model: str,
) -> int:
    """Replaces any previous embeddings of this message for `model` and inserts the new chunks."""
    if len(chunks) != len(vectors):
        raise ValueError("chunks and vectors must have the same length")
    with connect() as connection:
        with connection.cursor() as cursor:
            cursor.execute(
                "DELETE FROM message_embeddings WHERE message_id = %s AND model = %s;",
                (message_id, model),
            )
            for chunk, vector in zip(chunks, vectors):
                cursor.execute(
                    """
                    INSERT INTO message_embeddings (user_id, conversation_id, message_id, project_id, chunk, embedding, model)
                    VALUES (%s, %s, %s, %s, %s, %s::vector, %s);
                    """,
                    (user_id, conversation_id, message_id, project_id, chunk, vector_literal(vector), model),
                )
            return len(chunks)


def save_memory_embedding(user_id: int, memory_id: int, vector: list[float], model: str) -> bool:
    with connect() as connection:
        with connection.cursor() as cursor:
            cursor.execute(
                "UPDATE memories SET embedding = %s::vector, model = %s WHERE id = %s AND user_id = %s;",
                (vector_literal(vector), model, memory_id, user_id),
            )
            return cursor.rowcount > 0


def purge_other_model_embeddings(model: str) -> int:
    """Deletes chunks embedded with any model other than `model`; returns the number of rows removed."""
    with connect() as connection:
        with connection.cursor() as cursor:
            cursor.execute("DELETE FROM message_embeddings WHERE model IS DISTINCT FROM %s;", (model,))
            return cursor.rowcount


def search_message_chunks(
    user_id: int,
    query_vector_literal: str,
    project_id: int | None,
    k: int,
    threshold: float,
    model: str | None = None,
    exclude_conversation_id: int | None = None,
) -> list[dict]:
    """Cosine search over message chunks. Strict project scoping: when `project_id` is set, only chunks of that project match.
    When `model` is set, only chunks of that model match (stale cross-model rows are excluded).
    When `exclude_conversation_id` is set, chunks of that conversation are skipped (its content is already in context)."""
    params: list = [query_vector_literal, user_id, query_vector_literal, threshold]
    filters = ""
    if project_id is not None:
        filters += " AND me.project_id = %s"
        params.append(project_id)
    if model is not None:
        filters += " AND me.model = %s"
        params.append(model)
    if exclude_conversation_id is not None:
        filters += " AND me.conversation_id <> %s"
        params.append(exclude_conversation_id)
    params.append(k)
    query = f"""
        SELECT me.chunk, 1 - (me.embedding <=> %s::vector) AS score,
               me.conversation_id, c.title, me.created_at
        FROM message_embeddings me
        JOIN conversations c ON c.id = me.conversation_id
        WHERE me.user_id = %s AND 1 - (me.embedding <=> %s::vector) >= %s{filters}
        ORDER BY score DESC
        LIMIT %s;
    """
    with connect() as connection:
        with connection.cursor() as cursor:
            cursor.execute(query, tuple(params))
            rows = cursor.fetchall()
    return [
        {"text": _as_text(row[0]), "score": float(row[1]), "conversation_id": row[2], "title": row[3] or "", "when": str(row[4])}
        for row in rows
    ]


def search_memory_vectors(user_id: int, query_vector_literal: str, k: int, threshold: float) -> list[dict]:
    with connect() as connection:
        with connection.cursor() as cursor:
            cursor.execute(
                """
                SELECT content, 1 - (embedding <=> %s::vector) AS score, updated_at
                FROM memories
                WHERE user_id = %s AND embedding IS NOT NULL
                  AND 1 - (embedding <=> %s::vector) >= %s
                ORDER BY score DESC
                LIMIT %s;
                """,
                (query_vector_literal, user_id, query_vector_literal, threshold, k),
            )
            rows = cursor.fetchall()
    return [{"text": _as_text(row[0]), "score": float(row[1]), "when": str(row[2])} for row in rows]


def count_missing_index(model: str) -> int:
    """Total pending units (memories + messages) not yet embedded with `model`."""
    with connect() as connection:
        with connection.cursor() as cursor:
            cursor.execute(
                """
                SELECT (
                    (SELECT COUNT(*) FROM memories WHERE embedding IS NULL OR model IS DISTINCT FROM %s)
                    + (SELECT COUNT(*) FROM messages m
                       JOIN conversations c ON c.id = m.conversation_id
                       WHERE m.role IN ('user', 'assistant')
                         AND NOT EXISTS (
                             SELECT 1 FROM message_embeddings me
                             WHERE me.message_id = m.id AND me.model = %s
                         ))
                );
                """,
                (model, model),
            )
            return int(cursor.fetchone()[0])


def list_missing_memories(model: str, exclude_memory_ids: list[int] | None = None) -> list[dict]:
    query = "SELECT id, user_id, content FROM memories WHERE embedding IS NULL OR model IS DISTINCT FROM %s"
    params: list = [model]
    if exclude_memory_ids:
        query += " AND id <> ALL(%s::bigint[])"
        params.append(exclude_memory_ids)
    query += " ORDER BY id;"
    with connect() as connection:
        with connection.cursor() as cursor:
            cursor.execute(query, tuple(params))
            rows = cursor.fetchall()
    return [{"id": row[0], "user_id": row[1], "content": row[2]} for row in rows]


def list_missing_messages(model: str, limit: int = 50, exclude_message_ids: list[int] | None = None) -> list[dict]:
    query = """
        SELECT c.user_id, m.conversation_id, m.id, proj.project_id, m.content
        FROM messages m
        JOIN conversations c ON c.id = m.conversation_id
        LEFT JOIN LATERAL (
            SELECT pc.project_id
            FROM project_conversations pc
            WHERE pc.conversation_id = c.id
            ORDER BY pc.project_id
            LIMIT 1
        ) proj ON true
        WHERE m.role IN ('user', 'assistant')
          AND NOT EXISTS (
              SELECT 1 FROM message_embeddings me
              WHERE me.message_id = m.id AND me.model = %s
          )"""
    params: list = [model]
    if exclude_message_ids:
        query += " AND m.id <> ALL(%s::bigint[])"
        params.append(exclude_message_ids)
    query += """
        ORDER BY m.id
        LIMIT %s;
        """
    params.append(limit)
    with connect() as connection:
        with connection.cursor() as cursor:
            cursor.execute(query, tuple(params))
            rows = cursor.fetchall()
    return [
        {"user_id": row[0], "conversation_id": row[1], "message_id": row[2], "project_id": row[3], "content": row[4]}
        for row in rows
    ]
