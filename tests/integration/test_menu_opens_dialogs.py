"""Integration tests proving the menu-bar Settings and About actions open their real modal
dialogs (STORY-083-AC-3, STORY-083-AC-4).

Neither dialog is stubbed to a `.exec()`-returns-instantly double -- that is the whole point.
`ollama_llm_bench.compose.make_settings_dialog` / `make_about_dialog` are patched only to take a
typed reference to the dialog the *real* factory builds; the call is forwarded unchanged. A
`QTimer.singleShot` inspects the live modal and closes it so the nested `.exec()` returns. If
the wiring regresses, these tests hang instead of quietly passing -- which is exactly the
failure mode the existing STORY-077-AC-8 test (both dialogs mocked) cannot detect.
"""

from collections.abc import Callable
from typing import cast

from PySide6.QtCore import Qt, QTimer
from PySide6.QtWidgets import QDialog, QPushButton
from pytest_mock import MockerFixture
from pytestqt.qtbot import QtBot

from ollama_llm_bench.compose import AppHandle
from ollama_llm_bench.ui.common_dialogs import make_about_dialog as _real_make_about_dialog
from ollama_llm_bench.ui.settings_dialog import make_settings_dialog as _real_make_settings_dialog

_DISMISS_DELAY_MS = 50


def test_settings_action_opens_settings_dialog(
    build_real_app: Callable[[], AppHandle], qtbot: QtBot, mocker: MockerFixture
) -> None:
    """Proves: STORY-083-AC-3

    Given the main window is shown, when the user activates the menu-bar Settings action, then
    the real Settings modal dialog opens (`01_Main_Window` §3.1).
    """
    # Arrange
    captured: list[QDialog] = []
    observed: dict[str, bool] = {}

    def _capture(**kwargs: object) -> QDialog:
        dialog = _real_make_settings_dialog(**kwargs)  # type: ignore[arg-type]  # forwarding real compose kwargs
        captured.append(dialog)
        return dialog

    mocker.patch("ollama_llm_bench.compose.make_settings_dialog", side_effect=_capture)
    handle = build_real_app()
    qtbot.addWidget(handle.window)
    settings_button = cast("QPushButton", handle.window.findChild(QPushButton, "settings_action"))
    assert settings_button is not None
    assert settings_button.isEnabled()

    def _inspect_and_dismiss() -> None:
        dialog = captured[0]
        observed["visible"] = dialog.isVisible()
        observed["modal"] = dialog.isModal()
        dialog.close()

    # Act -- blocks inside the dialog's nested exec() until the timer dismisses it
    QTimer.singleShot(_DISMISS_DELAY_MS, _inspect_and_dismiss)
    qtbot.mouseClick(  # type: ignore[no-untyped-call]  # pytest-qt provides no type stubs
        settings_button, Qt.MouseButton.LeftButton
    )

    # Assert
    assert observed == {"visible": True, "modal": True}


def test_about_action_opens_about_dialog(
    build_real_app: Callable[[], AppHandle], qtbot: QtBot, mocker: MockerFixture
) -> None:
    """Proves: STORY-083-AC-4

    Given the main window is shown, when the user activates the menu-bar About action, then the
    real Application Information modal dialog opens (`01_Main_Window` §3.2).
    """
    # Arrange
    captured: list[QDialog] = []
    observed: dict[str, bool] = {}

    def _capture(**kwargs: object) -> QDialog:
        dialog = _real_make_about_dialog(**kwargs)  # type: ignore[arg-type]  # forwarding real compose kwargs
        captured.append(dialog)
        return dialog

    mocker.patch("ollama_llm_bench.compose.make_about_dialog", side_effect=_capture)
    handle = build_real_app()
    qtbot.addWidget(handle.window)
    about_button = cast("QPushButton", handle.window.findChild(QPushButton, "about_action"))
    assert about_button is not None

    def _inspect_and_dismiss() -> None:
        dialog = captured[0]
        observed["visible"] = dialog.isVisible()
        observed["modal"] = dialog.isModal()
        dialog.close()

    # Act -- blocks inside the dialog's nested exec() until the timer dismisses it
    QTimer.singleShot(_DISMISS_DELAY_MS, _inspect_and_dismiss)
    qtbot.mouseClick(  # type: ignore[no-untyped-call]  # pytest-qt provides no type stubs
        about_button, Qt.MouseButton.LeftButton
    )

    # Assert
    assert observed == {"visible": True, "modal": True}
