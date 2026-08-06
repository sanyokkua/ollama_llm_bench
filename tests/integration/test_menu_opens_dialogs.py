"""Integration tests proving the menu-bar Settings and About actions open their real modal
dialogs (STORY-083-AC-3, STORY-083-AC-4).

Neither dialog is stubbed to a `.exec()`-returns-instantly double -- that is the whole point.
`ollama_llm_bench.compose.make_settings_dialog` / `make_about_dialog` are patched only to take a
typed reference to the dialog the *real* factory builds; the call is forwarded unchanged, and the
real `.exec()` in `compose.py` runs. If the wiring regresses (e.g. the menu action no longer
reaches the real factory), these tests fail with an `AssertionError` comparing the observed
`{"visible": ..., "modal": ...}` dict against the expected one -- not a hang -- which is a clean
regression signal the existing STORY-077-AC-8 test (both dialogs mocked, `.exec` never really
called) cannot give. Neither production dialog calls `setModal`/`setWindowModality` itself, so
`isModal()` being true is specifically evidence that `compose.py` opened it with `.exec()`; a
regression to a modeless `.show()` would fail these tests.

**Where the observation is taken, and why it is not a timer.** A `QShowEvent` filter installed on
the captured dialog records `isVisible()`/`isModal()` at the instant `.exec()` shows it --
synchronously, inside the `.exec()` call, before any event loop is involved. The `QTimer` below
exists only to *dismiss* the dialog so a blocking `.exec()` returns; nothing is asserted from it.

That split matters because whether `.exec()` blocks at all must not be a property of these
tests. Qt keeps a per-thread "quit now" flag that `QCoreApplication::exit()` sets and only
`QCoreApplication::exec()` clears; while it is set, every `QDialog.exec()` on the GUI thread
returns immediately without entering its nested loop, so a dialog's dismissal timer never fires
and the dialog is left shown. `tests/integration/test_launch_abort_modal_quits.py` sets that
flag for real -- its production handler calls `QApplication.exit(1)`, which is the behaviour
that file exists to prove -- and it now clears the flag again in its own teardown, so the
contamination no longer escapes into the rest of the session (see that file's
`_clear_qt_quit_flag` fixture). Reading these tests' observation from the show event rather
than from the dismissal timer predates that fix and is kept regardless: it is what makes the
result independent of collection order and of whether any other test leaves a nested loop
unrunnable, instead of something these two tests have to trust another file to maintain.

**Why the dialog is dismissed through `_dismiss_and_clear_modal_stack` rather than `close()`.**
See that helper's docstring. With the quit flag clear, `.exec()` blocks and cleans up its own
modal state on the way out, so the helper is a plain hide; the extra `WA_ShowModal` handling is
what keeps it correct in the early-return case too, where a plain `close()` would leave the
dialog on Qt's modal-widget stack permanently and corrupt a later, unrelated test badly enough
to abort the whole pytest process.

**Why these two build the application with every provider disabled.** Both tests use
`build_real_app_without_enabled_providers` rather than the seeded `build_real_app`. The seeded
fixture installs the three builtin providers *enabled*, two of which point at real local endpoints
(`http://localhost:11434`, `http://localhost:1234`). Opening the real Settings dialog runs the
embedding section's first-start bootstrap search over every **enabled** provider
(`ui/settings_dialog/_internal/providers_tab/embedding_section.py` `_bootstrap_search_next`),
which submits a real `discover_models` network call per provider to the application's real
`QThreadPool` and delivers each result back over a queued connection. Against the seeded providers
those calls really do hit the developer's machine: on a host running Ollama or LM Studio they
connect, take real time, and can leave work in flight past the end of the test; on an offline
runner they fail fast. A test whose timing depends on which servers the developer happens to have
running is non-deterministic by construction, so these two remove the dependency at its source --
with every provider disabled the bootstrap's `enabled_providers` tuple is empty and it returns
without submitting anything, and these tests touch no socket at all.

Nothing about what these tests prove depends on an *enabled* provider existing -- AC-3 and AC-4
are about the menu-bar actions reaching the real dialog factories and the resulting dialog being
visible and modal. "Every provider disabled" is a configuration any user can reach by unticking
all three in the Settings dialog, and one `build_app` supports as a first-class case -- proven
independently by `test_compose_build_app.py::test_build_app_survives_zero_enabled_providers`.
"""

from collections.abc import Callable
from typing import cast

