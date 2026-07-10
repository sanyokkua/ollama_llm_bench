"""The connection pragma sets applied to every SQLite connection.

Source of truth: ``docs/v3_specification/10_Domain_and_Data/03_PERSISTENCE_SCHEMA.md``
§2 (Connection pragmas). ``journal_size_limit`` is applied to the single write
connection only — it governs how the writer truncates the shared ``-wal`` file, so
applying it to a read connection would be a no-op at best.
"""

import sqlite3
from typing import Final

__all__: list[str] = [
    "READ_CONNECTION_PRAGMAS",
    "WRITE_CONNECTION_PRAGMAS",
    "apply_pragmas",
]

_SHARED_PRAGMAS: Final[tuple[str, ...]] = (
    "PRAGMA journal_mode = WAL",
    "PRAGMA synchronous = NORMAL",
    "PRAGMA busy_timeout = 5000",
    "PRAGMA foreign_keys = ON",
    "PRAGMA temp_store = MEMORY",
    "PRAGMA wal_autocheckpoint = 1000",
)

WRITE_CONNECTION_PRAGMAS: Final[tuple[str, ...]] = (
    *_SHARED_PRAGMAS,
    "PRAGMA journal_size_limit = 67108864",
)
"""The pragma set applied to the single write connection (write-only tail pragma
included)."""

READ_CONNECTION_PRAGMAS: Final[tuple[str, ...]] = _SHARED_PRAGMAS
"""The pragma set applied to every read-only connection."""


def apply_pragmas(conn: sqlite3.Connection, *, pragmas: tuple[str, ...]) -> None:
    """Apply every pragma statement in ``pragmas`` to ``conn``, in order.

    Args:
        conn: The freshly opened connection to configure.
        pragmas: The ordered pragma statements to execute.
    """
    for pragma in pragmas:
        conn.execute(pragma)
