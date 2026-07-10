"""The single-writer connection and read-only connection factory (DD-41).

Source of truth:
``docs/v3_specification/10_Domain_and_Data/03_PERSISTENCE_SCHEMA.md`` §2.1
(Connection topology).
"""

from pathlib import Path
import sqlite3
import threading

from ollama_llm_bench.backend.errors import PersistenceError
from ollama_llm_bench.backend.persistence.app_settings._internal.pragmas import (
    READ_CONNECTION_PRAGMAS,
    WRITE_CONNECTION_PRAGMAS,
    apply_pragmas,
)

__all__: list[str] = [
    "open_read_connection_impl",
    "open_write_connection_impl",
]


def open_write_connection_impl(db_path: Path) -> tuple[sqlite3.Connection, threading.Lock]:
    """Open the application's single write connection, guarded by one lock.

    ``isolation_level=None`` puts the connection in autocommit mode so
    ``conn.execute("BEGIN IMMEDIATE")`` genuinely opens an application-controlled
    immediate transaction. ``check_same_thread=False`` because the connection is
    opened once but called from both the GUI/compose thread and the dispatcher
    thread — thread-safety comes from the returned lock, not sqlite3's own
    thread-affinity check.

    Args:
        db_path: The resolved path to the database file.

    Returns:
        The opened connection and the lock every write must acquire around it.

    Raises:
        PersistenceError: ``db_path`` exists but is not a valid SQLite database
            (a corrupt or foreign file), so opening the connection or applying
            the pragmas failed.
    """
    try:
        conn = sqlite3.connect(str(db_path), isolation_level=None, check_same_thread=False)
        apply_pragmas(conn, pragmas=WRITE_CONNECTION_PRAGMAS)
    except sqlite3.Error as exc:
        message = f"failed to open the write connection to {db_path}"
        raise PersistenceError(message=message) from exc
    return conn, threading.Lock()


def open_read_connection_impl(db_path: Path) -> sqlite3.Connection:
    """Open a fresh read-only connection under WAL.

    A factory, not a shared singleton — every call opens a new connection so a
    reader's snapshot never entangles with another reader's or the writer's
    transaction lifetime.

    Args:
        db_path: The resolved path to the database file.

    Returns:
        A read-only connection with the read-connection pragma subset applied.

    Raises:
        PersistenceError: ``db_path`` exists but is not a valid SQLite database
            (a corrupt or foreign file), so opening the connection or applying
            the pragmas failed.
    """
    uri = f"file:{db_path}?mode=ro"
    try:
        conn = sqlite3.connect(uri, uri=True, check_same_thread=False)
        apply_pragmas(conn, pragmas=READ_CONNECTION_PRAGMAS)
    except sqlite3.Error as exc:
        message = f"failed to open the read connection to {db_path}"
        raise PersistenceError(message=message) from exc
    return conn
