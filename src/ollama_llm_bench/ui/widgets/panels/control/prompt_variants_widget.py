"""PromptVariantsWidget — model selector and prompt variant list for Prompt Quality Analysis mode."""

from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import Final

from PySide6.QtWidgets import (
    QComboBox,
    QDialog,
    QDialogButtonBox,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QListWidget,
    QListWidgetItem,
    QPlainTextEdit,
    QPushButton,
    QVBoxLayout,
    QWidget,
)

_logger = logging.getLogger(__name__)

_PLACEHOLDER: Final[str] = "{question}"
_TEMPLATE_ERROR: Final[str] = f"Template must contain {_PLACEHOLDER}"
_MAX_SUMMARY_CHARS: Final[int] = 60

_TOOLTIP_MODEL: Final[str] = "Select the single model to test all prompt variants against."
_TOOLTIP_VARIANTS: Final[str] = "List of prompt variants to evaluate. Each variant is tested on every task."
_TOOLTIP_ADD: Final[str] = "Open the editor to define a new prompt variant."
_TOOLTIP_REMOVE: Final[str] = "Remove the selected prompt variant from the list."
_TOOLTIP_VARIANT_ID: Final[str] = "Unique identifier for this variant. Used in results to distinguish variants."
_TOOLTIP_SYSTEM_PROMPT: Final[str] = "Optional system prompt. Leave blank to use no system message."
_TOOLTIP_USER_TEMPLATE: Final[str] = (
    f"User prompt template. Must contain {_PLACEHOLDER} as the task question placeholder."
)


# ---------------------------------------------------------------------------
# Data model
# ---------------------------------------------------------------------------


@dataclass(frozen=True, slots=True, kw_only=True)
class PromptVariant:
    """Immutable record for a single prompt variant.

    Attributes:
        variant_id: Unique identifier used to label results.
        system_prompt: Optional system message; empty string means none.
        user_prompt_template: Must contain ``{question}`` placeholder.
    """

    variant_id: str
    system_prompt: str
    user_prompt_template: str


# ---------------------------------------------------------------------------
# Variant editor dialog
# ---------------------------------------------------------------------------


class VariantEditorDialog(QDialog):
    """Modal dialog for creating a new :class:`PromptVariant`.

    Validates that ``variant_id`` is non-empty and that
    ``user_prompt_template`` contains the ``{question}`` placeholder before
    enabling the OK button.
    """

    def __init__(self, parent: QWidget | None = None) -> None:
        """Initialise the dialog and wire validation."""
        super().__init__(parent)
        self.setWindowTitle("Add Prompt Variant")
        self.setMinimumWidth(480)
        self._build_widgets()
        self._build_layout()
        self._connect_signals()
        self._validate()

    def _build_widgets(self) -> None:
        self._id_edit = QLineEdit()
        self._id_edit.setPlaceholderText("e.g. chain_of_thought_v1")
        self._id_edit.setToolTip(_TOOLTIP_VARIANT_ID)

        self._system_edit = QPlainTextEdit()
        self._system_edit.setPlaceholderText("Optional system prompt…")
        self._system_edit.setToolTip(_TOOLTIP_SYSTEM_PROMPT)
        self._system_edit.setFixedHeight(80)

        self._template_edit = QPlainTextEdit()
        self._template_edit.setPlaceholderText(f"Write your prompt. Use {_PLACEHOLDER} where the task goes.")
        self._template_edit.setToolTip(_TOOLTIP_USER_TEMPLATE)
        self._template_edit.setFixedHeight(120)

        self._validation_label = QLabel()
        self._validation_label.setProperty("role", "error")

        self._button_box = QDialogButtonBox(QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel)
        ok_button = self._button_box.button(QDialogButtonBox.StandardButton.Ok)
        if ok_button is not None:
            ok_button.setDefault(True)

    def _build_layout(self) -> None:
        layout = QVBoxLayout(self)
        layout.setContentsMargins(8, 8, 8, 8)
        layout.setSpacing(6)

        layout.addWidget(QLabel("Variant ID (required)"))
        layout.addWidget(self._id_edit)

        layout.addWidget(QLabel("System Prompt (optional)"))
        layout.addWidget(self._system_edit)

        layout.addWidget(QLabel(f"User Prompt Template (must contain {_PLACEHOLDER})"))
        layout.addWidget(self._template_edit)
        layout.addWidget(self._validation_label)

        layout.addWidget(self._button_box)

    def _connect_signals(self) -> None:
        self._id_edit.textChanged.connect(self._validate)
        self._template_edit.textChanged.connect(self._validate)
        self._button_box.accepted.connect(self.accept)
        self._button_box.rejected.connect(self.reject)

    def _validate(self) -> None:
        """Enable OK only when both required fields pass validation."""
        variant_id_ok = bool(self._id_edit.text().strip())
        template_ok = _PLACEHOLDER in self._template_edit.toPlainText()

        ok_button = self._button_box.button(QDialogButtonBox.StandardButton.Ok)
        if ok_button is not None:
            ok_button.setEnabled(variant_id_ok and template_ok)

        self._validation_label.setText("" if template_ok else _TEMPLATE_ERROR)
        self._validation_label.setVisible(not template_ok)

    def get_variant(self) -> PromptVariant:
        """Return the :class:`PromptVariant` built from the dialog's inputs."""
        return PromptVariant(
            variant_id=self._id_edit.text().strip(),
            system_prompt=self._system_edit.toPlainText(),
            user_prompt_template=self._template_edit.toPlainText(),
        )


