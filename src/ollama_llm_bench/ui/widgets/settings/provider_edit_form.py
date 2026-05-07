"""ProviderEditForm — labelled QFormLayout for editing a single provider's configuration."""

import logging
import re
from typing import Final
from urllib.parse import urlparse

from PySide6.QtCore import Signal
from PySide6.QtWidgets import (
    QCheckBox,
    QComboBox,
    QFormLayout,
    QHBoxLayout,
    QInputDialog,
    QLabel,
    QLineEdit,
    QListWidget,
    QPushButton,
    QVBoxLayout,
    QWidget,
)

from ollama_llm_bench.backend.core.models import ProviderConfig, ProviderType
from ollama_llm_bench.ui.style.style_utils import repolish

logger = logging.getLogger(__name__)

# ------------------------------------------------------------------
# Constants
# ------------------------------------------------------------------

_TYPE_OPENAI: Final[str] = ProviderType.OPENAI_COMPATIBLE.value
_TYPE_ANTHROPIC: Final[str] = ProviderType.ANTHROPIC.value
_TYPE_GEMINI: Final[str] = ProviderType.GEMINI.value

_ID_PATTERN: Final[re.Pattern[str]] = re.compile(r"^[a-z0-9_]+$")
_ENV_VAR_PATTERN: Final[re.Pattern[str]] = re.compile(r"^\$\{[A-Z_][A-Z0-9_]*\}$")

_TOOLTIP_ID: Final[str] = (
    "Stable internal identifier. Used in the database to link results to this provider. "
    "Cannot be changed without invalidating historical runs."
)
_TOOLTIP_LABEL: Final[str] = "Human-readable name shown in dropdowns and dialogs."
_TOOLTIP_TYPE: Final[str] = (
    "Determines which API protocol the client uses. Ollama, LM Studio, llama.cpp, OpenAI, "
    "and Azure all use 'openai_compatible'."
)
_TOOLTIP_ENABLED: Final[str] = "When disabled, this provider is hidden from run-configuration dropdowns."
_TOOLTIP_API_KEY: Final[str] = (
    "Use ${ENV_VAR_NAME} to read from an environment variable at runtime. Plain values are stored as-is."
)
_TOOLTIP_BASE_URL: Final[str] = "The OpenAI-compatible base URL ending with /v1."
_TOOLTIP_AZURE_FLAG: Final[str] = "Azure OpenAI?"
_TOOLTIP_AZURE_DEPLOYMENT: Final[str] = "Azure deployment name. Required for Azure OpenAI."
_TOOLTIP_AZURE_API_VERSION: Final[str] = "Azure API version, e.g. 2024-02-15-preview."
_TOOLTIP_ANTHROPIC_BASE_URL: Final[str] = "Override the default Anthropic API endpoint. Leave empty for default."
_TOOLTIP_GEMINI_BASE_URL: Final[str] = (
    "Optional. Override the Gemini API endpoint to point at an internal proxy or API gateway. "
    "Leave empty to use the SDK default. Use ${ENV_VAR_NAME} to read from an environment variable."
)
_TOOLTIP_DEFAULT_MODELS: Final[str] = "Pre-populates the model checklist on the Run Configuration panel."

_ERROR_ENV_VAR: Final[str] = "Use ${VAR_NAME} where VAR_NAME is uppercase letters, digits, and underscores."


