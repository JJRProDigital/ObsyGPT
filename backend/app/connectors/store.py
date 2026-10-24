"""Persistence for the connector catalog and user connected accounts."""

from ..db import connect
from .catalog import CONNECTOR_DEFINITIONS, get_connector_definition


class ConnectorStore:
    def list_catalog(self) -> list[dict]:
        with connect() as connection:
            with connection.cursor() as cursor:
                cursor.execute("SELECT slug, name, description, auth_type, token_label, enabled FROM connectors ORDER BY name;")
                columns = [column.name for column in cursor.description]
                return [dict(zip(columns, row)) for row in cursor.fetchall()]

    def ensure_catalog_rows(self) -> None:
        with connect() as connection:
            with connection.cursor() as cursor:
                for definition in CONNECTOR_DEFINITIONS.values():
                    cursor.execute(
                        """
                        INSERT INTO connectors (slug, name, description, auth_type, token_label, enabled)
                        VALUES (%s, %s, %s, %s, %s, true)
                        ON CONFLICT (slug) DO UPDATE SET name = EXCLUDED.name, description = EXCLUDED.description, auth_type = EXCLUDED.auth_type, token_label = EXCLUDED.token_label;
                        """,
                        (definition.slug, definition.name, definition.description, definition.auth_type, definition.token_label),
                    )

    def list_accounts(self, user_id: int) -> list[dict]:
        with connect() as connection:
            with connection.cursor() as cursor:
                cursor.execute(
                    """
                    SELECT ca.id, ca.connector_slug, ca.display_name, ca.status, ca.created_at
                    FROM connector_accounts ca
                    WHERE ca.user_id = %s
                    ORDER BY ca.created_at DESC;
                    """,
                    (user_id,),
                )
                columns = [column.name for column in cursor.description]
                return [dict(zip(columns, row)) for row in cursor.fetchall()]

    def create_account(self, user_id: int, connector_slug: str, credentials_encrypted: str, display_name: str) -> dict:
        get_connector_definition(connector_slug)
        with connect() as connection:
            with connection.cursor() as cursor:
                cursor.execute(
                    """
                    INSERT INTO connector_accounts (user_id, connector_slug, credentials_encrypted, display_name, status)
                    VALUES (%s, %s, %s, %s, 'connected')
                    ON CONFLICT (user_id, connector_slug) DO UPDATE SET credentials_encrypted = EXCLUDED.credentials_encrypted, display_name = EXCLUDED.display_name, status = 'connected'
                    RETURNING id, connector_slug, display_name, status;
                    """,
                    (user_id, connector_slug, credentials_encrypted, display_name),
                )
                columns = [column.name for column in cursor.description]
                return dict(zip(columns, cursor.fetchone()))

    def delete_account(self, account_id: int, user_id: int) -> bool:
        with connect() as connection:
            with connection.cursor() as cursor:
                cursor.execute(
                    "DELETE FROM connector_accounts WHERE id = %s AND user_id = %s;",
                    (account_id, user_id),
                )
                return cursor.rowcount > 0

    def get_credential(self, user_id: int, connector_slug: str) -> str | None:
        with connect() as connection:
            with connection.cursor() as cursor:
                cursor.execute(
                    "SELECT credentials_encrypted FROM connector_accounts WHERE user_id = %s AND connector_slug = %s AND status = 'connected';",
                    (user_id, connector_slug),
                )
                row = cursor.fetchone()
                return row[0] if row else None

    def connected_slugs(self, user_id: int) -> list[str]:
        with connect() as connection:
            with connection.cursor() as cursor:
                cursor.execute(
                    "SELECT connector_slug FROM connector_accounts WHERE user_id = %s AND status = 'connected';",
                    (user_id,),
                )
                return [row[0] for row in cursor.fetchall()]

    def update_credentials(self, user_id: int, connector_slug: str, credentials_encrypted: str) -> None:
        with connect() as connection:
            with connection.cursor() as cursor:
                cursor.execute(
                    "UPDATE connector_accounts SET credentials_encrypted = %s WHERE user_id = %s AND connector_slug = %s;",
                    (credentials_encrypted, user_id, connector_slug),
                )

    def create_oauth_state(self, user_id: int, connector_slug: str, state: str, code_verifier: str, redirect_uri: str, client_id: str) -> None:
        with connect() as connection:
            with connection.cursor() as cursor:
                cursor.execute("DELETE FROM connector_oauth_states WHERE created_at < NOW() - INTERVAL '15 minutes';")
                cursor.execute(
                    """
                    INSERT INTO connector_oauth_states (user_id, connector_slug, state, code_verifier, redirect_uri, client_id)
                    VALUES (%s, %s, %s, %s, %s, %s);
                    """,
                    (user_id, connector_slug, state, code_verifier, redirect_uri, client_id),
                )

    def consume_oauth_state(self, user_id: int, connector_slug: str, state: str) -> dict | None:
        with connect() as connection:
            with connection.cursor() as cursor:
                cursor.execute(
                    """
                    DELETE FROM connector_oauth_states
                    WHERE user_id = %s AND connector_slug = %s AND state = %s AND created_at >= NOW() - INTERVAL '15 minutes'
                    RETURNING code_verifier, redirect_uri, client_id;
                    """,
                    (user_id, connector_slug, state),
                )
                row = cursor.fetchone()
                if not row:
                    return None
                return {"code_verifier": row[0], "redirect_uri": row[1], "client_id": row[2]}