# ---------------------------------------------------------------------------
# Main widget
# ---------------------------------------------------------------------------


class PromptVariantsWidget(QWidget):
    """Widget for configuring model and prompt variants in Prompt Quality Analysis mode.

    Provides a single-model selector and a managed list of
    :class:`PromptVariant` objects. The list is populated via the
    :class:`VariantEditorDialog` and supports removal of selected items.
    """

    def __init__(self, parent: QWidget | None = None) -> None:
        """Initialise child widgets, layout, and signal connections."""
        super().__init__(parent)
        self._variants: list[PromptVariant] = []
        self._build_widgets()
        self._build_layout()
        self._connect_signals()
        self._update_remove_button()

    # ------------------------------------------------------------------
    # Widget construction
    # ------------------------------------------------------------------

    def _build_widgets(self) -> None:
        self._model_label = QLabel("Test Model")
        self._model_combo = QComboBox()
        self._model_combo.setToolTip(_TOOLTIP_MODEL)

        self._variants_label = QLabel("Prompt Variants")
        self._variants_list = QListWidget()
        self._variants_list.setToolTip(_TOOLTIP_VARIANTS)

        self._add_button = QPushButton("Add Variant")
        self._add_button.setToolTip(_TOOLTIP_ADD)

        self._remove_button = QPushButton("Remove")
        self._remove_button.setToolTip(_TOOLTIP_REMOVE)

    def _build_layout(self) -> None:
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(6)

        layout.addWidget(self._model_label)
        layout.addWidget(self._model_combo)
        layout.addSpacing(8)
        layout.addWidget(self._variants_label)
        layout.addWidget(self._variants_list)

        btn_row = QHBoxLayout()
        btn_row.setSpacing(8)
        btn_row.addWidget(self._add_button)
        btn_row.addWidget(self._remove_button)
        btn_row.addStretch()
        layout.addLayout(btn_row)

    def _connect_signals(self) -> None:
        self._add_button.clicked.connect(self._on_add_clicked)
        self._remove_button.clicked.connect(self._on_remove_clicked)
        self._variants_list.itemSelectionChanged.connect(self._update_remove_button)

    # ------------------------------------------------------------------
    # Slots
    # ------------------------------------------------------------------

    def _on_add_clicked(self) -> None:
        """Open :class:`VariantEditorDialog` and append the new variant."""
        dialog = VariantEditorDialog(parent=self)
        if dialog.exec() != QDialog.DialogCode.Accepted:
            return
        variant = dialog.get_variant()
        self._variants.append(variant)
        self._append_list_item(variant)
        _logger.debug("prompt_variant_added", extra={"variant_id": variant.variant_id})

    def _on_remove_clicked(self) -> None:
        """Remove the currently selected variant from the list and internal store."""
        row = self._variants_list.currentRow()
        if row < 0:
            return
        self._variants.pop(row)
        self._variants_list.takeItem(row)
        self._update_remove_button()
        _logger.debug("prompt_variant_removed", extra={"row": row})

    def _update_remove_button(self) -> None:
        """Enable Remove only when a row is selected."""
        self._remove_button.setEnabled(self._variants_list.currentRow() >= 0)

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------

    def _append_list_item(self, variant: PromptVariant) -> None:
        """Add a display-only summary row for *variant* to the list widget."""
        summary = variant.user_prompt_template[:_MAX_SUMMARY_CHARS]
        if len(variant.user_prompt_template) > _MAX_SUMMARY_CHARS:
            summary += "…"
        item = QListWidgetItem(f"[{variant.variant_id}] {summary}")
        self._variants_list.addItem(item)

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def set_available_models(self, models: list[str]) -> None:
        """Populate the model selector with *models*, preserving the current selection if possible.

        Args:
            models: Model name strings to display in the combo box.
        """
        current = self._model_combo.currentText()
        self._model_combo.clear()
        self._model_combo.addItems(models)
        index = self._model_combo.findText(current)
        if index >= 0:
            self._model_combo.setCurrentIndex(index)

    def get_selected_model(self) -> str | None:
        """Return the currently selected model name, or ``None`` if the list is empty.

        Returns:
            Model name string, or ``None`` when no models are loaded.
        """
        text = self._model_combo.currentText()
        return text if text else None

    def get_variants(self) -> list[PromptVariant]:
        """Return a copy of all configured prompt variants.

        Returns:
            Ordered list of :class:`PromptVariant` instances.
        """
        return list(self._variants)
