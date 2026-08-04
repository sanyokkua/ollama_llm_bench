"""End-to-end smoke tier: the full application launched, settled, and shut down."""

from collections.abc import Callable
import sqlite3
import threading
import time

import pytest
from pytestqt.qtbot import QtBot

from ollama_llm_bench.compose import AppHandle

_E2E_BUDGET_S = 60.0
_IDLE_TIMEOUT_MS = 10_000
_DISPATCHER_THREAD_NAME = "pipeline-dispatcher"


@pytest.mark.allow_qt_warnings  # offscreen-only: the deferred startup readiness tick
# opens the real `NOT_READY` modal (every provider is disabled for offline safety --
# see `offline_app_data_root`'s docstring) and that dialog resizes a widget before the
# offscreen platform plugin has a native window to hint, which logs "This plugin does
# not support propagateSizeHints()" -- pre-existing offscreen-plugin behaviour (also hit
# by `tests/integration/test_launch_abort_modal_quits.py`'s real-dialog `.exec()`), not
# a defect in this test or the production dialog wiring.
def test_app_launches_reaches_idle_and_shuts_down_cleanly(
    qtbot: QtBot,
    build_smoke_app: Callable[[], AppHandle],
    shutdown_handle: Callable[[AppHandle], None],
) -> None:
    """Proves: STORY-081-AC-1

    Launches the whole wired application, shows the main window, waits for the
    deferred startup readiness tick to settle it into a navigable idle state,
    then runs the ordered shutdown -- no worker thread outliving it and the
    database checkpointed and closed, inside the 60-second e2e budget.
    """
    # Arrange
    started_at = time.monotonic()
    handle = build_smoke_app()
    qtbot.addWidget(handle.window)

    # Act
    handle.window.show()
    qtbot.waitUntil(handle.window.isVisible, timeout=_IDLE_TIMEOUT_MS)
    shutdown_handle(handle)

    # Assert
    assert time.monotonic() - started_at < _E2E_BUDGET_S


@pytest.mark.allow_qt_warnings  # offscreen-only: see the identical marker on
# test_app_launches_reaches_idle_and_shuts_down_cleanly above -- the same NOT_READY
# modal fires on every one of this file's tests, since each builds its own app.
def test_shutdown_leaves_no_dispatcher_thread_running(
    qtbot: QtBot,
    build_smoke_app: Callable[[], AppHandle],
    shutdown_handle: Callable[[AppHandle], None],
) -> None:
    """Proves: STORY-081-AC-1

    The ordered shutdown joins the dispatcher thread; no worker outlives it.
    """
    # Arrange
    handle = build_smoke_app()
    qtbot.addWidget(handle.window)
    handle.window.show()
    qtbot.waitUntil(handle.window.isVisible, timeout=_IDLE_TIMEOUT_MS)

    # Act
    shutdown_handle(handle)

    # Assert
    assert not [t for t in threading.enumerate() if t.name == _DISPATCHER_THREAD_NAME]


@pytest.mark.allow_qt_warnings  # offscreen-only: see the identical marker on
# test_app_launches_reaches_idle_and_shuts_down_cleanly above -- the same NOT_READY
# modal fires on every one of this file's tests, since each builds its own app.
def test_shutdown_closes_the_write_connection(
    qtbot: QtBot,
    build_smoke_app: Callable[[], AppHandle],
    shutdown_handle: Callable[[AppHandle], None],
) -> None:
    """Proves: STORY-081-AC-1

    The database is checkpointed and closed, so any later statement is rejected.
    """
    # Arrange
    handle = build_smoke_app()
    qtbot.addWidget(handle.window)
    handle.window.show()
    qtbot.waitUntil(handle.window.isVisible, timeout=_IDLE_TIMEOUT_MS)

    # Act
    shutdown_handle(handle)

    # Assert
    with pytest.raises(sqlite3.ProgrammingError):
        handle.write_conn.execute("SELECT 1")
