"""Regression test proving the `tests/integration/conftest.py` NOT_READY-modal guard covers
a test that builds the real application by calling `compose.build_app` directly, bypassing
both the `build_real_app`/`build_real_app_without_enabled_providers` fixtures.

**The gap this closes.** Eight modules in this directory
(`test_launch_crash_recovery.py`, `test_launch_app_data_dir.py`,
`test_ui_thread_exception_hook.py`, `test_quit_sequence.py`, `test_launch_schema_check.py`,
`test_launch_abort_modal_quits.py`, `test_launch_seeding.py`, `test_launch_instance_lock.py`)
call `build_app` directly rather than through either fixture. Before this fix, only
`_app_handle_factory` (the shared body of `build_real_app`/`build_real_app_without_enabled_
providers`) installed `_DismissReadinessModalOnShow` on `qapp`, so none of those eight modules
had any protection against the real NOT_READY `QMessageBox.critical(...).exec()`
(`08_Cross_Cutting/08-M_app_lifecycle.md` §5). None of them currently call
`handle.window.show()`, which is the only reason none of them hangs today -- the readiness tick
`MainWindowController` arms on the main window's `showEvent` never fires without a real
`show()` call, so the modal never has a chance to open. That is an accident of what those tests
happen to exercise, not a guarantee, and the first test added to any of those modules that shows
its window while running offline would block the GUI thread forever with no `pytest-timeout` to
rescue the run.

This module reproduces exactly that shape -- direct `build_app`, then a real `window.show()`,
against a genuinely offline app-data root (every builtin provider present but disabled, so the
real, unpatched `ReadinessService` computes `NOT_READY` for real, not a NOT_READY produced by a
patched fake) -- so it is the regression test that would have caught the gap: before the
directory-wide `_dismiss_not_ready_modal` autouse fixture existed, this exact test hung (see the
counterfactual evidence recorded in this session's report). With that fixture now installing
`_DismissReadinessModalOnShow` on `qapp` for every test in this directory, this test completes.
"""

from collections.abc import Callable
from pathlib import Path
from typing import cast

from PySide6.QtCore import QEventLoop
from PySide6.QtWidgets import QApplication, QPushButton
import pytest
from pytestqt.qtbot import QtBot

from ollama_llm_bench.compose import AppHandle, build_app

_WAIT_TIMEOUT_MS = 3000


@pytest.mark.allow_qt_warnings  # offscreen-only: the real NOT_READY QMessageBox this test lets
# fire (auto-dismissed by this directory's `_dismiss_not_ready_modal` autouse fixture) resizes a
# widget before the offscreen platform plugin has a native window to hint, which logs "This
# plugin does not support propagateSizeHints()" -- the identical pre-existing offscreen-plugin
# behaviour `test_launch_not_ready_gating.py` and `test_menu_opens_dialogs.py` already carry
# this same marker for, not a defect in this test or the production dialog wiring.
def test_direct_build_app_show_with_no_reachable_provider_does_not_hang(
    isolated_home: Path,  # redirects Path.home() into tmp_path for build_app
    app_data_root_all_providers_disabled: Path,  # makes the built app genuinely NOT_READY
    qapp: QApplication,
    qtbot: QtBot,
    shutdown_handle: Callable[[AppHandle], None],
) -> None:
    """Given the real application is built by calling `build_app` directly -- the same
    bypass shape every `test_launch_*`/`test_quit_sequence.py`/`test_ui_thread_exception_
    hook.py`/`test_launch_abort_modal_quits.py` test uses, never through `build_real_app` or
    `build_real_app_without_enabled_providers` -- against an app-data root whose builtin
    providers are all present but disabled, when the window is shown and the deferred
    readiness tick fires, then the real, unpatched `ReadinessService` resolves `NOT_READY`,
    the production code opens the real blocking `QMessageBox.critical(...).exec()`, this
    directory's directory-wide guard dismisses it, and the test completes instead of hanging
    the GUI thread forever.
    """
    # Arrange / Act
    handle = build_app(app=qapp, loop=QEventLoop())
    qtbot.addWidget(handle.window)
    handle.window.show()
    start_button = cast(
        "QPushButton", handle.window.findChild(QPushButton, "new_benchmark.start_button")
    )
    qtbot.waitUntil(lambda: start_button.isEnabled() is False, timeout=_WAIT_TIMEOUT_MS)

    # Assert -- reaching this line at all proves the modal did not block the GUI thread; the
    # disabled Start button additionally confirms the real (unpatched) probe genuinely
    # resolved NOT_READY rather than the tick simply never having fired.
    assert start_button.isEnabled() is False

    # Cleanup
    shutdown_handle(handle)
