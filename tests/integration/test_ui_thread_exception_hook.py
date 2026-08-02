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
import sqlite3
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


def test_ui_thread_uncaught_exception_logs_shows_modal_closes_db_and_exits(
    seeded_app_data_root: Path, qapp: QApplication, qtbot: QtBot, mocker: MockerFixture
) -> None:
    """Proves: STORY-076-AC-1

    Given a real, composed `AppHandle` backing a live SQLite write connection (the
    application is running), when an uncaught exception reaches the UI thread, then
    the top-level hook logs it to `app.log`, shows a blocking FATAL-pattern modal
    error dialog, and -- once the user clicks its Quit button -- closes the database
    cleanly and requests the application to exit (EC-M-8).
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

    # Assert -- the write connection and HTTP client were closed by the quit callback.
    assert handle.http_client.is_closed
    with pytest.raises(sqlite3.ProgrammingError):
        handle.write_conn.execute("SELECT 1")


def test_quit_callback_shuts_down_handle_with_configured_timeout(
    tmp_path: Path, mocker: MockerFixture
) -> None:
    """Proves: STORY-080-AC-6

    Given an uncaught user-interface-thread exception, when the fatal dialog's Quit
    button callback runs, then it shuts the composed `AppHandle` down by calling
    `AppHandle.shutdown(timeout_ms=...)` with the application's configured shutdown
    timeout budget -- the same budget `main()`'s own post-`app.exec()` ordered-shutdown
    call site uses -- not the old no-argument `handle.shutdown()` call.
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

    # Assert -- the quit callback shut the handle down with the configured timeout
    # budget as a keyword argument, not the old no-argument call.
    mock_handle.shutdown.assert_called_once_with(timeout_ms=_SHUTDOWN_TIMEOUT_MS)


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
