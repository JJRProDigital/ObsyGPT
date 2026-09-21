from collections.abc import Generator

import psycopg
from psycopg import Connection

from .config import get_settings


def connect() -> Connection:
    return psycopg.connect(get_settings().database_url)


def cursor() -> Generator[psycopg.Cursor, None, None]:
    with connect() as connection:
        with connection.cursor() as db_cursor:
            yield db_cursor
