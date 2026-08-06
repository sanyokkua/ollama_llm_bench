"""Integration tests for the ordered shutdown sequence (STORY-080-AC-4, AC-6, AC-7)."""

import functools
from pathlib import Path
import sqlite3
from typing import cast

import msgspec.structs
from PySide6.QtCore import QEventLoop, Qt
from PySide6.QtWidgets import QApplication, QPushButton
import pytest
from pytest_mock import MockerFixture
from pytestqt.qtbot import QtBot

from ollama_llm_bench.backend.infra import (
    InstanceLockOutcome,
    acquire_instance_lock,
    make_system_clock,
)
from ollama_llm_bench.backend.persistence.app_settings import (
    DB_FILENAME,
    create_app_settings_store,
    ensure_schema,
    open_read_connection,
    open_write_connection,
)
from ollama_llm_bench.backend.persistence.providers import seed_builtin_providers
from ollama_llm_bench.backend.platform import create_app_data_dir, make_platform_detector
from ollama_llm_bench.compose import build_app

_SHUTDOWN_TIMEOUT_MS = 2000


class _RecordingConnectionProxy:
    """Records `execute`/`close` call order before delegating to the real connection.

    `sqlite3.Connection` is an immutable C type -- `mocker.patch.object` on either
    the instance or the class raises `AttributeError: ... attribute 'execute' is
    read-only`, so it cannot be spied on directly. This proxy is swapped in for
    `AppHandle.write_conn` via `msgspec.structs.replace` instead, since
    `AppHandle.shutdown()` only ever calls `.execute(...)` and `.close()` on it.
    """

    def __init__(self, real: sqlite3.Connection, call_order: list[str]) -> None:
        self._real = real
        self._call_order = call_order

    def execute(self, sql: str, *args: object) -> object:
        if "wal_checkpoint" in sql:
            self._call_order.append("db_checkpoint")
        return self._real.execute(sql, *args)  # type: ignore[arg-type]  # forwarding a generic proxy signature to sqlite3.Connection.execute's real (sql, parameters) shape

    def close(self) -> None:
        self._call_order.append("db_close")
        self._real.close()


