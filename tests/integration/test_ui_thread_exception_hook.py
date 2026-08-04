"""Integration test for `__main__`'s UI-thread top-level exception hook (STORY-076).

Exercises `_handle_ui_thread_exception` against a *real* composed `AppHandle` (real
`QApplication`, real SQLite write connection, real schema, real seeded providers) --
the same shape `tests/integration/test_compose_build_app.py` builds -- so the assertion
that the database is genuinely closed afterward is meaningful, not a mock assertion.

Source of truth: `docs/v3_specification/08_Cross_Cutting/08-M_app_lifecycle.md` §8
(crash policy) and `#EC-M-8`.
"""

from collections.abc import Generator
import json
from pathlib import Path
import sys
import threading
import time
from typing import TYPE_CHECKING, cast

import icontract.errors
from PySide6.QtCore import QEventLoop, Qt, QTimer
from PySide6.QtWidgets import QApplication
import pytest
from pytest_mock import MockerFixture
from pytestqt.qtbot import QtBot

from ollama_llm_bench.__main__ import (
    _SHUTDOWN_TIMEOUT_MS,
    _AppHandleHolder,
    _CrashDialogCollaborators,
    _handle_ui_thread_exception,
    main,
)
from ollama_llm_bench.adapters.clipboard import Clipboard
from ollama_llm_bench.backend.errors import ContractViolationError
from ollama_llm_bench.backend.events import EventBus
from ollama_llm_bench.backend.infra import app_log_path, configure_logging, make_system_clock
from ollama_llm_bench.backend.persistence.app_settings import (
    DB_FILENAME,
    ensure_schema,
    open_write_connection,
)
from ollama_llm_bench.backend.persistence.providers import seed_builtin_providers
from ollama_llm_bench.backend.platform import create_app_data_dir, make_platform_detector
from ollama_llm_bench.compose import AppHandle, build_app
from ollama_llm_bench.ui.common_dialogs import make_error_dialog as _real_make_error_dialog
from ollama_llm_bench.ui.common_dialogs.models import ErrorDialogPattern, ErrorDialogPayload

if TYPE_CHECKING:
    from ollama_llm_bench.ui.common_dialogs._internal.error_view import ErrorDialog

_DISPATCHER_SHUTDOWN_TIMEOUT_MS = 2000
_QUEUE_DRAIN_WAIT_S = 0.5
_QUIT_CLICK_DELAY_MS = 50
_DIALOG_TEARDOWN_TICK_MS = 10


@pytest.fixture(autouse=True)
def _disconnect_os_color_scheme_signal(qapp: QApplication) -> Generator[None]:
    """See the identical fixture in `test_compose_build_app.py`: `build_app` wires a
    `ThemeManager` connecting `qapp.styleHints().colorSchemeChanged`, which production
    never disconnects; left connected, it leaks into later tests sharing this
    session-scoped `qapp`.
    """
    yield
    qapp.styleHints().colorSchemeChanged.disconnect()
    qapp.styleHints().unsetColorScheme()


@pytest.fixture(autouse=True)
def _restore_global_exception_hooks() -> Generator[None]:
    """See the identical fixture in `test_worker_thread_exception_hook.py`:
    `_install_exception_hooks` mutates the process-global `sys.excepthook` and
    `threading.excepthook`; restore both after the test so this test's closures
    (holding test-local mocks/fixtures) never linger for a later, unrelated test."""
    original_sys_hook = sys.excepthook
    original_threading_hook = threading.excepthook
    yield
    sys.excepthook = original_sys_hook
    threading.excepthook = original_threading_hook


@pytest.fixture(autouse=True)
def _clear_qt_quit_flag(qapp: QApplication) -> Generator[None]:
    """Clear Qt's per-thread "quit now" flag after this module's tests run for real.

    See the identical fixture in `test_launch_abort_modal_quits.py` for the full
    mechanism: `QCoreApplication::exit()` sets `QThreadData::quitNow`, and the
    **only** code that ever clears it is `QCoreApplication::exec()` itself. Under
    `pytest` no top-level `app.exec()` is running, so once
    `test_ui_thread_uncaught_exception_logs_shows_modal_and_requests_exit` below lets
    the real quit callback call `QApplication.instance().exit(1)` on this module's
    real, session-scoped `qapp` (the behaviour that test proves), the flag stays set
    for the rest of the session -- every later `QDialog.exec()`/`QEventLoop.exec()`/
    queued-signal-delivering nested loop on the GUI thread then returns immediately
    without running. Measured: with this fixture absent, that one test alone poisons
    unrelated `src/`-colocated Qt tests run later in the same session (e.g.
    `ui/progress/tests/test_log_controller.py`'s queued-signal assertions), even
    though every other test in this file already avoids triggering a real `.exit()`
    on the shared `qapp` (see the `QApplication.instance` patch in
    `test_quit_callback_never_shuts_down_the_handle_itself` above). This teardown
    re-creates the one condition that clears the flag -- a real, bounded `qapp.exec()`
    ended immediately by `qapp.exit(0)` -- after every test in this module, so nothing
    leaks into tests collected afterward.
    """
    yield
    QTimer.singleShot(0, lambda: qapp.exit(0))
    qapp.exec()


