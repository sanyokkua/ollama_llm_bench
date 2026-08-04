"""Fixtures for the end-to-end smoke tier: an isolated, fully offline composed app.

`tests/integration/conftest.py` holds an equivalent rig, but a conftest applies only
to descendants of its own directory and there are no `__init__.py` files under
`tests/` to import a shared helper through, so the rig is restated here rather than
shared -- a deliberate duplication, not an oversight.
"""

from collections.abc import Callable, Generator
import functools
from pathlib import Path
import warnings

import msgspec
from PySide6.QtCore import QEvent, QEventLoop, QObject, Qt, QTimer, SignalInstance
from PySide6.QtWidgets import QApplication, QMessageBox
import pytest
from pytestqt.qtbot import QtBot

from ollama_llm_bench.backend.infra import make_system_clock
from ollama_llm_bench.backend.persistence.app_settings import (
    DB_FILENAME,
    ensure_schema,
    open_read_connection,
    open_write_connection,
)
from ollama_llm_bench.backend.persistence.providers import (
    create_providers_store,
    seed_builtin_providers,
)
from ollama_llm_bench.backend.platform import create_app_data_dir, make_platform_detector
from ollama_llm_bench.compose import AppHandle, build_app

_SHUTDOWN_TIMEOUT_MS = 2000
_GEOMETRY_DEBOUNCE_DRAIN_MS = 300
_NOT_READY_MODAL_DISMISS_DELAY_MS = 100


def _disconnect_and_discard_warning(signal: SignalInstance) -> None:
    """Disconnect every slot from `signal`, discarding whatever warning PySide6 emits.

    `SignalInstance.disconnect()` does not raise when nothing is connected -- it emits a
    Python-level `RuntimeWarning` straight from the C++ binding and returns normally.
    `warnings.catch_warnings(record=True)` combined with `simplefilter("always")` captures
    that warning into a local list this function never inspects, so it never escapes to the
    caller or to pytest's warning capture.
    """
    with warnings.catch_warnings(record=True):
        warnings.simplefilter("always")
        signal.disconnect()


@pytest.fixture(autouse=True)
def _disconnect_os_color_scheme_signal(qapp: QApplication) -> Generator[None]:
    """Drop the `colorSchemeChanged` connection each `build_app` leaves on the shared qapp.

    `ThemeManager` connects to the session-scoped `qapp.styleHints()` and production
    never disconnects it, so without this every built app leaks a connection into the
    next test.
    """
    yield
    _disconnect_and_discard_warning(qapp.styleHints().colorSchemeChanged)
    qapp.styleHints().unsetColorScheme()