@pytest.fixture
def isolated_home(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    home = tmp_path / "home"
    home.mkdir()
    monkeypatch.setenv("HOME", str(home))
    monkeypatch.setenv("USERPROFILE", str(home))
    return home


@pytest.fixture
def seeded_app_data_root(isolated_home: Path) -> Path:
    profile = make_platform_detector().detect()
    app_data_root = create_app_data_dir(profile.app_data_root)
    write_conn, lock = open_write_connection(app_data_root / DB_FILENAME)
    ensure_schema(write_conn, lock, clock=make_system_clock())
    seed_builtin_providers(write_conn, lock)
    write_conn.close()
    return app_data_root


def test_quit_closes_db_with_wal_checkpoint_truncate(
    seeded_app_data_root: Path, qapp: QApplication
) -> None:
    """Proves: STORY-080-AC-4

    Given the application is quitting, when `AppHandle.shutdown()` runs, then
    `PRAGMA wal_checkpoint(TRUNCATE)` runs on the write connection before it
    is closed, and the database's `-wal` file is reclaimed (zero-length or
    absent) once shutdown returns.
    """
    # Arrange
    handle = build_app(app=qapp, loop=QEventLoop())
    wal_path = seeded_app_data_root / f"{DB_FILENAME}-wal"

    # Act
    handle.window.close()
    handle.shutdown(timeout_ms=_SHUTDOWN_TIMEOUT_MS)

    # Assert
    assert not wal_path.exists() or wal_path.stat().st_size == 0


def test_ordered_shutdown_runs_all_six_steps_in_order(
    seeded_app_data_root: Path, qapp: QApplication, mocker: MockerFixture
) -> None:
    """Proves: STORY-080-AC-6

    Given the application is quitting, when the ordered shutdown runs, then
    these six actions are each performed exactly once, in exactly this order:
    hard-cancel, dispatcher-join-then-pool-drain, HTTP-client close,
    checkpoint-then-close the write connection, instance-lock release, process
    exit (the sixth step, process exit, is `__main__.py`'s responsibility per
    the story's design constraints -- not exercised here, since this test calls
    `AppHandle.shutdown()` directly, not `main()`).
    """
    # Arrange
    handle = build_app(app=qapp, loop=QEventLoop())
    handle.window.close()
    call_order: list[str] = []

    real_flow_shutdown = handle.flow.shutdown
    real_task_runner_shutdown = handle.task_runner.shutdown
    real_http_client_close = handle.http_client.close
    real_instance_lock_release = handle.instance_lock.release

    def _flow_shutdown(timeout_ms: int) -> None:
        call_order.append("flow_shutdown")
        real_flow_shutdown(timeout_ms)

    def _task_runner_shutdown() -> None:
        call_order.append("task_runner_shutdown")
        real_task_runner_shutdown()

    def _http_client_close() -> None:
        call_order.append("http_client_close")
        real_http_client_close()

    def _instance_lock_release() -> None:
        call_order.append("instance_lock_release")
        real_instance_lock_release()

    # Every mock below still performs the real action after recording its call --
    # a pure recording stub here would leave the real (non-daemon) dispatcher
    # thread unjoined, the real HTTP client unclosed, and the real instance lock
    # unreleased, which can hang the pytest process at exit (a `daemon=False`
    # thread blocks interpreter shutdown) rather than fail this one test cleanly.
    mocker.patch.object(handle.flow, "shutdown", side_effect=_flow_shutdown)
    mocker.patch.object(handle.task_runner, "shutdown", side_effect=_task_runner_shutdown)
    mocker.patch.object(handle.http_client, "close", side_effect=_http_client_close)
    mocker.patch.object(handle.instance_lock, "release", side_effect=_instance_lock_release)
    proxied_write_conn = cast(
        "sqlite3.Connection", _RecordingConnectionProxy(handle.write_conn, call_order)
    )
    shutdown_handle = msgspec.structs.replace(handle, write_conn=proxied_write_conn)

    # Act
    shutdown_handle.shutdown(timeout_ms=_SHUTDOWN_TIMEOUT_MS)

    # Assert
    assert call_order == [
        "flow_shutdown",
        "task_runner_shutdown",
        "http_client_close",
        "db_checkpoint",
        "db_close",
        "instance_lock_release",
    ]


def test_instance_lock_is_reacquirable_after_clean_quit(
    seeded_app_data_root: Path, qapp: QApplication
) -> None:
    """Proves: STORY-080-AC-7

    Given the application has quit through the ordered shutdown, when a
    second process acquires the single-instance lock against the same
    application data directory, then acquisition succeeds immediately
    without needing the stale-owner reclaim path.
    """
    # Arrange
    handle = build_app(app=qapp, loop=QEventLoop())
    handle.window.close()

    # Act
    handle.shutdown(timeout_ms=_SHUTDOWN_TIMEOUT_MS)
    reacquired = acquire_instance_lock(
        app_data_root=seeded_app_data_root, clock=make_system_clock()
    )

    # Assert
    try:
        assert reacquired.outcome is InstanceLockOutcome.ACQUIRED
        assert reacquired.lock is not None
    finally:
        if reacquired.lock is not None:
            reacquired.lock.release()


def test_quit_persists_ui_state_before_closing_db(
    seeded_app_data_root: Path, qapp: QApplication, qtbot: QtBot
) -> None:
    """Proves: STORY-080-AC-3

    Given a quit has been confirmed, when the confirmed-quit path runs, then
    the active workspace has been written through the settings service before
    the database write connection is closed.
    """
    # Arrange
    handle = build_app(app=qapp, loop=QEventLoop())
    qtbot.addWidget(handle.window)
    task_editor_button = cast(
        "QPushButton",
        handle.window.findChild(QPushButton, "workspace_task_editor_button"),
    )
    assert task_editor_button is not None
    qtbot.mouseClick(  # type: ignore[no-untyped-call]  # pytest-qt provides no type stubs
        task_editor_button, Qt.MouseButton.LeftButton
    )

    # Act
    handle.window.close()
    handle.shutdown(timeout_ms=_SHUTDOWN_TIMEOUT_MS)

    # Assert
    db_path = seeded_app_data_root / DB_FILENAME
    after_write_conn, after_lock = open_write_connection(db_path)
    try:
        appset = create_app_settings_store(
            after_write_conn,
            after_lock,
            functools.partial(open_read_connection, db_path),
            make_system_clock(),
        )
        assert appset.get_setting("ui.active_workspace") == "task_editor"
    finally:
        after_write_conn.close()
