"""Unit tests for the schema-version check (colocated; real tmp_path SQLite files).

Source of truth: STORY-008 acceptance criteria AC-1, AC-2, AC-3 and EC-PERSIST-1.
"""

from pathlib import Path
import sqlite3
import threading

import pytest

from ollama_llm_bench.backend.errors import PersistenceError
from ollama_llm_bench.backend.infra.protocols import Clock
from ollama_llm_bench.backend.persistence.app_settings._internal.version_check import (
    check_and_evolve,
)
from ollama_llm_bench.backend.persistence.app_settings.api import ensure_schema
from ollama_llm_bench.backend.persistence.app_settings.models import EXPECTED_SCHEMA_VERSION


def test_first_run_creates_every_table_and_index_and_seeds_app_meta(
    initialised_write_conn_and_lock: tuple[sqlite3.Connection, threading.Lock],
) -> None:
    """Proves: STORY-008-AC-1

    First-run schema creation runs every CREATE TABLE/CREATE INDEX statement
    and writes the single app_meta row (id=1, schema_version=expected,
    non-null created_at).
    """
    # Arrange
    conn, _lock = initialised_write_conn_and_lock

    # Act
    tables = {
        row[0]
        for row in conn.execute(
            "SELECT name FROM sqlite_master WHERE type = 'table' AND name NOT LIKE 'sqlite_%'"
        ).fetchall()
    }
    app_meta_row = conn.execute(
        "SELECT id, schema_version, created_at FROM app_meta WHERE id = 1"
    ).fetchone()

    # Assert
    expected_tables = {
        "app_meta",
        "providers",
        "provider_models",
        "app_settings",
        "model_capabilities",
        "benchmark_runs",
        "benchmark_run_models",
        "benchmark_run_providers",
        "benchmark_run_settings",
        "benchmark_tasks",
        "benchmark_task_terms",
        "benchmark_results",
        "benchmark_result_terms",
        "benchmark_result_attempts",
    }
    assert expected_tables <= tables
    assert app_meta_row == (1, EXPECTED_SCHEMA_VERSION, "2026-01-01T00:00:00+00:00")


def test_matching_schema_version_performs_no_ddl_or_write(
    initialised_write_conn_and_lock: tuple[sqlite3.Connection, threading.Lock],
) -> None:
    """Proves: STORY-008-AC-2

    When the stored schema_version equals the expected version, check_and_evolve
    returns without altering app_meta.
    """
    # Arrange
    conn, lock = initialised_write_conn_and_lock
    before = conn.execute("SELECT schema_version, created_at FROM app_meta WHERE id = 1").fetchone()

    # Act
    check_and_evolve(conn, lock)

    # Assert
    after = conn.execute("SELECT schema_version, created_at FROM app_meta WHERE id = 1").fetchone()
    assert after == before


def test_newer_schema_version_raises_persistence_error_leaving_row_untouched(
    initialised_write_conn_and_lock: tuple[sqlite3.Connection, threading.Lock],
) -> None:
    """Proves: STORY-008-AC-3

    A stored schema_version higher than expected raises PersistenceError and
    performs no DDL/UPDATE — the app_meta row is left exactly as found. Covers
    EC-PERSIST-1 (the newer-than-app branch).
    """
    # Arrange
    conn, lock = initialised_write_conn_and_lock
    newer_version = EXPECTED_SCHEMA_VERSION + 1
    with lock:
        conn.execute("BEGIN IMMEDIATE")
        conn.execute("UPDATE app_meta SET schema_version = ? WHERE id = 1", (newer_version,))
        conn.commit()
    before = conn.execute("SELECT schema_version, created_at FROM app_meta WHERE id = 1").fetchone()

    # Act / Assert
    with pytest.raises(PersistenceError):
        check_and_evolve(conn, lock)

    after = conn.execute("SELECT schema_version, created_at FROM app_meta WHERE id = 1").fetchone()
    assert after == before


def test_ensure_schema_first_run_then_reopen_reports_match(
    db_path: Path,
    fake_clock: Clock,
) -> None:
    """Proves: STORY-008-AC-1

    Calling ensure_schema twice against the same file — first-run creation,
    then a startup version check on the already-initialised file — leaves the
    database in a valid, matching-version state with no error.
    """
    # Arrange
    conn = sqlite3.connect(str(db_path), isolation_level=None, check_same_thread=False)
    lock = threading.Lock()

    # Act
    ensure_schema(conn, lock, clock=fake_clock)
    ensure_schema(conn, lock, clock=fake_clock)

    # Assert
    version = conn.execute("SELECT schema_version FROM app_meta WHERE id = 1").fetchone()[0]
    assert version == EXPECTED_SCHEMA_VERSION
    conn.close()
