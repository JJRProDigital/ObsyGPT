"""Database access: pooled connections shared across the app."""

import logging
import threading
from collections.abc import Generator
from contextlib import contextmanager

from psycopg import Connection, adapters
from psycopg.types.string import StrBinaryDumper, StrDumper
from psycopg_pool import ConnectionPool

from .config import get_settings

logger = logging.getLogger("obsygpt.db")

_warned_nul_stripped = False


class _SanitizedStrDumper(StrDumper):
    """Strips NUL bytes before dumping text: PostgreSQL rejects 0x00 in text fields,
    and web-scraped content (HTML/RSS) can legitimately contain them."""

    def dump(self, obj):  # noqa: ANN001, ANN201
        global _warned_nul_stripped
        if "\x00" in obj:
            if not _warned_nul_stripped:
                _warned_nul_stripped = True
                logger.warning("Stripped NUL byte(s) from a text parameter (web content often carries them).")
            obj = obj.replace("\x00", "")
        return obj.encode("utf-8")


class _SanitizedStrBinaryDumper(StrBinaryDumper):
    def dump(self, obj):  # noqa: ANN001, ANN201
        global _warned_nul_stripped
        if "\x00" in obj:
            if not _warned_nul_stripped:
                _warned_nul_stripped = True
                logger.warning("Stripped NUL byte(s) from a text parameter (web content often carries them).")
            obj = obj.replace("\x00", "")
        return obj.encode("utf-8")


# Registered on the global adapters map so every pooled connection created
# after this import inherits the sanitized str dumpers.
adapters.register_dumper(str, _SanitizedStrDumper)
adapters.register_dumper(str, _SanitizedStrBinaryDumper)

_pool: ConnectionPool | None = None
_pool_lock = threading.Lock()


def _get_pool() -> ConnectionPool:
    global _pool
    with _pool_lock:
        if _pool is None or _pool.closed:
            _pool = ConnectionPool(
                get_settings().database_url,
                min_size=0,
                max_size=10,
                timeout=15,
                name="obsygpt-pool",
                open=True,
            )
            logger.info("Connection pool opened (max_size=10)")
        return _pool


@contextmanager
def connect() -> Generator[Connection, None, None]:
    """Checks a connection out of the shared pool; commits on success, rolls back on error."""
    pool = _get_pool()
    with pool.connection() as connection:
        yield connection


def close_pool() -> None:
    global _pool
    with _pool_lock:
        if _pool is not None and not _pool.closed:
            _pool.close()
            logger.info("Connection pool closed")
        _pool = None