from PySide6.QtCore import QEvent, QObject, Qt, QTimer
from PySide6.QtWidgets import QDialog, QPushButton
import pytest
from pytest_mock import MockerFixture
from pytestqt.qtbot import QtBot

from ollama_llm_bench.compose import AppHandle
from ollama_llm_bench.ui.common_dialogs import make_about_dialog as _real_make_about_dialog
from ollama_llm_bench.ui.settings_dialog import make_settings_dialog as _real_make_settings_dialog

_DISMISS_DELAY_MS = 50


class _RecordVisibilityOnShow(QObject):
    """Event filter recording a widget's `isVisible()`/`isModal()` the first time it is shown.

    `QDialog.exec()` shows the dialog synchronously, from inside the `.exec()` call, before it
    enters its nested event loop -- so this filter runs at exactly the moment production opens
    the dialog, whether or not that nested loop then actually runs. `into` is the dict the test
    asserts on; it stays empty if the dialog is never shown, which is the regression signal.
    """

    def __init__(self, into: dict[str, bool]) -> None:
        super().__init__()
        self._into = into

    def eventFilter(self, watched: QObject, event: QEvent) -> bool:
        if event.type() == QEvent.Type.Show and not self._into:
            widget = cast("QDialog", watched)
            self._into["visible"] = widget.isVisible()
            self._into["modal"] = widget.isModal()
        return False


def _dismiss_and_clear_modal_stack(dialog: QDialog) -> None:
    """Hide `dialog` in a way that always removes it from Qt's modal-widget stack.

    `QDialog.exec()` saves the dialog's `WA_ShowModal` attribute, sets it, shows the dialog
    (which is what pushes it onto the application's modal-widget stack, via Qt's internal
    `enterModal`), runs its nested loop, and on the way out restores the saved attribute and
    hides the dialog -- the hide being what pops the stack again, via `leaveModal`.

    When that nested loop returns immediately -- which happens in any session where Qt's
    per-thread "quit now" flag has been left set (see the module docstring) -- `.exec()` still
    restores `WA_ShowModal` to false but leaves the dialog *shown*. A later
    `close()`/`hide()`/`reject()`
    then does **not** pop the stack, because as far as Qt is concerned the widget is no longer a
    modal one. Verified directly against Qt: after such an `.exec()`,
    `QApplication.activeModalWidget()` keeps returning that dialog through `close()`, `hide()`,
    `done()`, `reject()`, `setModal(False)` and even `deleteLater()` -- ultimately as a dangling
    pointer to a destroyed C++ object.

    That is not a cosmetic leak. `test_new_benchmark_start.py` reads
    `QApplication.activeModalWidget()` from a timer to find its own Run Summary dialog. With a
    stale entry left on the stack it finds the wrong dialog, `findChild(...)` for the button it
    wants returns `None`, and `qtbot.mouseClick(None, ...)` trips `QTEST_ASSERT` inside Qt --
    `ASSERT: "window" in qtestmouse.h` -- which calls `abort()`. That is a `Fatal Python error:
    Aborted` (exit 134) that kills the whole pytest process, in a file that did nothing wrong.

    Restoring `WA_ShowModal` before hiding makes Qt run `leaveModal` and leaves the stack empty.
    Verified against Qt both ways: with the plain `close()` the stack keeps the entry, with this
    helper `QApplication.activeModalWidget()` is back to `None`. `hide()` on an already-hidden
    dialog (the normal case, where `.exec()` did block and cleaned up after itself) returns
    early inside Qt without touching the stack, so this is safe to call unconditionally.
    """
    dialog.setAttribute(Qt.WidgetAttribute.WA_ShowModal, on=True)
    dialog.hide()
    dialog.setAttribute(Qt.WidgetAttribute.WA_ShowModal, on=False)


