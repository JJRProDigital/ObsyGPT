import json

from ..db import connect


class AuditStore:
    def add_log(
        self,
        actor_user_id: int,
        action: str,
        target_type: str,
        target_id: int | None,
        metadata: dict | None = None,
    ) -> None:
        with connect() as connection:
            with connection.cursor() as cursor:
                cursor.execute(
                    """
                    INSERT INTO audit_logs (actor_user_id, action, target_type, target_id, metadata)
                    VALUES (%s, %s, %s, %s, %s);
                    """,
                    (actor_user_id, action, target_type, target_id, json.dumps(metadata or {})),
                )
