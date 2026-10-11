"""Shared query helpers for the admin API modules.

Domain modules call these through the module (``queries.fetch_one(...)``) so
tests can monkeypatch ``app.admin.queries.*`` once for every consumer.
"""

from .. import db as app_db


def fetch_all(query: str, params: tuple = ()):  # noqa: ANN201
    with app_db.connect() as connection:
        with connection.cursor() as cursor:
            cursor.execute(query, params)
            columns = [column.name for column in cursor.description]
            return [dict(zip(columns, row)) for row in cursor.fetchall()]


def fetch_one(query: str, params: tuple):  # noqa: ANN201
    with app_db.connect() as connection:
        with connection.cursor() as cursor:
            cursor.execute(query, params)
            columns = [column.name for column in cursor.description]
            row = cursor.fetchone()
            return dict(zip(columns, row)) if row else None


def execute_returning(query: str, params: tuple):  # noqa: ANN201
    with app_db.connect() as connection:
        with connection.cursor() as cursor:
            cursor.execute(query, params)
            columns = [column.name for column in cursor.description]
            row = cursor.fetchone()
            return dict(zip(columns, row)) if row else None


def ensure_positive_id(value: int, label: str) -> int:
    if value <= 0:
        raise ValueError(f"{label} must be a positive integer")
    return value
