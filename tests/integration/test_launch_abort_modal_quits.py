"""Integration test proving the launch-abort modal's Quit button genuinely stops the
process instead of hanging forever (final-review Critical finding on STORY-078).

Mirrors `tests/integration/test_ui_thread_exception_hook.py`'s already-proven
real-dialog-click pattern: a `QTimer.singleShot` schedules a real `qtbot.mouseClick`
on the dialog's real `quit_button` while `build_app`'s `_abort_launch` call is
blocked inside the dialog's nested `.exec()` event loop. `make_error_dialog` is
never stubbed to a `.exec()`-returns-instantly `mocker.Mock` -- that is the entire
point of this regression test: every other `test_launch_*` abort test uses exactly
that stub, which is why none of them caught the original no-op `quit_callback` bug.
`ollama_llm_bench.compose.make_error_dialog` is patched only to capture a typed
reference to the dialog it constructs -- the call is forwarded to the real,
unmocked factory, so the constructed `ErrorDialog` and its `.exec()` are entirely
real. If the fix regresses, this test hangs/times out instead of completing.
"""

from pathlib import Path
from typing import TYPE_CHECKING, cast

from PySide6.QtCore import QEventLoop, Qt, QTimer
from PySide6.QtWidgets import QApplication
import pytest
from pytest_mock import MockerFixture
from pytestqt.qtbot import QtBot

from ollama_llm_bench.adapters.clipboard import Clipboard
from ollama_llm_bench.backend.errors import ConfigurationError
from ollama_llm_bench.backend.events import EventBus
from ollama_llm_bench.backend.platform import make_platform_detector
from ollama_llm_bench.compose import build_app
from ollama_llm_bench.ui.common_dialogs import make_error_dialog as _real_make_error_dialog
from ollama_llm_bench.ui.common_dialogs.models import ErrorDialogPayload

if TYPE_CHECKING:
    from ollama_llm_bench.ui.common_dialogs._internal.error_view import ErrorDialog

_QUIT_CLICK_DELAY_MS = 50


@pytest.fixture
def isolated_home(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    """Redirect `Path.home()` into `tmp_path` (mirrors the sibling `test_launch_*` files)."""
    home = tmp_path / "home"
    home.mkdir()
    monkeypatch.setenv("HOME", str(home))
    monkeypatch.setenv("USERPROFILE", str(home))
    return home


def test_abort_modal_quit_button_returns_from_exec_and_exits(
    isolated_home: Path,
    qapp: QApplication,
    qtbot: QtBot,
    mocker: MockerFixture,
) -> None:
    """Proves: STORY-078-AC-1

    Given the app-data-creation step aborts launch and shows a real, unmocked
    FATAL error dialog, when the user clicks the dialog's real Quit button, then
    the dialog's nested `.exec()` call genuinely returns and `build_app` reaches
    `sys.exit(1)` -- proving `_abort_launch`'s `quit_callback` actually quits the
    nested Qt event loop instead of the previous no-op that hung every abort path
    forever. The fix lives in the one shared `_abort_launch` helper, so this single
    real-dialog path backstops all four launch-abort paths that call it.
    """
    # Arrange
    app_data_root = make_platform_detector().detect().app_data_root
    permission_error = ConfigurationError(
        message=(
            f"Cannot create the application data directory at '{app_data_root}': Permission denied."
        )
    )
    mocker.patch("ollama_llm_bench.compose.create_app_data_dir", side_effect=permission_error)

    captured_dialogs: list[ErrorDialog] = []

    def _capture_dialog(
        *, payload: ErrorDialogPayload, clipboard: Clipboard, event_bus: EventBus
    ) -> "ErrorDialog":
        dialog = cast(
            "ErrorDialog",
            _real_make_error_dialog(payload=payload, clipboard=clipboard, event_bus=event_bus),
        )
        captured_dialogs.append(dialog)
        return dialog

    mocker.patch("ollama_llm_bench.compose.make_error_dialog", side_effect=_capture_dialog)

    def _click_quit() -> None:
        qtbot.mouseClick(  # type: ignore[no-untyped-call]  # pytest-qt provides no type stubs
            captured_dialogs[0].quit_button, Qt.MouseButton.LeftButton
        )

    # Click the modal's real Quit button once the blocking `.exec()` starts running --
    # `QApplication.instance().exit(1)` (invoked by `_abort_launch`'s quit callback)
    # interrupts every active event loop on this thread, including the dialog's
    # nested one, so `.exec()` returns instead of hanging the test.
    QTimer.singleShot(_QUIT_CLICK_DELAY_MS, _click_quit)

    # Act / Assert -- if `.exec()` never returned, this call would hang instead of
    # raising, and the test would time out rather than complete.
    with pytest.raises(SystemExit) as exc_info:
        build_app(app=qapp, loop=QEventLoop())

    assert exc_info.value.code == 1
    assert len(captured_dialogs) == 1