@pytest.fixture
def isolated_home(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    """Redirect `Path.home()` into `tmp_path` -- see `test_compose_build_app.py`'s
    module docstring for why this is required beyond the root `_isolate_filesystem`
    fixture on every host platform."""
    home = tmp_path / "home"
    home.mkdir()
    monkeypatch.setenv("HOME", str(home))
    monkeypatch.setenv("USERPROFILE", str(home))
    return home


@pytest.fixture
def seeded_app_data_root(isolated_home: Path) -> Path:
    """Pre-create the schema and one enabled builtin provider at the exact
    `<app-data>` path `build_app` itself will resolve and open."""
    profile = make_platform_detector().detect()
    app_data_root = create_app_data_dir(profile.app_data_root)
    write_conn, lock = open_write_connection(app_data_root / DB_FILENAME)
    ensure_schema(write_conn, lock, clock=make_system_clock())
    seed_builtin_providers(write_conn, lock)
    write_conn.close()
    return app_data_root


def _read_app_log_lines(app_log_file: Path) -> list[dict[str, object]]:
    """Read and JSON-decode every record currently written to `app.log`."""
    if not app_log_file.exists():
        return []
    lines = [line for line in app_log_file.read_text(encoding="utf-8").splitlines() if line]
    return [json.loads(line) for line in lines]


def test_ui_thread_uncaught_exception_logs_shows_modal_and_requests_exit(
    seeded_app_data_root: Path, qapp: QApplication, qtbot: QtBot, mocker: MockerFixture
) -> None:
    """Proves: STORY-076-AC-1

    Given a real, composed `AppHandle` backing a live SQLite write connection (the
    application is running), when an uncaught exception reaches the UI thread, then
    the top-level hook logs it to `app.log`, shows a blocking FATAL-pattern modal
    error dialog, and -- once the user clicks its Quit button -- requests the
    application to exit (EC-M-8).

    The hook's quit callback deliberately does **not** close the database itself
    (STORY-080's final-review fix): `main()`'s own post-`app.exec()` tail is the
    single shutdown call site for both a normal quit and this crash path, proven by
    `test_main_runs_ordered_shutdown_exactly_once_after_app_exec_then_exits_with_its_code`
    below. This test proves the logging/dialog/exit-request contract only; it shuts
    the handle down itself afterward purely for test hygiene (there is no `main()`
    tail running here to do it).
    """
    # Arrange
    profile = make_platform_detector().detect()
    app_log_file = app_log_path(profile)
    configure_logging(app_log_file=app_log_file)
    handle = build_app(app=qapp, loop=QEventLoop())
    # Close the window and stop the dispatcher up front, exactly like the existing
    # `test_app_handle_shutdown_closes_http_client_and_write_connection` Arrange --
    # the hook under test never touches either, and leaving them live would leak a
    # thread/widget into later tests for no assertion this test makes.
    handle.window.close()
    handle.run_dispatcher.shutdown(timeout_ms=_DISPATCHER_SHUTDOWN_TIMEOUT_MS)
    handle_holder = _AppHandleHolder()
    handle_holder.set_handle(handle)
    clipboard = mocker.Mock(spec=Clipboard)
    event_bus = mocker.Mock(spec=EventBus)
    collaborators = _CrashDialogCollaborators(
        clipboard=clipboard, event_bus=event_bus, handle_holder=handle_holder
    )
    try:
        raise ValueError("synthetic ui-thread boom")
    except ValueError as exc:
        exc_type, exc_value, exc_tb = type(exc), exc, exc.__traceback__

    captured_payloads: list[ErrorDialogPayload] = []
    captured_dialogs: list[ErrorDialog] = []

    def _capture_dialog(
        *, payload: ErrorDialogPayload, clipboard: Clipboard, event_bus: EventBus
    ) -> "ErrorDialog":
        captured_payloads.append(payload)
        dialog = cast(
            "ErrorDialog",
            _real_make_error_dialog(payload=payload, clipboard=clipboard, event_bus=event_bus),
        )
        captured_dialogs.append(dialog)
        return dialog

    mocker.patch("ollama_llm_bench.__main__.make_error_dialog", side_effect=_capture_dialog)

    def _click_quit() -> None:
        qtbot.mouseClick(  # type: ignore[no-untyped-call]  # pytest-qt provides no type stubs
            captured_dialogs[0].quit_button, Qt.MouseButton.LeftButton
        )

    # Click the modal's Quit button once the blocking `.exec()` starts running --
    # `QApplication.exit()` (invoked by the quit callback) interrupts every active
    # event loop on this thread, including the dialog's nested one, so `.exec()`
    # returns instead of hanging the test.
    QTimer.singleShot(_QUIT_CLICK_DELAY_MS, _click_quit)

    # Act
    _handle_ui_thread_exception(exc_type, exc_value, exc_tb, collaborators=collaborators)
    time.sleep(_QUEUE_DRAIN_WAIT_S)

    # Assert -- the dialog shown was the FATAL pattern with a real quit callback.
    assert len(captured_payloads) == 1
    assert captured_payloads[0].pattern is ErrorDialogPattern.FATAL
    assert captured_payloads[0].quit_callback is not None

    # Assert -- an app.log record exists for the exception.
    app_records = _read_app_log_lines(app_log_file)
    matching = [r for r in app_records if r.get("event") == "uncaught_ui_thread_exception"]
    assert len(matching) == 1
    assert matching[0]["level"] == "error"
    assert matching[0]["exc_type"] == "ValueError"

    # Assert -- the quit callback did not close the database or the HTTP client
    # itself; only `main()`'s own tail does that now (regression guard for the
    # double-shutdown crash this session's final review found).
    assert not handle.http_client.is_closed
    handle.write_conn.execute("SELECT 1")

    # Cleanup -- hide the real dialog and let the resulting layout work run here, inside
    # this test. `QApplication.exit(1)` unwinds `.exec()`'s nested loop without ever going
    # through `QDialog::done()`, so unlike a normal dismissal it leaves the dialog *shown*
    # with layout work still queued. Under the offscreen platform plugin that queued work
    # logs "This plugin does not support propagateSizeHints()" whenever it is finally
    # processed -- and `pytest-qt` processes it in the *next* test's `pytest_runtest_setup`,
    # where the root `_qt_parity_rig` fixture fails a test that did nothing wrong (measured:
    # it landed on `test_quit_callback_never_shuts_down_the_handle_itself` below). Draining
    # it here keeps the warning inside the test that caused it.
    captured_dialogs[0].hide()
    qtbot.wait(_DIALOG_TEARDOWN_TICK_MS)

    # Cleanup -- no `main()` tail runs in this test to close the handle's resources.
    handle.shutdown(timeout_ms=_DISPATCHER_SHUTDOWN_TIMEOUT_MS)


def test_quit_callback_never_shuts_down_the_handle_itself(
    tmp_path: Path, mocker: MockerFixture
) -> None:
    """Given an uncaught user-interface-thread exception, when the fatal dialog's Quit
    button callback runs, then it only requests the Qt application exit
    (`QApplication.instance().exit(1)`) and never calls `AppHandle.shutdown()` itself.

    Regression guard for a final-review Critical finding on STORY-080: the quit
    callback used to also call `handle.shutdown(timeout_ms=...)` directly, so
    `main()`'s own unconditional post-`app.exec()` tail (which also calls
    `handle.shutdown()`, exactly once, with the same configured timeout budget --
    see `test_main_runs_ordered_shutdown_exactly_once_after_app_exec_then_exits_with_its_code`
    below for that proof) ran it a *second* time on an already-closed write
    connection, raising an unhandled `sqlite3.ProgrammingError` instead of exiting
    cleanly. The normal quit and this crash path must share the single shutdown call
    site in `main()`'s tail, per this story's Design constraints.
    """
    # Arrange
    app_log_file = tmp_path / "logs" / "app" / "app.log"
    configure_logging(app_log_file=app_log_file)
    mock_handle = mocker.Mock(spec=AppHandle)
    handle_holder = _AppHandleHolder()
    handle_holder.set_handle(mock_handle)
    clipboard = mocker.Mock(spec=Clipboard)
    event_bus = mocker.Mock(spec=EventBus)
    collaborators = _CrashDialogCollaborators(
        clipboard=clipboard, event_bus=event_bus, handle_holder=handle_holder
    )
    captured_payloads: list[ErrorDialogPayload] = []
    stub_dialog = mocker.Mock(spec=["exec"])

    def _capture_payload(
        *, payload: ErrorDialogPayload, clipboard: Clipboard, event_bus: EventBus
    ) -> object:
        captured_payloads.append(payload)
        return stub_dialog

    mocker.patch("ollama_llm_bench.__main__.make_error_dialog", side_effect=_capture_payload)
    # `_quit()` also calls `QApplication.instance().exit(1)` -- with no real nested
    # event loop running here (`stub_dialog.exec` is a `Mock`, not a real blocking
    # call), calling `.exit()` on the real, session-scoped `qapp` would permanently
    # set Qt's internal "quit now" flag: every later `QDialog.exec()`/`QEventLoop.exec()`
    # for the rest of the test session (e.g. the real-`AppHandle` test above, which
    # relies on its own nested `dialog.exec()` staying alive long enough for its
    # `QTimer.singleShot` Quit-button click to fire) would then return immediately
    # instead of running. Making `QApplication.instance()` return `None` here keeps
    # this test inside `_quit()`'s own existing `if instance is not None` guard and
    # never touches the real, shared `qapp` at all.
    mocker.patch("ollama_llm_bench.__main__.QApplication.instance", return_value=None)
    try:
        raise ValueError("synthetic ui-thread boom")
    except ValueError as exc:
        exc_type, exc_value, exc_tb = type(exc), exc, exc.__traceback__

    # Act
    _handle_ui_thread_exception(exc_type, exc_value, exc_tb, collaborators=collaborators)
    assert captured_payloads[0].quit_callback is not None
    captured_payloads[0].quit_callback()

    # Assert -- the quit callback never touches the handle; `main()`'s tail is the
    # sole shutdown call site (see the `main()`-exercising test below).
    mock_handle.shutdown.assert_not_called()


@pytest.mark.parametrize(
    "programmer_exception",
    [
        ContractViolationError(message="synthetic invariant violation"),
        icontract.errors.ViolationError("synthetic contract violation"),
    ],
    ids=["backend_programmer_error", "icontract_violation_error"],
)
def test_ui_thread_uncaught_programmer_error_logs_critical(
    programmer_exception: BaseException, tmp_path: Path, mocker: MockerFixture
) -> None:
    """Proves: STORY-076-AC-1

    Given the same top-level user-interface-thread hook AC-1 exercises above with a
    plain `ValueError` (logged at ERROR), when the uncaught exception is instead
    this codebase's own `ProgrammerError` (`ContractViolationError`) or `icontract`'s
    own `ViolationError` -- a distinct hierarchy raised when an `@icontract.require`/
    `@icontract.ensure` contract is violated -- then the hook logs it at CRITICAL,
    not ERROR, matching the crash policy's "never caught, crashes the process"
    treatment of both.
    """
    # Arrange
    app_log_file = tmp_path / "logs" / "app" / "app.log"
    configure_logging(app_log_file=app_log_file)
    handle_holder = _AppHandleHolder()
    clipboard = mocker.Mock(spec=Clipboard)
    event_bus = mocker.Mock(spec=EventBus)
    collaborators = _CrashDialogCollaborators(
        clipboard=clipboard, event_bus=event_bus, handle_holder=handle_holder
    )
    stub_dialog = mocker.Mock(spec=["exec"])
    mocker.patch("ollama_llm_bench.__main__.make_error_dialog", return_value=stub_dialog)
    exc_type, exc_value, exc_tb = type(programmer_exception), programmer_exception, None

    # Act
    _handle_ui_thread_exception(exc_type, exc_value, exc_tb, collaborators=collaborators)
    time.sleep(_QUEUE_DRAIN_WAIT_S)

    # Assert -- the app.log record for this exception was logged at CRITICAL.
    app_records = _read_app_log_lines(app_log_file)
    matching = [r for r in app_records if r.get("event") == "uncaught_ui_thread_exception"]
    assert len(matching) == 1
    assert matching[0]["level"] == "critical"
    stub_dialog.exec.assert_called_once()


def test_ui_thread_second_exception_during_modal_does_not_show_second_dialog(
    tmp_path: Path, mocker: MockerFixture
) -> None:
    """Proves: STORY-076-AC-1

    Given the fatal dialog's re-entrancy guard is already marking a fatal dialog as
    showing (simulating a second uncaught exception arriving while the first fatal
    dialog's nested `.exec()` event loop is still running), when the hook is invoked
    again, then it still logs the second exception but never constructs a second
    dialog (`07_Common_Dialogs/error_dialog.md` EC-ERR-3: two Error dialogs are
    never visible at once).
    """
    # Arrange
    app_log_file = tmp_path / "logs" / "app" / "app.log"
    configure_logging(app_log_file=app_log_file)
    handle_holder = _AppHandleHolder()
    clipboard = mocker.Mock(spec=Clipboard)
    event_bus = mocker.Mock(spec=EventBus)
    collaborators = _CrashDialogCollaborators(
        clipboard=clipboard, event_bus=event_bus, handle_holder=handle_holder
    )
    collaborators.dialog_guard.begin()
    make_error_dialog_spy = mocker.patch("ollama_llm_bench.__main__.make_error_dialog")
    try:
        raise ValueError("synthetic second ui-thread boom")
    except ValueError as exc:
        exc_type, exc_value, exc_tb = type(exc), exc, exc.__traceback__

    # Act
    _handle_ui_thread_exception(exc_type, exc_value, exc_tb, collaborators=collaborators)
    time.sleep(_QUEUE_DRAIN_WAIT_S)

    # Assert -- no second dialog was constructed.
    make_error_dialog_spy.assert_not_called()

    # Assert -- the second exception was still logged.
    app_records = _read_app_log_lines(app_log_file)
    matching = [r for r in app_records if r.get("event") == "uncaught_ui_thread_exception"]
    assert len(matching) == 1
    assert matching[0]["level"] == "error"


def test_main_runs_ordered_shutdown_exactly_once_after_app_exec_then_exits_with_its_code(
    isolated_home: Path, qapp: QApplication, mocker: MockerFixture
) -> None:
    """Proves: STORY-080-AC-6

    Given the application is running, when `main()`'s blocking `app.exec()` call
    returns (a normal quit or a crash-triggered `QApplication.exit(1)` -- this test
    does not care which), then `main()`'s own tail runs the ordered shutdown exactly
    once, calling `AppHandle.shutdown(timeout_ms=...)` with the application's
    configured shutdown-timeout budget strictly after `app.exec()` returns and
    strictly before the process exit, and the process then exits with `app.exec()`'s
    own returned exit code -- not a hardcoded value, and never silently swallowed.

    No existing test called `main()` itself before this one: every other AC-6 test
    exercises `AppHandle.shutdown()` directly. That gap is exactly what let a
    final-review Critical finding on STORY-080 ship unnoticed -- the fatal-dialog
    crash hook used to *also* call `handle.shutdown()` from its own quit callback,
    so this same tail ran `shutdown()` a second time on an already-closed write
    connection and crashed with `sqlite3.ProgrammingError` instead of exiting
    cleanly (see `test_quit_callback_never_shuts_down_the_handle_itself` above for
    that regression guard). `QApplication` and `build_app` are both faked, so this
    test needs no real Qt event loop and never touches the database.
    """
    # Arrange
    call_order: list[str] = []
    exit_code = 7

    mock_handle = mocker.Mock(spec=AppHandle)

    def _record_shutdown(*, timeout_ms: int) -> None:
        call_order.append(f"handle_shutdown:{timeout_ms}")

    mock_handle.shutdown.side_effect = _record_shutdown
    mocker.patch("ollama_llm_bench.__main__.build_app", return_value=mock_handle)

    mock_qapplication_cls = mocker.patch("ollama_llm_bench.__main__.QApplication")
    mock_app = mock_qapplication_cls.return_value

    def _record_exec() -> int:
        call_order.append("app_exec")
        return exit_code

    mock_app.exec.side_effect = _record_exec

    # Act -- catch the real `SystemExit` rather than mocking `sys.exit`, mirroring
    # `test_launch_abort_modal_quits.py`'s established pattern for proving a "did the
    # process actually try to exit, and with what code" claim.
    with pytest.raises(SystemExit) as exc_info:
        main(argv=[])

    # Assert -- `app.exec()` ran, then the handle was shut down with the configured
    # timeout budget exactly once, strictly after `app.exec()` returned.
    assert call_order == ["app_exec", f"handle_shutdown:{_SHUTDOWN_TIMEOUT_MS}"]
    mock_handle.shutdown.assert_called_once_with(timeout_ms=_SHUTDOWN_TIMEOUT_MS)

    # Assert -- the process exit used `app.exec()`'s own returned code.
    assert exc_info.value.code == exit_code
