"""``SettingsDialogView`` -- the modal ``QDialog`` shell: tab strip (Providers +
General), footer (Reset to Defaults / save-state indicator / Import… /
Export… / Close / Save Changes) (``description.md`` §2, §5).

A passive ``QWidget``: renders the ``DialogChromeViewModel`` it is given and
forwards user interaction. Imports no Gateway, no reactive store, and no
``ollama_llm_bench.backend.*`` symbol beyond ``models``'s own DTO -- the
passive-View rule. Esc / the title-bar close (X) route through ``reject()``,
which this view overrides to emit ``close_requested`` instead of closing
immediately -- the controller decides whether to actually close
(``on_close_requested()``, STORY-067-AC-6) and, if so, calls ``close_now()``.
"""

from typing import TYPE_CHECKING, override

from PySide6.QtCore import Signal
from PySide6.QtWidgets import (
    QDialog,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QTabWidget,
    QVBoxLayout,
    QWidget,
)

from ollama_llm_bench.ui.settings_dialog._internal.general_tab.view import GeneralTabView
from ollama_llm_bench.ui.settings_dialog._internal.providers_tab.view import ProvidersTabWidget
from ollama_llm_bench.ui.settings_dialog.models import DialogChromeViewModel, GeneralFieldState

if TYPE_CHECKING:
    from ollama_llm_bench.ui.settings_dialog._internal.controller import SettingsController

__all__: list[str] = ["SettingsDialogView"]

_PROVIDERS_TAB_INDEX = 0
_GENERAL_TAB_INDEX = 1


class SettingsDialogView(QDialog):
    """The Settings dialog shell: tab strip, footer, and the five footer actions."""

    save_clicked = Signal()
    export_clicked = Signal()
    import_clicked = Signal()
    reset_clicked = Signal()
    close_requested = Signal()

    def __init__(
        self,
        *,
        providers_tab: ProvidersTabWidget,
        general_tab: GeneralTabView,
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        self.setObjectName("settings_dialog.view")
        self.setWindowTitle("Settings")
        self._providers_tab = providers_tab
        self._general_tab = general_tab
        self._controller: SettingsController | None = None
        self._build_ui()

    def _build_ui(self) -> None:
        layout = QVBoxLayout(self)

        self._tab_widget = QTabWidget()
        self._tab_widget.setObjectName("settings_dialog.tabs")
        self._tab_widget.addTab(self._providers_tab, "Providers")
        self._tab_widget.addTab(self._general_tab, "General")
        layout.addWidget(self._tab_widget, 1)

        layout.addLayout(self._build_footer())

    def _build_footer(self) -> QHBoxLayout:
        footer = QHBoxLayout()

        reset_button = QPushButton("Reset to Defaults")
        reset_button.setObjectName("settings_dialog.reset_to_defaults_button")
        reset_button.setProperty("role", "outlined-muted-button")
        reset_button.clicked.connect(self.reset_clicked)
        footer.addWidget(reset_button)

        self._save_state_label = QLabel("")
        self._save_state_label.setObjectName("settings_dialog.save_state")
        self._save_state_label.setProperty("role", "muted-caption")
        footer.addWidget(self._save_state_label)
        footer.addStretch()

        import_button = QPushButton("Import…")
        import_button.setObjectName("settings_dialog.import_button")
        import_button.setProperty("role", "outlined-muted-button")
        import_button.clicked.connect(self.import_clicked)
        footer.addWidget(import_button)

        export_button = QPushButton("Export…")
        export_button.setObjectName("settings_dialog.export_button")
        export_button.setProperty("role", "outlined-muted-button")
        export_button.clicked.connect(self.export_clicked)
        footer.addWidget(export_button)

        close_button = QPushButton("Close")
        close_button.setObjectName("settings_dialog.close_button")
        close_button.setProperty("role", "outlined-muted-button")
        close_button.clicked.connect(self.close_requested)
        footer.addWidget(close_button)

        self._save_changes_button = QPushButton("Save Changes")
        self._save_changes_button.setObjectName("settings_dialog.save_changes_button")
        self._save_changes_button.setProperty("role", "primary-button")
        self._save_changes_button.clicked.connect(self.save_clicked)
        footer.addWidget(self._save_changes_button)

        return footer

    def apply_chrome(self, chrome: DialogChromeViewModel) -> None:
        """Render both tab labels, the save-state indicator, and the Save
        Changes button's enabled state/asterisk (§2, §5)."""
        self._tab_widget.setTabText(_PROVIDERS_TAB_INDEX, chrome.providers_tab_label)
        self._tab_widget.setTabText(_GENERAL_TAB_INDEX, chrome.general_tab_label)
        self._save_state_label.setText(chrome.save_state_text)
        self._save_changes_button.setText("Save Changes*" if chrome.dirty else "Save Changes")
        self._save_changes_button.setEnabled(chrome.save_enabled)
        if not chrome.save_enabled:
            self._save_changes_button.setToolTip(
                "Fix the validation errors above, or there are no unsaved changes yet."
            )
        else:
            self._save_changes_button.setToolTip("")

    def push_general_field_states(self, states: tuple[GeneralFieldState, ...]) -> None:
        """Forward the General tab's current (validation-augmented) field
        states to the mounted ``GeneralTabView`` (STORY-067-AC-1, AC-2)."""
        self._general_tab.set_field_states(states)

    @override
    def reject(self) -> None:
        """Esc / title-bar close (X): route through ``close_requested`` instead
        of closing immediately (STORY-067-AC-6)."""
        self.close_requested.emit()

    def close_now(self) -> None:
        """Actually close the dialog -- called only by the controller after
        ``on_close_requested()`` confirms it is safe to do so."""
        super().reject()

    @property
    def providers_tab(self) -> ProvidersTabWidget:
        """The mounted Providers tab widget."""
        return self._providers_tab

    @property
    def general_tab(self) -> GeneralTabView:
        """The mounted General tab widget."""
        return self._general_tab
