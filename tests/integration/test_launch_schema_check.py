"""Integration tests for the schema-version-check launch abort path, the
corrupt-database abort path, and the write-connection pragma ordering
(STORY-078-AC-2, STORY-078-AC-3, STORY-078-AC-5, EC-M-2, EC-M-3).
"""

from pathlib import Path
import sqlite3

from PySide6.QtCore import QEventLoop
from PySide6.QtWidgets import QApplication
import pytest
from pytest_mock import MockerFixture

from ollama_llm_bench.backend.infra import make_system_clock
from ollama_llm_bench.backend.persistence.app_settings import (
    DB_FILENAME,
    ensure_schema,
    open_write_connection,
)
from ollama_llm_bench.backend.platform import create_app_data_dir, make_platform_detector
from ollama_llm_bench.compose import build_app
from ollama_llm_bench.ui.common_dialogs import ErrorDialogPattern


@pytest.fixture
def isolated_home(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    home = tmp_path / "home"
    home.mkdir()
    monkeypatch.setenv("HOME", str(home))
    monkeypatch.setenv("USERPROFILE", str(home))
    return home


def _read_app_meta_row(app_data_root: Path) -> tuple[int, str]:
    conn = sqlite3.connect(str(app_data_root / DB_FILENAME))
    row = conn.execute("SELECT schema_version, created_at FROM app_meta WHERE id = 1").fetchone()
    conn.close()
    return (int(row[0]), str(row[1]))


@pytest.fixture
def mismatched_schema_app_data_root(isolated_home: Path) -> Path:
    """Pre-create a real, schema-applied database, then corrupt its stored
    `schema_version` to a value newer than `EXPECTED_SCHEMA_VERSION`."""
    profile = make_platform_detector().detect()
    app_data_root = create_app_data_dir(profile.app_data_root)
    write_conn, lock = open_write_connection(app_data_root / DB_FILENAME)
    ensure_schema(write_conn, lock, clock=make_system_clock())
    write_conn.execute("UPDATE app_meta SET schema_version = 999 WHERE id = 1")
    write_conn.commit()
    write_conn.close()
    return app_data_root


def test_schema_version_mismatch_aborts_and_leaves_db_untouched(
    mismatched_schema_app_data_root: Path, qapp: QApplication, mocker: MockerFixture
) -> None:
    """Proves: STORY-078-AC-2

    Given an existing database whose persisted schema version does not match the
    version this build expects, when launch runs the schema check, then launch
    aborts with the hard schema-mismatch modal naming the database file, the
    database is left untouched, and the process exits (EC-M-2).
    """
    # Arrange
    row_before = _read_app_meta_row(mismatched_schema_app_data_root)
    dialog = mocker.Mock(spec=["exec"])
    make_error_dialog_spy = mocker.patch(
        "ollama_llm_bench.compose.make_error_dialog", return_value=dialog
    )

    # Act / Assert
    with pytest.raises(SystemExit) as exc_info:
        build_app(app=qapp, loop=QEventLoop())

    # Assert
    assert exc_info.value.code == 1
    payload = make_error_dialog_spy.call_args.kwargs["payload"]
    assert payload.pattern is ErrorDialogPattern.FATAL
    assert str(mismatched_schema_app_data_root / DB_FILENAME) in (payload.detail or "")
    assert _read_app_meta_row(mismatched_schema_app_data_root) == row_before


def test_unreadable_database_aborts_without_overwrite(
    isolated_home: Path, qapp: QApplication, mocker: MockerFixture
) -> None:
    """Proves: STORY-078-AC-3

    Given a database file that is present but unreadable or corrupt, when launch
    attempts to open the write connection to it, then launch aborts with an
    explanatory modal naming the database file, and the file is never
    overwritten automatically (EC-M-3).
    """
    # Arrange
    profile = make_platform_detector().detect()
    app_data_root = create_app_data_dir(profile.app_data_root)
    db_path = app_data_root / DB_FILENAME
    db_path.write_bytes(b"not a sqlite database")
    corrupt_bytes_before = db_path.read_bytes()

    dialog = mocker.Mock(spec=["exec"])
    make_error_dialog_spy = mocker.patch(
        "ollama_llm_bench.compose.make_error_dialog", return_value=dialog
    )

    # Act / Assert
    with pytest.raises(SystemExit) as exc_info:
        build_app(app=qapp, loop=QEventLoop())

    # Assert
    assert exc_info.value.code == 1
    payload = make_error_dialog_spy.call_args.kwargs["payload"]
    assert payload.pattern is ErrorDialogPattern.FATAL
    assert str(db_path) in (payload.detail or "")
    assert db_path.read_bytes() == corrupt_bytes_before


def test_write_connection_applies_pragmas_before_first_statement(
    isolated_home: Path, qapp: QApplication, mocker: MockerFixture
) -> None:
    """Proves: STORY-078-AC-5

    Given the application has launched as far as the schema check — the first
    statement run on the write connection, when that statement executes, then
    every `03_PERSISTENCE_SCHEMA.md` §2 write-connection pragma is already in
    effect on that connection.
    """
    # Arrange
    ensure_schema_spy = mocker.patch("ollama_llm_bench.compose.ensure_schema", wraps=ensure_schema)

    # Act
    handle = build_app(app=qapp, loop=QEventLoop())

    # Assert
    write_conn = ensure_schema_spy.call_args.args[0]
    assert write_conn is handle.write_conn
    assert write_conn.execute("PRAGMA journal_mode").fetchone()[0] == "wal"
    assert write_conn.execute("PRAGMA synchronous").fetchone()[0] == 1  # NORMAL
    assert write_conn.execute("PRAGMA foreign_keys").fetchone()[0] == 1
    assert write_conn.execute("PRAGMA busy_timeout").fetchone()[0] == 5000  # noqa: PLR2004

    # Cleanup
    handle.window.close()
    handle.run_dispatcher.shutdown(timeout_ms=2000)
    handle.http_client.close()
    handle.write_conn.close()