@pytest.fixture
def isolated_home(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    """Redirect the resolved app-data root into `tmp_path`.

    The root `_isolate_filesystem` fixture sets only the XDG/LOCALAPPDATA variables.
    On macOS the platform detector ignores those and reads `Path.home()`, so `HOME`
    and `USERPROFILE` are the only cross-platform lever.
    """
    home = tmp_path / "home"
    home.mkdir(parents=True, exist_ok=True)
    monkeypatch.setenv("HOME", str(home))
    monkeypatch.setenv("USERPROFILE", str(home))
    return home


def _create_app_data_root_with_schema() -> Path:
    """Create, and apply the schema to, the database at the exact `<app-data>` path
    `build_app` itself will resolve and open (same detector, same environment).

    Returns the app-data root with the write connection already closed, so the caller
    can reopen it to seed rows before `build_app` opens its own connection.
    """
    profile = make_platform_detector().detect()
    app_data_root = create_app_data_dir(profile.app_data_root)
    write_conn, lock = open_write_connection(app_data_root / DB_FILENAME)
    ensure_schema(write_conn, lock, clock=make_system_clock())
    write_conn.close()
    return app_data_root


@pytest.fixture
def offline_app_data_root(isolated_home: Path) -> Path:
    """Seed the app-data directory, then disable every provider so no probe dials out.

    Leaving the catalog empty does not work: `build_app` re-seeds the builtins whenever
    it finds `providers` empty, and those point at localhost:11434 / localhost:1234. On a
    developer machine running Ollama or LM Studio that is real network I/O from a test
    that looks clean on an offline CI runner. Seeding the rows first, then disabling every
    one, means the catalog is non-empty (so `build_app`'s fresh-install re-seed never
    fires) and nothing enabled is left for the readiness probe to dial.
    """
    app_data_root = _create_app_data_root_with_schema()
    db_path = app_data_root / DB_FILENAME
    write_conn, lock = open_write_connection(db_path)
    seed_builtin_providers(write_conn, lock)
    store = create_providers_store(write_conn, lock, functools.partial(open_read_connection, db_path))  # fmt: skip
    store.replace_providers(
        tuple(msgspec.structs.replace(config, enabled=False) for config in store.list_providers())
    )
    write_conn.close()
    return app_data_root


def _dismiss_message_box(modal: QMessageBox) -> None:
    """Hide `modal` in a way that always removes it from Qt's modal-widget stack.

    Identical mechanics to `tests/integration/conftest.py`'s `_dismiss_message_box` (restated
    here, not imported -- see this module's own docstring on why the rig is duplicated).
    `QDialog.exec()` (which `QMessageBox.critical()` calls internally) shows the dialog, which
    is what pushes it onto `QApplication.activeModalWidget()`'s stack; a plain `close()`/
    `hide()` after the nested loop is already running does not reliably pop that stack back
    off, and a stale entry left behind aborts a later, unrelated test's own modal lookup with a
    fatal `QTEST_ASSERT` inside Qt. Restoring `WA_ShowModal` immediately before hiding makes Qt
    run `leaveModal` and clears the stack properly.
    """
    modal.setAttribute(Qt.WidgetAttribute.WA_ShowModal, on=True)
    modal.hide()
    modal.setAttribute(Qt.WidgetAttribute.WA_ShowModal, on=False)


class _DismissReadinessModalOnShow(QObject):
    """App-wide event filter that auto-dismisses the real NOT_READY `QMessageBox` the instant
    it is shown, wherever in a test's execution it happens to appear.

    Restated from `tests/integration/conftest.py`'s identical class -- see this module's own
    docstring for why the rig is duplicated rather than shared. `offline_app_data_root`
    disables every provider so the fixture never dials a real network endpoint, but a fully
    offline application with zero enabled providers is genuinely `NOT_READY`
    (`08_Cross_Cutting/08-M_app_lifecycle.md` §5), and production surfaces that state with a
    blocking `QMessageBox.critical(...)` modal the first time the deferred,
    `QTimer.singleShot(0, ...)`-scheduled startup readiness tick resolves it
    (`main_window_shown_readiness_probe_scheduled` -> `QtNotificationService._show_modal` ->
    `.exec()`).

    **Why a one-shot timer armed once, right after `build_app()` returns, is not enough.** That
    0ms readiness timer is armed the moment `window.show()` fires its `showEvent`, but stays
    *pending*, undelivered, until something next pumps the Qt event loop -- which happens only
    once a test starts genuinely waiting on real application state (e.g. the status-bar health
    dot settling). A dismiss timer armed once, at a fixed short delay after build time, can
    easily fire before the modal exists yet if that first real event-loop pump happens later
    than the delay -- the timer then finds nothing to dismiss, and the modal opens afterwards
    into a nested loop nothing will ever unwind, hanging the suite. An event filter watching
    for the moment Qt actually shows a `QMessageBox` is the only thing that reliably catches it
    regardless of when the pump happens.

    **Why the dismiss is scheduled on a delay rather than done synchronously inside the Show
    event.** `QDialog.exec()`'s sequence is `show()` (which is what dispatches the `Show` event
    this filter reacts to) followed by constructing and running its own nested `QEventLoop` --
    that loop object does not exist yet while `show()` is still on the call stack, so hiding
    the widget from directly inside the event filter has nothing to make the nested loop
    return; the loop would still block forever once `exec()` reaches it. Coming back a little
    later, once the nested loop is actually running, is what lets the dismissal take effect.
    """

    def eventFilter(self, watched: QObject, event: QEvent) -> bool:
        if event.type() == QEvent.Type.Show and isinstance(watched, QMessageBox):
            QTimer.singleShot(
                _NOT_READY_MODAL_DISMISS_DELAY_MS, functools.partial(_dismiss_message_box, watched)
            )
        return False


@pytest.fixture
def build_smoke_app(
    qapp: QApplication, offline_app_data_root: Path
) -> Generator[Callable[[], AppHandle]]:
    """Build the real composed app against the offline app-data root.

    Installs `_DismissReadinessModalOnShow` on `qapp` for the fixture's lifetime: every app
    built here is fully offline with no enabled provider (see `offline_app_data_root`), so its
    deferred startup readiness tick genuinely resolves NOT_READY and production genuinely opens
    a real blocking `QMessageBox.critical` modal -- the filter catches and dismisses it
    whenever it actually appears, rather than guessing when.
    """
    built: list[AppHandle] = []
    dismiss_not_ready_modal = _DismissReadinessModalOnShow()
    qapp.installEventFilter(dismiss_not_ready_modal)

    def _build() -> AppHandle:
        handle = build_app(app=qapp, loop=QEventLoop())
        built.append(handle)
        return handle

    yield _build
    qapp.removeEventFilter(dismiss_not_ready_modal)
    for handle in built:
        handle.window.close()


@pytest.fixture
def shutdown_handle(qtbot: QtBot) -> Callable[[AppHandle], None]:
    """Run the ordered shutdown the way production does -- window first, then handle.

    `AppHandle.shutdown` is not idempotent -- a second call raises `sqlite3.ProgrammingError`
    on the already-closed connection. `build_smoke_app`'s finalizer therefore only closes the
    window; a test calls this exactly once per handle.

    **Drains the geometry debounce timer before closing the database.** `window.close()`
    routes through `CloseHandler` -> `_on_confirmed_quit`, which flushes the pending window
    geometry synchronously and then calls `shell.force_close()`. That second, real `close()`
    hides the window, which -- observed empirically under the offscreen Qt platform plugin --
    re-fires a resize/move event that re-arms `DebouncedGeometryWriter`'s single-shot 200ms
    timer with a fresh pending write. Left undrained, that timer only fires once *something
    else* next pumps the Qt event loop (typically the next test), by which point this
    fixture has already closed the write connection underneath it, crashing with
    `sqlite3.ProgrammingError: Cannot operate on a closed database` in a later, unrelated
    test. `qtbot.wait` past the 200ms debounce window lets that trailing write land while
    the connection is still open, so the shutdown below closes it cleanly instead.

    By the time a test calls this, it has already waited for the status-bar health dot to
    settle into NOT_READY (see `_wait_for_not_ready_health_dot` in the test module), so the
    real modal has already appeared and been dismissed by `build_smoke_app`'s installed
    `_DismissReadinessModalOnShow` filter -- this fixture no longer needs its own dismiss
    timer.
    """

    def _shutdown(handle: AppHandle) -> None:
        handle.window.close()
        qtbot.wait(_GEOMETRY_DEBOUNCE_DRAIN_MS)
        handle.shutdown(timeout_ms=_SHUTDOWN_TIMEOUT_MS)

    return _shutdown
