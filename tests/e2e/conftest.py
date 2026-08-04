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
from PySide6.QtCore import QEventLoop, Qt, QTimer, SignalInstance
from PySide6.QtWidgets import QApplication
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


@pytest.fixture
def build_smoke_app(
    qapp: QApplication, offline_app_data_root: Path
) -> Generator[Callable[[], AppHandle]]:
    """Build the real composed app against the offline app-data root."""
    built: list[AppHandle] = []

    def _build() -> AppHandle:
        handle = build_app(app=qapp, loop=QEventLoop())
        built.append(handle)
        return handle

    yield _build
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
    """

    def _shutdown(handle: AppHandle) -> None:
        handle.window.close()
        QTimer.singleShot(_NOT_READY_MODAL_DISMISS_DELAY_MS, _dismiss_active_modal_if_shown)
        qtbot.wait(_GEOMETRY_DEBOUNCE_DRAIN_MS)
        handle.shutdown(timeout_ms=_SHUTDOWN_TIMEOUT_MS)

    return _shutdown


def _dismiss_active_modal_if_shown() -> None:
    """Dismiss whatever real modal dialog is currently blocking the GUI thread, if any.

    `offline_app_data_root` disables every provider so the fixture never dials a real
    network endpoint (see that fixture's docstring) -- but a fully offline application with
    zero enabled providers is genuinely `NOT_READY` (`08_Cross_Cutting/08-M_app_lifecycle.md`
    §5), and production surfaces that state with a blocking `QMessageBox.critical(...)`
    modal the first time the deferred, `QTimer.singleShot(0, ...)`-scheduled startup
    readiness tick computes it (`main_window_shown_readiness_probe_scheduled` ->
    `QtNotificationService._show_modal` -> `.exec()`). That 0ms timer is armed the moment
    `window.show()` fires its `showEvent`, but stays *pending*, undelivered, until something
    next pumps the Qt event loop -- observed empirically to be `qtbot.wait` below, called
    from this same `shutdown_handle` fixture, well after `window.close()` has already run.
    Left undismissed, `.exec()`'s nested loop never returns and the smoke test hangs forever
    (confirmed by a standalone repro with no dismiss timer: the process is still blocked
    inside `_show_modal` on a `dump_traceback_later` dump after a 25-second wait).

    Mirrors `tests/integration/test_menu_opens_dialogs.py`'s `_dismiss_and_clear_modal_stack`
    -- restoring `WA_ShowModal` before hiding is what makes Qt run `leaveModal` and pop the
    dialog off `QApplication.activeModalWidget()`'s stack, rather than leaving a stale entry
    a later test's own modal-widget lookup could pick up by mistake. This targets whichever
    modal is on top generically (via `QApplication.activeModalWidget()`) rather than a
    captured dialog instance, because `QMessageBox.critical(...)` is a static convenience
    call that never hands the caller a reference to construct one.
    """
    modal = QApplication.activeModalWidget()
    if modal is None:
        return
    modal.setAttribute(Qt.WidgetAttribute.WA_ShowModal, on=True)
    modal.hide()
    modal.setAttribute(Qt.WidgetAttribute.WA_ShowModal, on=False)