@pytest.mark.allow_qt_warnings  # offscreen-only: opening either real dialog resizes a
# widget before the offscreen platform plugin has a native window to hint, which logs
# "This plugin does not support propagateSizeHints()" -- pre-existing offscreen-plugin
# behaviour (also hit by test_launch_abort_modal_quits.py's real-dialog `.exec()`), not a
# defect in this test or the production dialog wiring.
def test_settings_action_opens_settings_dialog(
    build_real_app_without_enabled_providers: Callable[[], AppHandle],
    qtbot: QtBot,
    mocker: MockerFixture,
    drain_task_runner_deliveries: Callable[[AppHandle], None],
) -> None:
    """Proves: STORY-083-AC-3

    Given the main window is shown, when the user activates the menu-bar Settings action, then
    the real Settings modal dialog opens (`01_Main_Window` §3.1).
    """
    # Arrange
    captured: list[QDialog] = []
    observed: dict[str, bool] = {}
    show_filter = _RecordVisibilityOnShow(observed)

    def _capture(**kwargs: object) -> QDialog:
        dialog = _real_make_settings_dialog(**kwargs)  # type: ignore[arg-type]  # forwarding real compose kwargs
        dialog.installEventFilter(show_filter)
        captured.append(dialog)
        return dialog

    mocker.patch("ollama_llm_bench.compose.make_settings_dialog", side_effect=_capture)
    handle = build_real_app_without_enabled_providers()
    qtbot.addWidget(handle.window)
    settings_button = cast(
        "QPushButton", handle.window.findChild(QPushButton, "settings_menu_button")
    )
    assert settings_button is not None
    assert settings_button.isEnabled()

    # Act -- blocks inside the dialog's nested exec() until the timer dismisses it
    QTimer.singleShot(_DISMISS_DELAY_MS, lambda: _dismiss_and_clear_modal_stack(captured[0]))
    qtbot.mouseClick(  # type: ignore[no-untyped-call]  # pytest-qt provides no type stubs
        settings_button, Qt.MouseButton.LeftButton
    )

    # Assert
    assert observed == {"visible": True, "modal": True}

    # Cleanup -- unconditional, and a no-op when the timer above already ran; see
    # `_dismiss_and_clear_modal_stack` for why leaving this dialog on Qt's modal-widget
    # stack aborts an unrelated later test's teardown.
    _dismiss_and_clear_modal_stack(captured[0])

    # Cleanup -- belt and braces. With every provider disabled the embedding section's
    # first-start bootstrap search submits nothing (see the module docstring), so there
    # should be nothing left in flight on `handle.task_runner`. This drain stays as the
    # guard for the general case: any *other* real background work the Settings dialog
    # might start would otherwise have its queued completion delivered on a later test's
    # event-loop tick, after this test's widget tree has been torn down, crashing a test
    # that did nothing wrong. Draining here, inside the test body, is the only place that
    # works -- see `drain_task_runner_deliveries`/`_drain_pending_task_runner_deliveries`
    # in `tests/integration/conftest.py` for why a fixture teardown is too late.
    drain_task_runner_deliveries(handle)


@pytest.mark.allow_qt_warnings  # offscreen-only: see the identical marker/comment on
# test_settings_action_opens_settings_dialog above -- same pre-existing offscreen-plugin
# warning, not a defect in this test or the production About dialog wiring.
def test_about_action_opens_about_dialog(
    build_real_app_without_enabled_providers: Callable[[], AppHandle],
    qtbot: QtBot,
    mocker: MockerFixture,
) -> None:
    """Proves: STORY-083-AC-4

    Given the main window is shown, when the user activates the menu-bar About action, then the
    real Application Information modal dialog opens (`01_Main_Window` §3.2).
    """
    # Arrange
    captured: list[QDialog] = []
    observed: dict[str, bool] = {}
    show_filter = _RecordVisibilityOnShow(observed)

    def _capture(**kwargs: object) -> QDialog:
        dialog = _real_make_about_dialog(**kwargs)  # type: ignore[arg-type]  # forwarding real compose kwargs
        dialog.installEventFilter(show_filter)
        captured.append(dialog)
        return dialog

    mocker.patch("ollama_llm_bench.compose.make_about_dialog", side_effect=_capture)
    handle = build_real_app_without_enabled_providers()
    qtbot.addWidget(handle.window)
    about_button = cast("QPushButton", handle.window.findChild(QPushButton, "about_menu_button"))
    assert about_button is not None

    # Act -- blocks inside the dialog's nested exec() until the timer dismisses it
    QTimer.singleShot(_DISMISS_DELAY_MS, lambda: _dismiss_and_clear_modal_stack(captured[0]))
    qtbot.mouseClick(  # type: ignore[no-untyped-call]  # pytest-qt provides no type stubs
        about_button, Qt.MouseButton.LeftButton
    )

    # Assert
    assert observed == {"visible": True, "modal": True}

    # Cleanup -- unconditional, and a no-op when the timer above already ran; see
    # `_dismiss_and_clear_modal_stack` for why leaving this dialog on Qt's modal-widget
    # stack aborts an unrelated later test's teardown.
    _dismiss_and_clear_modal_stack(captured[0])