class ProviderEditForm(QWidget):
    """Form widget for editing a single provider's configuration.

    Uses a QFormLayout with per-field validation error labels. Conditional rows
    are shown or hidden based on the selected provider type and Azure flag.

    Signals:
        form_changed: Emitted whenever any visible field value changes.
    """

    form_changed: Signal = Signal()

    def __init__(self, *, used_ids: set[str], parent: QWidget | None = None) -> None:
        """Initialize the provider edit form.

        Args:
            used_ids: Set of provider IDs already in use. Does NOT include the
                ID currently being edited — the caller is responsible for excluding it.
            parent: Optional parent widget.
        """
        super().__init__(parent)
        self._used_ids: set[str] = used_ids
        self._setup_widgets()
        self._setup_layout()
        self._setup_signals()
        self._update_field_visibility()
        self._validate()

    # ------------------------------------------------------------------
    # Widget construction
    # ------------------------------------------------------------------

    def _setup_widgets(self) -> None:
        """Construct all child widgets."""
        # Always-visible fields
        self._id_edit: QLineEdit = QLineEdit()
        self._id_edit.setToolTip(_TOOLTIP_ID)

        self._id_error: QLabel = QLabel()
        self._id_error.setProperty("status_tone", "error")
        self._id_error.setVisible(False)

        self._label_edit: QLineEdit = QLineEdit()
        self._label_edit.setToolTip(_TOOLTIP_LABEL)

        self._label_error: QLabel = QLabel()
        self._label_error.setProperty("status_tone", "error")
        self._label_error.setVisible(False)

        self._type_combo: QComboBox = QComboBox()
        self._type_combo.addItems([_TYPE_OPENAI, _TYPE_ANTHROPIC, _TYPE_GEMINI])
        self._type_combo.setToolTip(_TOOLTIP_TYPE)

        self._enabled_check: QCheckBox = QCheckBox()
        self._enabled_check.setChecked(True)
        self._enabled_check.setToolTip(_TOOLTIP_ENABLED)

        self._api_key_edit: QLineEdit = QLineEdit()
        self._api_key_edit.setEchoMode(QLineEdit.EchoMode.Password)
        self._api_key_edit.setToolTip(_TOOLTIP_API_KEY)

        self._api_key_error: QLabel = QLabel()
        self._api_key_error.setProperty("status_tone", "error")
        self._api_key_error.setVisible(False)

        # openai_compatible fields
        self._base_url_edit: QLineEdit = QLineEdit()
        self._base_url_edit.setPlaceholderText("http://localhost:11434/v1")
        self._base_url_edit.setToolTip(_TOOLTIP_BASE_URL)

        self._base_url_error: QLabel = QLabel()
        self._base_url_error.setProperty("status_tone", "error")
        self._base_url_error.setVisible(False)

        self._azure_flag: QCheckBox = QCheckBox()
        self._azure_flag.setToolTip(_TOOLTIP_AZURE_FLAG)

        # Azure-only fields
        self._azure_deployment_edit: QLineEdit = QLineEdit()
        self._azure_deployment_edit.setToolTip(_TOOLTIP_AZURE_DEPLOYMENT)

        self._azure_api_version_edit: QLineEdit = QLineEdit()
        self._azure_api_version_edit.setToolTip(_TOOLTIP_AZURE_API_VERSION)

        # anthropic-only fields
        self._anthropic_base_url_edit: QLineEdit = QLineEdit()
        self._anthropic_base_url_edit.setToolTip(_TOOLTIP_ANTHROPIC_BASE_URL)

        # gemini-only fields
        self._gemini_base_url_edit: QLineEdit = QLineEdit()
        self._gemini_base_url_edit.setPlaceholderText("https://generativelanguage.googleapis.com")
        self._gemini_base_url_edit.setToolTip(_TOOLTIP_GEMINI_BASE_URL)

        # Default models list + buttons
        self._models_list: QListWidget = QListWidget()
        self._add_model_btn: QPushButton = QPushButton("Add model…")
        self._remove_model_btn: QPushButton = QPushButton("Remove")

    def _setup_layout(self) -> None:
        """Compose all widgets into the QFormLayout."""
        self._form_layout: QFormLayout = QFormLayout(self)
        self._form_layout.setContentsMargins(8, 8, 8, 8)
        self._form_layout.setSpacing(6)

        # Always-visible rows
        self._form_layout.addRow("ID:", self._id_edit)
        self._form_layout.addRow("", self._id_error)
        self._form_layout.addRow("Label:", self._label_edit)
        self._form_layout.addRow("", self._label_error)
        self._form_layout.addRow("Type:", self._type_combo)
        self._form_layout.addRow("Enabled:", self._enabled_check)
        self._form_layout.addRow("API key:", self._api_key_edit)
        self._form_layout.addRow("", self._api_key_error)

        # Conditional rows — openai_compatible
        self._form_layout.addRow("Base URL:", self._base_url_edit)
        self._form_layout.addRow("", self._base_url_error)
        self._form_layout.addRow("Azure OpenAI?", self._azure_flag)

        # Azure sub-rows
        self._form_layout.addRow("Azure deployment:", self._azure_deployment_edit)
        self._form_layout.addRow("API version:", self._azure_api_version_edit)

        # anthropic row
        self._form_layout.addRow("Base URL (optional):", self._anthropic_base_url_edit)

        # gemini row
        self._form_layout.addRow("Base URL (optional):", self._gemini_base_url_edit)

        # Default models composite widget
        models_container: QWidget = QWidget()
        models_layout: QVBoxLayout = QVBoxLayout(models_container)
        models_layout.setContentsMargins(0, 0, 0, 0)
        models_layout.setSpacing(4)
        models_layout.addWidget(self._models_list)

        btn_row: QHBoxLayout = QHBoxLayout()
        btn_row.setContentsMargins(0, 0, 0, 0)
        btn_row.addWidget(self._add_model_btn)
        btn_row.addWidget(self._remove_model_btn)
        btn_row.addStretch()
        models_layout.addLayout(btn_row)

        self._form_layout.addRow("Default models:", models_container)

    def _setup_signals(self) -> None:
        """Wire all field signals to change handlers."""
        self._id_edit.textChanged.connect(self._on_field_changed)
        self._label_edit.textChanged.connect(self._on_field_changed)
        self._type_combo.currentTextChanged.connect(self._on_type_changed)
        self._enabled_check.stateChanged.connect(self._on_field_changed)
        self._api_key_edit.textChanged.connect(self._on_field_changed)

        self._base_url_edit.textChanged.connect(self._on_field_changed)
        self._azure_flag.stateChanged.connect(self._on_azure_flag_changed)
        self._azure_deployment_edit.textChanged.connect(self._on_field_changed)
        self._azure_api_version_edit.textChanged.connect(self._on_field_changed)

        self._anthropic_base_url_edit.textChanged.connect(self._on_field_changed)
        self._gemini_base_url_edit.textChanged.connect(self._on_field_changed)

        self._add_model_btn.clicked.connect(self._on_add_model)
        self._remove_model_btn.clicked.connect(self._on_remove_model)

    # ------------------------------------------------------------------
    # Signal handlers
    # ------------------------------------------------------------------

    def _on_field_changed(self) -> None:
        """Handle any field change: validate then emit form_changed."""
        self._validate()
        self.form_changed.emit()

    def _on_type_changed(self, _text: str) -> None:
        """Handle provider type change: update visibility then run generic handler."""
        self._update_field_visibility()
        self._on_field_changed()

    def _on_azure_flag_changed(self, _state: int) -> None:
        """Handle Azure flag toggle: update visibility then run generic handler."""
        self._update_field_visibility()
        self._on_field_changed()

    def _on_add_model(self) -> None:
        """Open an input dialog and add a model to the list if confirmed."""
        text, ok = QInputDialog.getText(self, "Add model", "Model name:")
        if ok and text.strip():
            self._models_list.addItem(text.strip())
            self.form_changed.emit()

    def _on_remove_model(self) -> None:
        """Remove the currently selected model from the list."""
        current_row = self._models_list.currentRow()
        if current_row >= 0:
            self._models_list.takeItem(current_row)
            self.form_changed.emit()

    # ------------------------------------------------------------------
    # Visibility management
    # ------------------------------------------------------------------

    def _set_row_visible(self, widget: QWidget, *, visible: bool) -> None:
        """Show or hide a form row and its label together.

        Args:
            widget: The field widget whose row should be shown or hidden.
            visible: Whether the row should be visible.
        """
        widget.setVisible(visible)
        label_widget = self._form_layout.labelForField(widget)
        if label_widget is not None:
            label_widget.setVisible(visible)

    def _update_field_visibility(self) -> None:
        """Show or hide conditional rows based on current type and Azure flag."""
        current_type: str = self._type_combo.currentText()
        is_openai: bool = current_type == _TYPE_OPENAI
        is_anthropic: bool = current_type == _TYPE_ANTHROPIC
        is_gemini: bool = current_type == _TYPE_GEMINI
        is_azure: bool = is_openai and self._azure_flag.isChecked()

        self._set_row_visible(self._base_url_edit, visible=is_openai)
        self._set_row_visible(self._base_url_error, visible=is_openai)
        self._set_row_visible(self._azure_flag, visible=is_openai)

        self._set_row_visible(self._azure_deployment_edit, visible=is_azure)
        self._set_row_visible(self._azure_api_version_edit, visible=is_azure)

        self._set_row_visible(self._anthropic_base_url_edit, visible=is_anthropic)
        self._set_row_visible(self._gemini_base_url_edit, visible=is_gemini)

    # ------------------------------------------------------------------
    # Validation
    # ------------------------------------------------------------------

    def _set_error(self, label: QLabel, *, message: str | None) -> None:
        """Show or hide an error label with the given message.

        Args:
            label: The error QLabel to update.
            message: Error text to display, or None to hide the label.
        """
        if message:
            label.setText(message)
            label.setVisible(True)
        else:
            label.setText("")
            label.setVisible(False)
        repolish(label)

    def _validate(self) -> None:
        """Run all visible field validations and update error labels."""
        id_text: str = self._id_edit.text().strip()
        if not id_text:
            self._set_error(self._id_error, message="ID is required.")
        elif not _ID_PATTERN.match(id_text):
            self._set_error(self._id_error, message="ID may only contain lowercase letters, digits, and underscores.")
        elif id_text in self._used_ids:
            self._set_error(self._id_error, message="This ID is already used by another provider.")
        else:
            self._set_error(self._id_error, message=None)

        label_text: str = self._label_edit.text().strip()
        if not label_text:
            self._set_error(self._label_error, message="Label is required.")
        else:
            self._set_error(self._label_error, message=None)

        is_openai: bool = self._type_combo.currentText() == _TYPE_OPENAI
        if is_openai:
            url_text: str = self._base_url_edit.text().strip()
            if url_text:
                parsed_scheme: str = urlparse(url_text).scheme
                if parsed_scheme not in {"http", "https"}:
                    self._set_error(self._base_url_error, message="Base URL must start with http:// or https://.")
                else:
                    self._set_error(self._base_url_error, message=None)
            else:
                self._set_error(self._base_url_error, message=None)
        else:
            self._set_error(self._base_url_error, message=None)

        api_key_text: str = self._api_key_edit.text()
        if api_key_text.startswith("${") and not _ENV_VAR_PATTERN.match(api_key_text):
            self._set_error(self._api_key_error, message=_ERROR_ENV_VAR)
        else:
            self._set_error(self._api_key_error, message=None)

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    @property
    def is_valid(self) -> bool:
        """Return True only when all visible validated fields pass."""
        id_text: str = self._id_edit.text().strip()
        id_ok: bool = bool(id_text) and bool(_ID_PATTERN.match(id_text)) and id_text not in self._used_ids

        label_ok: bool = bool(self._label_edit.text().strip())

        is_openai: bool = self._type_combo.currentText() == _TYPE_OPENAI
        base_url_ok: bool = True
        if is_openai:
            url: str = self._base_url_edit.text().strip()
            if url:
                base_url_ok = urlparse(url).scheme in {"http", "https"}

        api_key_text: str = self._api_key_edit.text()
        api_key_ok: bool = True
        if api_key_text.startswith("${"):
            api_key_ok = bool(_ENV_VAR_PATTERN.match(api_key_text))

        return id_ok and label_ok and base_url_ok and api_key_ok

    def get_config(self, *, original_provider_id: str) -> ProviderConfig:
        """Build and return a ProviderConfig from the current field values.

        Args:
            original_provider_id: The provider ID at the time the form was last populated.
                Used by callers to detect renames; not stored in the returned config.

        Returns:
            Frozen ProviderConfig reflecting all current field values.
        """
        current_type_str: str = self._type_combo.currentText()
        provider_type: ProviderType = ProviderType(current_type_str)
        is_openai: bool = current_type_str == _TYPE_OPENAI
        is_azure: bool = is_openai and self._azure_flag.isChecked()
        is_anthropic: bool = current_type_str == _TYPE_ANTHROPIC
        is_gemini: bool = current_type_str == _TYPE_GEMINI

        base_url: str | None = None
        if is_openai:
            raw_url: str = self._base_url_edit.text().strip()
            base_url = raw_url or None
        elif is_anthropic:
            raw_anthropic: str = self._anthropic_base_url_edit.text().strip()
            base_url = raw_anthropic or None
        elif is_gemini:
            raw_gemini: str = self._gemini_base_url_edit.text().strip()
            base_url = raw_gemini or None

        azure_deployment: str | None = self._azure_deployment_edit.text().strip() or None if is_azure else None
        azure_api_version: str | None = self._azure_api_version_edit.text().strip() or None if is_azure else None

        default_models: tuple[str, ...] = tuple(
            self._models_list.item(i).text() for i in range(self._models_list.count())
        )

        return ProviderConfig(
            provider_id=self._id_edit.text().strip(),
            label=self._label_edit.text().strip(),
            provider_type=provider_type,
            enabled=self._enabled_check.isChecked(),
            api_key_raw=self._api_key_edit.text(),
            api_key="",
            base_url=base_url,
            default_models=default_models,
            azure_deployment=azure_deployment,
            azure_api_version=azure_api_version,
        )

    def populate(self, config: ProviderConfig) -> None:
        """Fill all form fields from a ProviderConfig without emitting form_changed.

        Args:
            config: Provider configuration to load into the form.
        """
        # Block signals during population
        self._id_edit.blockSignals(True)
        self._label_edit.blockSignals(True)
        self._type_combo.blockSignals(True)
        self._enabled_check.blockSignals(True)
        self._api_key_edit.blockSignals(True)
        self._base_url_edit.blockSignals(True)
        self._azure_flag.blockSignals(True)
        self._azure_deployment_edit.blockSignals(True)
        self._azure_api_version_edit.blockSignals(True)
        self._anthropic_base_url_edit.blockSignals(True)
        self._gemini_base_url_edit.blockSignals(True)

        try:
            self._id_edit.setText(config.provider_id)
            self._label_edit.setText(config.label)

            idx: int = self._type_combo.findText(config.provider_type.value)
            if idx >= 0:
                self._type_combo.setCurrentIndex(idx)

            self._enabled_check.setChecked(config.enabled)
            self._api_key_edit.setText(config.api_key_raw or config.api_key)

            is_openai: bool = config.provider_type == ProviderType.OPENAI_COMPATIBLE
            is_anthropic: bool = config.provider_type == ProviderType.ANTHROPIC

            if is_openai:
                self._base_url_edit.setText(config.base_url or "")
                has_azure: bool = bool(config.azure_deployment or config.azure_api_version)
                self._azure_flag.setChecked(has_azure)
                self._azure_deployment_edit.setText(config.azure_deployment or "")
                self._azure_api_version_edit.setText(config.azure_api_version or "")
                self._anthropic_base_url_edit.setText("")
                self._gemini_base_url_edit.setText("")
            elif is_anthropic:
                self._base_url_edit.setText("")
                self._azure_flag.setChecked(False)
                self._azure_deployment_edit.setText("")
                self._azure_api_version_edit.setText("")
                self._anthropic_base_url_edit.setText(config.base_url or "")
                self._gemini_base_url_edit.setText("")
            else:
                # gemini
                self._base_url_edit.setText("")
                self._azure_flag.setChecked(False)
                self._azure_deployment_edit.setText("")
                self._azure_api_version_edit.setText("")
                self._anthropic_base_url_edit.setText("")
                self._gemini_base_url_edit.setText(config.base_url or "")

            self._models_list.clear()
            for model in config.default_models:
                self._models_list.addItem(model)
        finally:
            self._id_edit.blockSignals(False)
            self._label_edit.blockSignals(False)
            self._type_combo.blockSignals(False)
            self._enabled_check.blockSignals(False)
            self._api_key_edit.blockSignals(False)
            self._base_url_edit.blockSignals(False)
            self._azure_flag.blockSignals(False)
            self._azure_deployment_edit.blockSignals(False)
            self._azure_api_version_edit.blockSignals(False)
            self._anthropic_base_url_edit.blockSignals(False)
            self._gemini_base_url_edit.blockSignals(False)

        self._update_field_visibility()
        self._validate()
