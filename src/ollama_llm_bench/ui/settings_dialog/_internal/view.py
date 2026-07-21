"""``SettingsDialogView`` -- the modal ``QDialog`` shell: tab strip (Providers only
this story), footer save-state indicator, and Close (``description.md`` §2).

A passive ``QWidget``: renders the ``DialogChromeViewModel`` it is given and
forwards user interaction. Imports no Gateway, no reactive store, and no
``ollama_llm_bench.backend.*`` symbol beyond ``models``'s own DTO -- the
passive-View rule. Save Changes / Import… / Export… / Reset to Defaults are
STORY-067's (the atomic transactions they commit are out of this story's
scope); only the save-state indicator and Close are rendered this story.
"""

from typing import TYPE_CHECKING

from PySide6.QtWidgets import (
    QDialog,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QTabWidget,
    QVBoxLayout,
    QWidget,
)

from ollama_llm_bench.ui.settings_dialog._internal.providers_tab.view import ProvidersTabWidget
from ollama_llm_bench.ui.settings_dialog.models import DialogChromeViewModel

if TYPE_CHECKING:
    from ollama_llm_bench.ui.settings_dialog._internal.controller import SettingsController

__all__: list[str] = ["SettingsDialogView"]


class SettingsDialogView(QDialog):
    """The Settings dialog shell: tab strip, footer save-state indicator, Close."""

    def __init__(self, *, providers_tab: ProvidersTabWidget, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setObjectName("settings_dialog.view")
        self.setWindowTitle("Settings")
        self._providers_tab = providers_tab
        self._controller: SettingsController | None = None
        self._build_ui()

    def _build_ui(self) -> None:
        layout = QVBoxLayout(self)

        self._tab_widget = QTabWidget()
        self._tab_widget.setObjectName("settings_dialog.tabs")
        self._tab_widget.addTab(self._providers_tab, "Providers")
        layout.addWidget(self._tab_widget, 1)

        footer = QHBoxLayout()
        self._save_state_label = QLabel("")
        self._save_state_label.setObjectName("settings_dialog.save_state")
        self._save_state_label.setProperty("role", "muted-caption")
        footer.addWidget(self._save_state_label)
        footer.addStretch()
        close_button = QPushButton("Close")
        close_button.setObjectName("settings_dialog.close_button")
        close_button.setProperty("role", "outlined-muted-button")
        close_button.clicked.connect(self.reject)
        footer.addWidget(close_button)
        layout.addLayout(footer)

    def apply_chrome(self, chrome: DialogChromeViewModel) -> None:
        """Render the tab label and the footer save-state indicator."""
        self._tab_widget.setTabText(0, chrome.providers_tab_label)
        self._save_state_label.setText(chrome.save_state_text)

    @property
    def providers_tab(self) -> ProvidersTabWidget:
        """The mounted Providers tab widget."""
        return self._providers_tab
