"""Integration tests for the app_settings persistence foundation.

Exercises the real public surface of ``backend/persistence/app_settings/`` —
``open_write_connection``, ``open_read_connection``, ``ensure_schema``, and
``create_app_settings_store`` — against a real ``tmp_path`` SQLite database
file, never ``:memory:``.

Source of truth: STORY-008 acceptance criteria AC-1, AC-2, AC-3, AC-6 and
``docs/v3_specification/08_Cross_Cutting/08-I_edge_cases.md`` EC-PERSIST-1,
EC-PERSIST-5.
"""

import hashlib
from pathlib import Path

import pytest

from ollama_llm_bench.backend.errors import PersistenceError
from ollama_llm_bench.backend.infra.protocols import Clock
from ollama_llm_bench.backend.persistence.app_settings import (
    EXPECTED_SCHEMA_VERSION,
    create_app_settings_store,
    ensure_schema,
    open_read_connection,
    open_write_connection,
)


def test_first_run_creates_schema_and_seeds_app_meta(db_path: Path, clock: Clock) -> None:
    """Proves: STORY-008-AC-1

    Given no database file exists at the resolved path, when the module opens
    the database, then a new file is created, every CREATE TABLE/CREATE INDEX
    statement has run, and the single app_meta row exists with id=1,
    schema_version equal to the embedded expected version, and a non-null
    created_at.
    """
    # Arrange
    assert not db_path.exists()

    # Act
    write_conn, lock = open_write_connection(db_path)
    try:
        ensure_schema(write_conn, lock, clock=clock)

        # Assert
        assert db_path.exists()
        tables = {
            row[0]
            for row in write_conn.execute(
                "SELECT name FROM sqlite_master WHERE type = 'table' AND name NOT LIKE 'sqlite_%'"
            ).fetchall()
        }
        app_meta_row = write_conn.execute(
            "SELECT id, schema_version, created_at FROM app_meta WHERE id = 1"
        ).fetchone()
        assert {"app_meta", "app_settings", "providers", "benchmark_runs"} <= tables
        assert app_meta_row is not None
        assert app_meta_row[0] == 1
        assert app_meta_row[1] == EXPECTED_SCHEMA_VERSION
        assert app_meta_row[2] is not None
    finally:
        write_conn.close()


def test_matching_schema_version_performs_no_ddl(db_path: Path, clock: Clock) -> None:
    """Proves: STORY-008-AC-2

    Given an existing database whose app_meta.schema_version equals the
    embedded expected version, when the version check runs, then it reports a
    match and performs no DDL and no write to app_meta.
    """
    # Arrange
    write_conn, lock = open_write_connection(db_path)
    try:
        ensure_schema(write_conn, lock, clock=clock)
        before = write_conn.execute(
            "SELECT schema_version, created_at FROM app_meta WHERE id = 1"
        ).fetchone()
        table_count_before = write_conn.execute(
            "SELECT COUNT(*) FROM sqlite_master WHERE type = 'table'"
        ).fetchone()[0]

        # Act
        ensure_schema(write_conn, lock, clock=clock)

        # Assert
        after = write_conn.execute(
            "SELECT schema_version, created_at FROM app_meta WHERE id = 1"
        ).fetchone()
        table_count_after = write_conn.execute(
            "SELECT COUNT(*) FROM sqlite_master WHERE type = 'table'"
        ).fetchone()[0]
        assert after == before
        assert table_count_after == table_count_before
    finally:
        write_conn.close()


