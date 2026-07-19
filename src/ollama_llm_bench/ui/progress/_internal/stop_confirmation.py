"""``confirm_stop`` -- the Stop confirmation modal (description.md §3.5, §3.6; AC-3;
EC-RUN-2).

Backs both a normal Stop and Stop-while-Pausing (description.md §3.4) -- the same
confirmation gates both paths. No shared confirm-dialog factory exists in
``ui/common_dialogs`` to reuse; this mirrors the inline ``QMessageBox.question``
pattern ``ui/resume_benchmark/_internal/actions.py``'s ``confirm_and_delete_run`` and
``ui/main_window/_internal/close_handler.py``'s ``_confirm_running_benchmark_quit``
already use.
"""

from PySide6.QtWidgets import QMessageBox, QWidget

__all__: list[str] = ["confirm_stop"]

_TITLE = "Stop run"
_TEXT = (
    "Stop — Cancel the in-flight task and end this run? Completed results are kept; "
    "the run status becomes STOPPED and can be resumed later from the Resume tab."
)


def confirm_stop(*, parent: QWidget) -> bool:
    """Show the Stop confirmation modal; return `True` only on Confirm (AC-3)."""
    answer = QMessageBox.question(
        parent,
        _TITLE,
        _TEXT,
        QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
        QMessageBox.StandardButton.No,
    )
    return answer is QMessageBox.StandardButton.Yes
