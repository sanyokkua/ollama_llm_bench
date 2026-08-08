"""The Task Editor's six confirmation/modal dialogs (STORY-069; ``description.md``
§3.7, §9 EC-TE-07/EC-TE-09/EC-TE-10; ``state_machine.md`` §1/§3).

A bundle of small, plain blocking ``QMessageBox``-builder functions, each returning a
decision -- following ``ui/resume_benchmark/_internal/actions.py``'s and
``ui/main_window/_internal/close_handler.py``'s established inline-``QMessageBox``
pattern. No generic reusable confirm-dialog factory is introduced, per
``ui/progress/_internal/stop_confirmation.py``'s own explicit precedent. Every
three-choice dialog uses explicit ``addButton(..., ButtonRole)`` calls (never the
ambiguous ``.question()`` two-button shortcut), mirroring
``CloseHandler._confirm_unsaved_buffers``.
"""

from PySide6.QtWidgets import QMessageBox

from ollama_llm_bench.backend.yaml_formatter import SaveFailureReason

__all__: list[str] = [
    "confirm_close",
    "confirm_in_use_save",
    "confirm_leave",
    "confirm_quit",
    "confirm_reload",
    "show_save_failure",
]

_SAVE_CHOICE_TEXT_TEMPLATE = "Save changes to {count} file(s)?"
_IN_USE_TEXT = (
    "A running benchmark is reading this file. The running benchmark already cached "
    "its tasks at run-start, so this save will not affect it. Continue?"
)
_RELOAD_TEXT = "Reloading discards your unsaved edits and re-reads the file from disk. Continue?"
_CLOSE_TEXT_TEMPLATE = "{name} has unsaved changes. Save before closing?"
_SAVE_FAILURE_REASON_TEXT: dict[SaveFailureReason, str] = {
    SaveFailureReason.DIRECTORY_NOT_WRITABLE: "The destination folder is not writable.",
    SaveFailureReason.WRITE_FAILED: "The file could not be written.",
    SaveFailureReason.RENAME_FAILED: "The saved file could not be committed in place.",
}


def _confirm_save_discard_cancel(*, title: str, dirty_count: int) -> str:
    """Show the three-choice Save All / Discard All / Cancel dialog; return one of
    ``"save_all"``, ``"discard_all"``, ``"cancel"``."""
    box = QMessageBox()
    box.setWindowTitle(title)
    box.setText(_SAVE_CHOICE_TEXT_TEMPLATE.format(count=dirty_count))
    discard_button = box.addButton("Discard All", QMessageBox.ButtonRole.DestructiveRole)
    box.addButton("Cancel", QMessageBox.ButtonRole.RejectRole)
    save_button = box.addButton("Save All", QMessageBox.ButtonRole.AcceptRole)
    box.setDefaultButton(save_button)
    box.exec()
    clicked = box.clickedButton()
    if clicked is save_button:
        return "save_all"
    if clicked is discard_button:
        return "discard_all"
    return "cancel"


def confirm_leave(dirty_count: int) -> str:
    """The leave-confirmation dialog (§3.7): switching away from the Task Editor
    with dirty buffers. Returns ``"save_all"``, ``"discard_all"``, or ``"cancel"``.
    """
    return _confirm_save_discard_cancel(title="Leave Task Editor", dirty_count=dirty_count)


def confirm_quit(dirty_count: int) -> str:
    """The quit-confirmation dialog (§3.7): quitting the application with dirty
    buffers. Returns ``"save_all"``, ``"discard_all"``, or ``"cancel"``."""
    return _confirm_save_discard_cancel(title="Quit", dirty_count=dirty_count)


def confirm_close(display_name: str) -> str:
    """The close-confirmation dialog (``state_machine.md``'s ``ConfirmClose``):
    closing one dirty file. Returns ``"save_and_close"``, ``"discard_and_close"``,
    or ``"cancel"``."""
    box = QMessageBox()
    box.setWindowTitle("Unsaved changes")
    box.setText(_CLOSE_TEXT_TEMPLATE.format(name=display_name))
    discard_button = box.addButton("Discard && Close", QMessageBox.ButtonRole.DestructiveRole)
    box.addButton("Cancel", QMessageBox.ButtonRole.RejectRole)
    save_button = box.addButton("Save && Close", QMessageBox.ButtonRole.AcceptRole)
    box.setDefaultButton(save_button)
    box.exec()
    clicked = box.clickedButton()
    if clicked is save_button:
        return "save_and_close"
    if clicked is discard_button:
        return "discard_and_close"
    return "cancel"


def confirm_reload() -> bool:
    """The reload-confirmation dialog (EC-TE-09): reloading a dirty file. Returns
    ``True`` only when the user confirms Reload (discarding the edits)."""
    box = QMessageBox()
    box.setWindowTitle("Reload from disk")
    box.setText(_RELOAD_TEXT)
    box.addButton("Cancel", QMessageBox.ButtonRole.RejectRole)
    reload_button = box.addButton("Reload", QMessageBox.ButtonRole.AcceptRole)
    box.setDefaultButton(reload_button)
    box.exec()
    return box.clickedButton() is reload_button


def confirm_in_use_save() -> bool:
    """The in-use-on-save dialog (EC-TE-07), verbatim text. Returns ``True`` only
    when the user confirms Save Anyway; ``False`` means Defer."""
    box = QMessageBox()
    box.setWindowTitle("File in use by a running benchmark")
    box.setText(_IN_USE_TEXT)
    box.addButton("Defer", QMessageBox.ButtonRole.RejectRole)
    save_anyway_button = box.addButton("Save Anyway", QMessageBox.ButtonRole.AcceptRole)
    box.setDefaultButton(save_anyway_button)
    box.exec()
    return box.clickedButton() is save_anyway_button


def show_save_failure(*, reason: SaveFailureReason | None, detail: str) -> None:
    """The save-failure dialog (EC-TE-10): a single Close button, primary/filled.

    Args:
        reason: The typed ``SaveFailureReason``; ``None`` is treated as an
            unspecified write failure.
        detail: The OS-provided failure detail from the ``SaveResult``.
    """
    box = QMessageBox()
    box.setIcon(QMessageBox.Icon.Critical)
    box.setWindowTitle("Save failed")
    reason_text = _SAVE_FAILURE_REASON_TEXT.get(
        reason if reason is not None else SaveFailureReason.WRITE_FAILED,
        "The file could not be saved.",
    )
    box.setText(f"{reason_text}\n\n{detail}" if detail else reason_text)
    box.addButton("Close", QMessageBox.ButtonRole.AcceptRole)
    box.exec()
