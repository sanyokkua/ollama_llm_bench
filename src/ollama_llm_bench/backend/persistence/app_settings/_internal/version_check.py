"""The startup schema-version check and additive evolution (DD-53).

Source of truth:
``docs/v3_specification/10_Domain_and_Data/03_PERSISTENCE_SCHEMA.md`` §8 (schema
versioning) and ``08_Cross_Cutting/08-I_edge_cases.md`` EC-PERSIST-1.
"""

import sqlite3
import threading

from ollama_llm_bench.backend.errors import PersistenceError
from ollama_llm_bench.backend.persistence.app_settings._internal.schema_ddl import ADDITIVE_STEPS
from ollama_llm_bench.backend.persistence.app_settings.models import EXPECTED_SCHEMA_VERSION

__all__: list[str] = [
    "check_and_evolve",
]


def check_and_evolve(write_conn: sqlite3.Connection, lock: threading.Lock) -> None:
    """Compare the stored schema version to the expected version and evolve if needed.

    Reads ``app_meta.schema_version`` and compares it to
    ``EXPECTED_SCHEMA_VERSION``:

    - **Match** — returns immediately; no DDL, no write to ``app_meta``.
    - **Higher than expected** — raises ``PersistenceError``; no DDL, no
      ``UPDATE``, no file mutation. (DD-53 also names a "cross-major lineage"
      hard-error trigger; no spec file defines a major-lineage numbering
      scheme yet, and ``EXPECTED_SCHEMA_VERSION`` starts at 1, so every
      version compared here is necessarily same-major today — that branch is
      deferred until a future non-additive break defines the scheme via its
      own ADR.)
    - **Lower (same-major)** — walks ``ADDITIVE_STEPS`` from the stored
      version to ``EXPECTED_SCHEMA_VERSION``, applying each step's statements
      plus the ``app_meta.schema_version`` update in one ``BEGIN IMMEDIATE``
      transaction per step.

    Args:
        write_conn: The single write connection.
        lock: The lock guarding ``write_conn``.

    Raises:
        PersistenceError: The stored version is higher than expected, or an
            additive step failed to apply (prior committed steps stay applied).
    """
    current = _read_schema_version(write_conn)

    if current == EXPECTED_SCHEMA_VERSION:
        return

    if current > EXPECTED_SCHEMA_VERSION:
        message = (
            f"database schema_version {current} is newer than this build's expected "
            f"version {EXPECTED_SCHEMA_VERSION}; the database is incompatible with "
            "this application build"
        )
        raise PersistenceError(message=message)

    _apply_additive_steps(write_conn, lock, current=current)


def _read_schema_version(write_conn: sqlite3.Connection) -> int:
    """Read ``app_meta.schema_version`` from the write connection.

    Raises:
        PersistenceError: The read failed or the row is missing.
    """
    try:
        cursor = write_conn.execute("SELECT schema_version FROM app_meta WHERE id = 1")
        row = cursor.fetchone()
    except sqlite3.Error as exc:
        message = "failed to read app_meta.schema_version"
        raise PersistenceError(message=message) from exc
    if row is None:
        message = "app_meta has no row with id = 1; the database was not initialised correctly"
        raise PersistenceError(message=message)
    return int(row[0])


def _apply_additive_steps(
    write_conn: sqlite3.Connection, lock: threading.Lock, *, current: int
) -> None:
    """Apply the ordered additive steps from ``current`` up to the expected version.

    Raises:
        PersistenceError: A step's DDL or version-bump statement failed; prior
            committed steps remain applied.
    """
    version = current
    for step in ADDITIVE_STEPS:
        if step.from_version < version:
            continue
        if version >= EXPECTED_SCHEMA_VERSION:
            break
        with lock:
            write_conn.execute("BEGIN IMMEDIATE")
            try:
                for statement in step.statements:
                    write_conn.execute(statement)
                write_conn.execute(
                    "UPDATE app_meta SET schema_version = ? WHERE id = 1",
                    (step.to_version,),
                )
                write_conn.commit()
            except sqlite3.Error as exc:
                write_conn.rollback()
                message = (
                    f"failed to apply additive schema step {step.from_version} -> {step.to_version}"
                )
                raise PersistenceError(message=message) from exc
        version = step.to_version
