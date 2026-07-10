"""Public surface for ``backend/persistence/model_capabilities/``.

The composition root constructs this store over the shared single-writer
connection and read-only connection factory opened by
``backend/persistence/app_settings/`` (ADR-0004) and injects it wherever a
``ModelCapabilitiesStore`` is needed.

Source of truth: ``docs/v3_specification/08_Cross_Cutting/08-E_interfaces_contracts.md``
§7.5; ``docs/v3_specification/10_Domain_and_Data/03_PERSISTENCE_SCHEMA.md`` §4.6.
"""

from collections.abc import Callable
import sqlite3
import threading

import icontract

from ollama_llm_bench.backend.persistence.model_capabilities._internal.store_impl import (
    SqliteModelCapabilitiesStore,
)
from ollama_llm_bench.backend.persistence.model_capabilities.protocols import (
    ModelCapabilitiesStore,
)

__all__: list[str] = [
    "ModelCapabilitiesStore",
    "create_model_capabilities_store",
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
def create_model_capabilities_store(
    write_conn: sqlite3.Connection,
    lock: threading.Lock,
    read_conn_factory: Callable[[], sqlite3.Connection],
) -> ModelCapabilitiesStore:
    """Construct the concrete ``ModelCapabilitiesStore`` over the shared connection.

    Args:
        write_conn: The single write connection.
        lock: The lock guarding ``write_conn``.
        read_conn_factory: A zero-argument callable opening a fresh read-only
            connection, e.g. ``open_read_connection`` bound to the resolved
            ``db_path``.

    Returns:
        A ``ModelCapabilitiesStore`` implementation reading/writing
        ``model_capabilities``.
    """
    return SqliteModelCapabilitiesStore(
        write_conn=write_conn, lock=lock, read_conn_factory=read_conn_factory
    )
