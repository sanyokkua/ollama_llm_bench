"""ProviderCardWidget — single provider configuration card for the settings providers tab."""

import logging
from typing import Final

from PySide6.QtCore import Signal
from PySide6.QtWidgets import (
    QCheckBox,
    QHBoxLayout,
    QLabel,
    QMessageBox,
    QPushButton,
    QVBoxLayout,
    QWidget,
)

from ollama_llm_bench.backend.core.models import ProviderConfig
from ollama_llm_bench.ui.style.style_utils import repolish
from ollama_llm_bench.ui.widgets.settings.provider_edit_form import ProviderEditForm

logger = logging.getLogger(__name__)

_HEALTH_UNKNOWN: Final[str] = "unknown"
_HEALTH_LIVE: Final[str] = "live"
_HEALTH_DOWN: Final[str] = "down"
_HEALTH_DOT_SIZE: Final[int] = 12
_BASE_URL_MAX_WIDTH: Final[int] = 200
_PLACEHOLDER_NO_BASE_URL: Final[str] = "(no base URL)"


class ProviderCardWidget(QWidget):
    """Card widget representing a single provider configuration entry.

    Displays provider label, type badge, base URL, health dot, and
    enable/disable toggle. Emits test_config_requested when the user clicks
    "Test Connection". Expands to show an edit form when "Edit" is clicked.
    Emits delete_requested with the provider_id after user confirmation.

    Signals:
        delete_requested: Emitted with the provider_id after user confirms deletion.
        card_changed: Forwarded from ProviderEditForm.form_changed.
        test_config_requested: Emitted with the current ProviderConfig when "Test" is clicked.
    """

    delete_requested: Signal = Signal(str)
    card_changed: Signal = Signal()
    test_config_requested: Signal = Signal(object)

    def __init__(self, *, config: ProviderConfig, used_ids: set[str]) -> None:
        """Initialize the provider card.

        Args:
            config: The provider configuration to display and edit.
            used_ids: Set of provider IDs already in use by other providers.
                The caller must exclude the current config's ID from this set.
        """
        super().__init__()
        self._config: ProviderConfig = config
        self._used_ids: set[str] = used_ids
        self._setup_ui()
        self._setup_signals()

    def _setup_ui(self) -> None:
        # Health dot
        self._health_dot: QLabel = QLabel()
        self._health_dot.setFixedSize(_HEALTH_DOT_SIZE, _HEALTH_DOT_SIZE)
        self._health_dot.setProperty("health", _HEALTH_UNKNOWN)

        # Provider label (bold)
        self._provider_label: QLabel = QLabel(self._config.label)
        font = self._provider_label.font()
        font.setBold(True)
        self._provider_label.setFont(font)

        # Type badge
        self._type_badge: QLabel = QLabel(self._config.provider_type.value)
        self._type_badge.setProperty("role", "badge")
        self._type_badge.setProperty("variant", "provider-type")

        # Label + badge column
        label_col: QVBoxLayout = QVBoxLayout()
        label_col.addWidget(self._provider_label)
        label_col.addWidget(self._type_badge)
        label_col.setContentsMargins(0, 0, 0, 0)

        # Base URL display
        self._base_url_display: QLabel = QLabel(
            self._config.base_url if self._config.base_url else _PLACEHOLDER_NO_BASE_URL
        )
        self._base_url_display.setMaximumWidth(_BASE_URL_MAX_WIDTH)

        # Enable toggle
        self._enable_checkbox: QCheckBox = QCheckBox()
        self._enable_checkbox.setChecked(self._config.enabled)

        # Test, Edit, and Delete buttons
        self._test_button: QPushButton = QPushButton("Test")
        self._test_button.setProperty("size", "small")
        self._test_button.setToolTip("Verifies the provider is reachable, configured, and responding correctly.")

        self._edit_button: QPushButton = QPushButton("Edit")
        self._edit_button.setProperty("size", "small")

        self._delete_button: QPushButton = QPushButton("Delete")
        self._delete_button.setProperty("size", "small")
        self._delete_button.setProperty("role", "danger")
        self._delete_button.setToolTip("Remove this provider permanently.")

        # Edit form (hidden by default)
        self._edit_form: ProviderEditForm = ProviderEditForm(used_ids=self._used_ids, parent=self)
        self._edit_form.populate(self._config)
        self._edit_form.setVisible(False)

        # Status label (shown below card row after a test)
        self._status_label: QLabel = QLabel()
        self._status_label.setProperty("role", "status")
        self._status_label.setVisible(False)

        # Env-var warning label
        self._env_warning_label: QLabel = QLabel()
        self._env_warning_label.setProperty("status_tone", "warning")
        self._env_warning_label.setWordWrap(True)
        self._env_warning_label.setVisible(False)

        # Card row
        card_row: QHBoxLayout = QHBoxLayout()
        card_row.addWidget(self._health_dot)
        card_row.addLayout(label_col)
        card_row.addWidget(self._base_url_display)
        card_row.addStretch()
        card_row.addWidget(self._enable_checkbox)
        card_row.addWidget(self._test_button)
        card_row.addWidget(self._edit_button)
        card_row.addWidget(self._delete_button)

        # Outer layout
        outer: QVBoxLayout = QVBoxLayout()
        outer.addLayout(card_row)
        outer.addWidget(self._status_label)
        outer.addWidget(self._env_warning_label)
        outer.addWidget(self._edit_form)
        outer.setContentsMargins(4, 4, 4, 4)
        self.setLayout(outer)

    def _setup_signals(self) -> None:
        self._test_button.clicked.connect(self._on_test_clicked)
        self._edit_button.clicked.connect(self._on_edit_clicked)
        self._delete_button.clicked.connect(self._on_delete_clicked)
        self._edit_form.form_changed.connect(self.card_changed)

    def _on_test_clicked(self) -> None:
        self.test_config_requested.emit(self.get_edited_config())

    def _on_edit_clicked(self) -> None:
        self._edit_form.setVisible(not self._edit_form.isVisible())

    def _on_delete_clicked(self) -> None:
        label: str = self._config.label
        answer = QMessageBox.question(
            self,
            "Delete provider",
            (
                f"Delete provider '{label}'? Existing run results will keep their "
                "reference but will appear as 'unknown provider'."
            ),
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.Cancel,
            QMessageBox.StandardButton.Cancel,
        )
        if answer == QMessageBox.StandardButton.Yes:
            self.delete_requested.emit(self._config.provider_id)

    def _set_status_text(self, text: str, *, tone: str = "neutral") -> None:
        if text:
            self._status_label.setText(text)
            self._status_label.setProperty("status_tone", tone)
            self._status_label.setVisible(True)
            repolish(self._status_label)
        else:
            self._status_label.setVisible(False)

    def set_health(
        self,
        *,
        state: str,
        tooltip: str,
        model_count: int = 0,
        latency_ms: int = 0,
        error_message: str = "",
    ) -> None:
        """Update the health dot and status label.

        Args:
            state: Health state — "live", "down", or "unknown".
            tooltip: Human-readable explanation shown on the dot.
            model_count: Number of available models (shown when live).
            latency_ms: Round-trip latency in milliseconds (shown when live).
            error_message: Error detail shown when state is "down".
        """
        self._test_button.setEnabled(True)
        self._health_dot.setProperty("health", state)
        repolish(self._health_dot)
        self._health_dot.setToolTip(tooltip)
        if state == _HEALTH_LIVE:
            self._set_status_text(f"{model_count} models · {latency_ms} ms", tone="success")
        elif state == _HEALTH_DOWN:
            self._set_status_text(error_message or "Unavailable", tone="error")
        else:
            self._set_status_text("")

    def reset_health(self) -> None:
        """Reset the health dot and status label to the testing-in-progress state."""
        self._test_button.setEnabled(False)
        self._health_dot.setProperty("health", _HEALTH_UNKNOWN)
        repolish(self._health_dot)
        self._set_status_text("Testing…", tone="neutral")

    def get_edited_config(self) -> ProviderConfig:
        """Return a new frozen ProviderConfig reflecting current form field values.

        Returns:
            ProviderConfig built from the edit form, using the original provider_id
            as the stable identity key.
        """
        return self._edit_form.get_config(original_provider_id=self._config.provider_id)

    @property
    def is_form_valid(self) -> bool:
        """Return True if the edit form passes all validation checks."""
        return self._edit_form.is_valid

    def show_unset_env_warning(self, var_name: str) -> None:
        """Show a warning label when the provider's env var is not set.

        Args:
            var_name: The environment variable name that is unset.
        """
        self._env_warning_label.setText(
            f"Environment variable {var_name} is not set. The provider will be unavailable at runtime."
        )
        self._env_warning_label.setVisible(True)
        repolish(self._env_warning_label)

    def hide_env_warning(self) -> None:
        """Hide the environment variable warning label."""
        self._env_warning_label.setVisible(False)
