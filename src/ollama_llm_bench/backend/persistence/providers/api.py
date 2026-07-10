"""Public surface for ``backend/persistence/providers/``.

The composition root constructs this store over the shared single-writer
connection and read-only connection factory opened by
``backend/persistence/app_settings/`` (ADR-0004) and injects it wherever a
``ProvidersStore`` is needed.

Source of truth: ``docs/v3_specification/08_Cross_Cutting/08-E_interfaces_contracts.md``
§7.4; ``docs/v3_specification/10_Domain_and_Data/03_PERSISTENCE_SCHEMA.md`` §10.
"""

from collections.abc import Callable
import sqlite3
import threading

import icontract

from ollama_llm_bench.backend.persistence.providers._internal.store_impl import (
    SqliteProvidersStore,
    seed_builtin_providers as seed_builtin_providers_impl,
)
from ollama_llm_bench.backend.persistence.providers.protocols import ProvidersStore

__all__: list[str] = [
    "ProvidersStore",
    "create_providers_store",
    "seed_builtin_providers",
]


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
def create_providers_store(
    write_conn: sqlite3.Connection,
    lock: threading.Lock,
    read_conn_factory: Callable[[], sqlite3.Connection],
) -> ProvidersStore:
    """Construct the concrete ``ProvidersStore`` over the shared connection.

    Args:
        write_conn: The single write connection.
        lock: The lock guarding ``write_conn``.
        read_conn_factory: A zero-argument callable opening a fresh read-only
            connection, e.g. ``open_read_connection`` bound to the resolved
            ``db_path``.

    Returns:
        A ``ProvidersStore`` implementation reading/writing ``providers`` and
        ``provider_models``.
    """
    return SqliteProvidersStore(
        write_conn=write_conn, lock=lock, read_conn_factory=read_conn_factory
    )


@icontract.require(
    lambda lock: isinstance(lock, threading.Lock),
    "lock must be the threading.Lock returned by open_write_connection",
)
def seed_builtin_providers(write_conn: sqlite3.Connection, lock: threading.Lock) -> None:
    """Seed the three built-in local providers (Ollama, LM Studio, llama.cpp).

    Writes all three ``openai_compatible`` rows in one transaction, each with
    a fresh UUID4 ``provider_id``, ``enabled = 1``, no API key, and
    ``provider_order`` 0/1/2 respectively, per
    ``10_Domain_and_Data/03_PERSISTENCE_SCHEMA.md`` §10. Safe to call again
    (e.g. Settings "Reset to Defaults") — each call re-seeds with fresh ids.

    Args:
        write_conn: The single write connection.
        lock: The lock guarding ``write_conn``.

    Raises:
        PersistenceError: The underlying write failed.
    """
    seed_builtin_providers_impl(write_conn, lock)
