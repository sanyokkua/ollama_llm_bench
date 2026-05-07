"""Centralised notification routing via QStatusBar and QMessageBox."""

from PySide6.QtWidgets import QMessageBox, QStatusBar, QWidget

_DEFAULT_MSECS: int = 5000


class NotificationService:
    """Routes transient feedback to QStatusBar and blocking alerts to QMessageBox.

    Transient messages (show_info) appear in the status bar for a limited duration.
    Blocking messages (show_warning_blocking, show_error_blocking, confirm) open
    modal QMessageBox dialogs and wait for user acknowledgement.
    """

    def __init__(self, *, status_bar: QStatusBar) -> None:
        """Initialize the service.

        Args:
            status_bar: The application status bar used for transient messages.
        """
        self._status_bar = status_bar

    def show_info(self, text: str, msecs: int = _DEFAULT_MSECS) -> None:
        """Display a transient informational message in the status bar.

        Args:
            text: The message text to display.
            msecs: Duration in milliseconds before the message clears. Defaults to 5000.
        """
        self._status_bar.showMessage(text, msecs)

    def show_warning_blocking(self, parent: QWidget, title: str, text: str) -> None:
        """Display a blocking warning dialog requiring user acknowledgement.

        Args:
            parent: Parent widget for proper dialog stacking.
            title: Dialog window title.
            text: Warning message body.
        """
        QMessageBox.warning(parent, title, text)

    def show_error_blocking(self, parent: QWidget, title: str, text: str) -> None:
        """Display a blocking error dialog requiring user acknowledgement.

        Args:
            parent: Parent widget for proper dialog stacking.
            title: Dialog window title.
            text: Error message body.
        """
        QMessageBox.critical(parent, title, text)

    def confirm(self, parent: QWidget, title: str, text: str) -> bool:
        """Ask the user to confirm an action via a Yes/Cancel dialog.

        The default button is Cancel to prevent accidental destructive actions.

        Args:
            parent: Parent widget for proper dialog stacking.
            title: Dialog window title.
            text: Confirmation question body.

        Returns:
            True if the user clicked Yes; False if they clicked Cancel or closed the dialog.
        """
        result = QMessageBox.question(
            parent,
            title,
            text,
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.Cancel,
            QMessageBox.StandardButton.Cancel,
        )
        return result == QMessageBox.StandardButton.Yes
