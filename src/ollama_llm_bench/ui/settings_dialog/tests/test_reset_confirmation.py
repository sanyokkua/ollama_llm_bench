"""Proves: STORY-067-AC-5

Confirms the Reset-confirmation sub-dialog states the consequences and that
Cancel vs Reset set `.confirmed` correctly.
"""

from PySide6.QtCore import Qt
from pytestqt.qtbot import QtBot

from ollama_llm_bench.ui.settings_dialog._internal.sub_dialogs.reset_confirmation_select import (
    RESET_CONFIRMATION_BODY_TEXT,
)
from ollama_llm_bench.ui.settings_dialog._internal.sub_dialogs.reset_confirmation_view import (
    make_reset_confirmation_dialog,
)


def test_reset_button_sets_confirmed_true(qtbot: QtBot) -> None:
    dialog = make_reset_confirmation_dialog()
    qtbot.addWidget(dialog)

    qtbot.mouseClick(  # type: ignore[no-untyped-call]  # pytest-qt provides no type stubs
        dialog.reset_button, Qt.MouseButton.LeftButton
    )

    assert dialog.confirmed is True


def test_cancel_button_sets_confirmed_false(qtbot: QtBot) -> None:
    dialog = make_reset_confirmation_dialog()
    qtbot.addWidget(dialog)

    qtbot.mouseClick(  # type: ignore[no-untyped-call]  # pytest-qt provides no type stubs
        dialog.cancel_button, Qt.MouseButton.LeftButton
    )

    assert dialog.confirmed is False


def test_body_text_mentions_bundled_providers_and_preserved_runs() -> None:
    assert "Ollama" in RESET_CONFIRMATION_BODY_TEXT
    assert "LM Studio" in RESET_CONFIRMATION_BODY_TEXT
    assert "llama.cpp" in RESET_CONFIRMATION_BODY_TEXT
    lowered = RESET_CONFIRMATION_BODY_TEXT.lower()
    assert "not affected" in lowered or "not be affected" in lowered
