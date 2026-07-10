"""Public surface for ``backend/persistence/app_settings/``.

Per ADR-0004 this module houses the shared single-writer connection manager and the
schema lifecycle (first-run DDL, version check, additive evolution) alongside the
``AppSettingsStore`` factory — the composition root constructs the connection once
here and injects it into the five sibling persistence stores.

Source of truth: ADR-0004;
``docs/v3_specification/10_Domain_and_Data/03_PERSISTENCE_SCHEMA.md`` §2, §8;
``docs/v3_specification/08_Cross_Cutting/08-E_interfaces_contracts.md`` §7.6.
"""

from collections.abc import Callable
from pathlib import Path
import sqlite3
import threading

import icontract

from ollama_llm_bench.backend.infra import Clock
from ollama_llm_bench.backend.persistence.app_settings._internal.connection import (
    open_read_connection_impl,
    open_write_connection_impl,
)
from ollama_llm_bench.backend.persistence.app_settings._internal.schema_ddl import (
    run_first_run_ddl,
)
from ollama_llm_bench.backend.persistence.app_settings._internal.store_impl import (
    SqliteAppSettingsStore,
)
from ollama_llm_bench.backend.persistence.app_settings._internal.version_check import (
    check_and_evolve,
)
from ollama_llm_bench.backend.persistence.app_settings.models import (
    DB_FILENAME,
    EXPECTED_SCHEMA_VERSION,
)
from ollama_llm_bench.backend.persistence.app_settings.protocols import AppSettingsStore

__all__: list[str] = [
    "DB_FILENAME",
    "EXPECTED_SCHEMA_VERSION",
    "AppSettingsStore",
    "create_app_settings_store",
    "ensure_schema",
    "open_read_connection",
    "open_write_connection",
]


@icontract.require(
    lambda db_path: db_path.is_absolute(),
    "db_path must be an absolute path — the caller (compose.py) is responsible for "
    "resolving the per-OS application-data path before calling this factory",
)
@icontract.ensure(
    lambda result: isinstance(result[1], threading.Lock),
    "the factory must always return a lock alongside the connection",
)
def open_write_connection(db_path: Path) -> tuple[sqlite3.Connection, threading.Lock]:
    """Open the application's single write connection, guarded by one lock.

    Args:
        db_path: The resolved, absolute path to the database file.

    Returns:
        The opened connection (WAL, write-connection pragma set applied) and
        the lock every write through it must acquire.

    Raises:
        PersistenceError: ``db_path`` exists but is not a valid SQLite database
            (a corrupt or foreign file); the file is left untouched.
    """
    return open_write_connection_impl(db_path)


@icontract.require(
    lambda db_path: db_path.is_absolute(),
    "db_path must be an absolute path — the caller (compose.py) is responsible for "
    "resolving the per-OS application-data path before calling this factory",
)
def open_read_connection(db_path: Path) -> sqlite3.Connection:
    """Open a fresh, read-only connection under WAL.

    A factory, not a shared singleton — call this once per reader; each call
    returns an independent connection.

    Args:
        db_path: The resolved, absolute path to the database file.

    Returns:
        A read-only connection with the read-connection pragma subset applied.

    Raises:
        PersistenceError: ``db_path`` exists but is not a valid SQLite database
            (a corrupt or foreign file); the file is left untouched.
    """
    return open_read_connection_impl(db_path)


@icontract.require(
    lambda lock: isinstance(lock, threading.Lock),
    "lock must be the threading.Lock returned by open_write_connection — this "
    "codebase's own call sites always pass that value, never an arbitrary object",
)
def ensure_schema(write_conn: sqlite3.Connection, lock: threading.Lock, *, clock: Clock) -> None:
    """Run first-run creation or the startup version check, whichever applies.

    Determines first-run vs. existing-file by querying ``sqlite_master`` for the
    ``app_meta`` table's presence on ``write_conn`` — never ``db_path.exists()``,
    since SQLite auto-creates an empty file the instant ``sqlite3.connect()``
    opens it.

    Args:
        write_conn: The single write connection, already opened.
        lock: The lock guarding ``write_conn``.
        clock: The injected time source for ``app_meta.created_at``.

    Raises:
        PersistenceError: The stored schema version is newer than expected, or
            an additive evolution step failed.
    """
    if _has_app_meta_table(write_conn):
        check_and_evolve(write_conn, lock)
    else:
        run_first_run_ddl(write_conn, lock, clock=clock)


@icontract.require(
    lambda read_conn_factory: callable(read_conn_factory),  # noqa: PLW0108  # icontract
    # binds the lambda's parameter name (`read_conn_factory`) to the guarded argument;
    # passing the bare `callable` builtin breaks that binding (its own parameter is
    # named `obj`), so the lambda wrapper is required here, not merely stylistic.
    "read_conn_factory must be a callable — this codebase's own call sites always "
    "pass open_read_connection bound to a resolved db_path, never an arbitrary value",
)
@icontract.require(
    lambda lock: isinstance(lock, threading.Lock),
    "lock must be the threading.Lock returned by open_write_connection",
)
def create_app_settings_store(
    write_conn: sqlite3.Connection,
    lock: threading.Lock,
    read_conn_factory: Callable[[], sqlite3.Connection],
    clock: Clock,
) -> AppSettingsStore:
    """Construct the concrete ``AppSettingsStore`` over the shared connection.

    Args:
        write_conn: The single write connection.
        lock: The lock guarding ``write_conn``.
        read_conn_factory: A zero-argument callable opening a fresh read-only
            connection, e.g. ``open_read_connection`` bound to the resolved
            ``db_path``.
        clock: The injected time source for ``app_settings.updated_at``.

    Returns:
        An ``AppSettingsStore`` implementation reading/writing ``app_settings``
        and ``app_meta``.
    """
    return SqliteAppSettingsStore(
        write_conn=write_conn,
        lock=lock,
        read_conn_factory=read_conn_factory,
        clock=clock,
    )


def _has_app_meta_table(write_conn: sqlite3.Connection) -> bool:
    """Return whether ``app_meta`` already exists on ``write_conn``."""
    cursor = write_conn.execute(
        "SELECT 1 FROM sqlite_master WHERE type = 'table' AND name = 'app_meta'"
    )
    return cursor.fetchone() is not None
