"""End-to-end smoke tier: the full application launched, settled, and shut down."""

from collections.abc import Callable
import sqlite3
import threading
import time
from typing import Final, cast

from PySide6.QtWidgets import QWidget
import pytest
from pytestqt.qtbot import QtBot

from ollama_llm_bench.compose import AppHandle
from ollama_llm_bench.ui.shared._internal.health_dot import HealthDotWidget

_E2E_BUDGET_S = 60.0
_IDLE_TIMEOUT_MS = 10_000
_DISPATCHER_THREAD_NAME = "pipeline-dispatcher"
_NOT_READY_HEALTH_LABEL: Final[str] = "Not ready"


def _health_dot(handle: AppHandle) -> HealthDotWidget:
    """Locate the status bar's health dot.

    Restated from `tests/integration/test_launch_not_ready_gating.py`'s identical helper (no
    importable shared home exists under `tests/`, see `conftest.py`'s module docstring). The
    dot is rebuilt on every render (`StatusBarWidget._rebuild_health_dot`), so a caller must
    re-locate it after a state change rather than caching the returned widget -- this is why
    `_wait_for_not_ready_health_dot` below calls this from inside its `waitUntil` predicate
    instead of resolving it once beforehand.
    """
    health_region = cast("QWidget", handle.window.findChild(QWidget, "health_region"))
    layout = health_region.layout()
    assert layout is not None
    item = layout.itemAt(0)
    assert item is not None
    dot = cast("HealthDotWidget", item.widget())
    assert dot is not None
    return dot


def _wait_for_not_ready_health_dot(handle: AppHandle, qtbot: QtBot) -> None:
    """Block until the status-bar health dot reflects a settled NOT_READY readiness probe.

    This can only become true once the Qt event loop has genuinely run the deferred startup
    readiness tick (`QTimer.singleShot(0, ...)`, armed on the main window's first
    `showEvent`) to completion -- the app is built fully offline with every provider
    disabled (`offline_app_data_root`), so that tick resolves to NOT_READY and the health
    dot's label settles to `"Not ready"` (`ui/main_window/_internal/status_bar.py`'s
    NOT_READY -> DOWN -> "Not ready" mapping). Waiting on this, rather than on
    `window.isVisible()` (true synchronously the instant `show()` returns, before any event
    has been pumped), is what proves the app actually reached a navigable idle state.
    """
    qtbot.waitUntil(
        lambda: _health_dot(handle).text_label == _NOT_READY_HEALTH_LABEL,
        timeout=_IDLE_TIMEOUT_MS,
    )


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
    deferred startup readiness tick to genuinely settle it into a navigable idle
    state (the status-bar health dot reaching its resolved NOT_READY label), then
    runs the ordered shutdown -- no worker thread outliving it and the database
    checkpointed and closed, inside the 60-second e2e budget.
    """
    # Arrange
    started_at = time.monotonic()
    handle = build_smoke_app()
    qtbot.addWidget(handle.window)

    # Act
    handle.window.show()
    qtbot.waitUntil(handle.window.isVisible, timeout=_IDLE_TIMEOUT_MS)
    _wait_for_not_ready_health_dot(handle, qtbot)
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
    _wait_for_not_ready_health_dot(handle, qtbot)

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
    _wait_for_not_ready_health_dot(handle, qtbot)

    # Act
    shutdown_handle(handle)

    # Assert
    with pytest.raises(sqlite3.ProgrammingError):
        handle.write_conn.execute("SELECT 1")