def test_newer_or_cross_major_version_is_hard_error_leaving_file_untouched(
    db_path: Path, clock: Clock
) -> None:
    """Proves: STORY-008-AC-3

    Given an existing database whose app_meta.schema_version is higher than
    the embedded expected version, when the version check runs, then it
    raises a hard startup error and the database file is left byte-for-byte
    unchanged on disk (no DDL, no UPDATE, no app_meta rewrite) — asserted here
    by a genuine hash comparison of the actual .db file bytes before/after the
    failed call, not merely the absence of a propagated exception side effect.
    Also covers EC-PERSIST-1's newer-than-app branch (STORY-008 declares
    EC-PERSIST-1 in its edge_cases front-matter, so this AC-3 test is also
    the edge case's proving test per the traceability generator's transitive
    AC-to-edge-case mapping).
    """
    # Arrange
    write_conn, lock = open_write_connection(db_path)
    ensure_schema(write_conn, lock, clock=clock)
    newer_version = EXPECTED_SCHEMA_VERSION + 1
    with lock:
        write_conn.execute("BEGIN IMMEDIATE")
        write_conn.execute("UPDATE app_meta SET schema_version = ? WHERE id = 1", (newer_version,))
        write_conn.commit()
    write_conn.execute("PRAGMA wal_checkpoint(FULL)")
    write_conn.close()

    hash_before = _hash_file(db_path)
    stat_before = db_path.stat()

    # Act
    write_conn2, lock2 = open_write_connection(db_path)
    try:
        with pytest.raises(PersistenceError):
            ensure_schema(write_conn2, lock2, clock=clock)
    finally:
        write_conn2.close()

    # Assert
    hash_after = _hash_file(db_path)
    stat_after = db_path.stat()
    assert hash_after == hash_before
    assert stat_after.st_size == stat_before.st_size
    assert stat_after.st_mtime == stat_before.st_mtime


def test_setting_upsert_read_and_schema_version(db_path: Path, clock: Clock) -> None:
    """Proves: STORY-008-AC-6

    Given the app_settings table, when upsert_settings writes a set of keys
    and get_setting/list_settings read them back, then a written key returns
    its stored value, an unwritten key returns None from get_setting, and
    get_schema_version returns the integer stored in app_meta.schema_version.
    """
    # Arrange
    write_conn, lock = open_write_connection(db_path)
    try:
        ensure_schema(write_conn, lock, clock=clock)
        store = create_app_settings_store(
            write_conn, lock, lambda: open_read_connection(db_path), clock
        )

        # Act
        store.upsert_settings({"ui.theme": "dark", "benchmark.retry_count": "3"})

        # Assert
        assert store.get_setting("ui.theme") == "dark"
        assert store.get_setting("benchmark.never_written") is None
        assert store.list_settings() == {"ui.theme": "dark", "benchmark.retry_count": "3"}
        assert store.get_schema_version() == EXPECTED_SCHEMA_VERSION
    finally:
        write_conn.close()


def test_absent_file_is_first_run(db_path: Path, clock: Clock) -> None:
    """Proves: EC-PERSIST-5

    An absent database file is created fresh with the current schema and
    recorded schema version — a normal first-run path, not an error.
    """
    # Arrange
    assert not db_path.exists()

    # Act
    write_conn, lock = open_write_connection(db_path)
    try:
        ensure_schema(write_conn, lock, clock=clock)

        # Assert
        version = write_conn.execute("SELECT schema_version FROM app_meta WHERE id = 1").fetchone()[
            0
        ]
        assert version == EXPECTED_SCHEMA_VERSION
    finally:
        write_conn.close()


def test_corrupt_file_is_hard_error(db_path: Path) -> None:
    """Proves: EC-PERSIST-5

    A present-but-not-a-valid-database file is a hard startup error — it
    raises this module's own PersistenceError rather than silently succeeding,
    corrupting further, or leaking a raw sqlite3 exception — and the file is
    never deleted or overwritten by this module.
    """
    # Arrange
    db_path.write_bytes(b"this is not a sqlite database, just garbage bytes\x00\x01\x02")
    original_bytes = db_path.read_bytes()

    # Act / Assert
    with pytest.raises(PersistenceError):
        open_write_connection(db_path)

    assert db_path.read_bytes() == original_bytes


def _hash_file(path: Path) -> str:
    """Return a hex digest of a file's exact bytes, for byte-for-byte comparison."""
    return hashlib.sha256(path.read_bytes()).hexdigest()
