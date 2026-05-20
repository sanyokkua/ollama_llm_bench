"""PromptVariantsWidget — prompt variant list for Prompt Quality Analysis mode."""

from __future__ import annotations

import logging
from pathlib import Path
from typing import Final

import yaml
from PySide6.QtCore import Signal
from PySide6.QtWidgets import (
    QDialog,
    QDialogButtonBox,
    QFileDialog,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QListWidget,
    QListWidgetItem,
    QMessageBox,
    QPlainTextEdit,
    QPushButton,
    QTextEdit,
    QVBoxLayout,
    QWidget,
)

from ollama_llm_bench.backend.core.models import PromptVariantSpec

_logger = logging.getLogger(__name__)

_PLACEHOLDER: Final[str] = "{question}"
_TEMPLATE_ERROR: Final[str] = f"Template must contain {_PLACEHOLDER}"
_MAX_SUMMARY_CHARS: Final[int] = 60
_PREVIEW_PLACEHOLDER: Final[str] = "<no task loaded — add a task file to preview>"
_IMPORT_FILTER: Final[str] = "Variant Files (*.yaml *.yml *.txt)"

_TOOLTIP_VARIANTS: Final[str] = "List of prompt variants to evaluate. Each variant is tested on every task."
_TOOLTIP_ADD: Final[str] = "Open the editor to define a new prompt variant."
_TOOLTIP_REMOVE: Final[str] = "Remove the selected prompt variant from the list."
_TOOLTIP_IMPORT: Final[str] = "Import variants from YAML or TXT files."
_TOOLTIP_VARIANT_ID: Final[str] = "Unique identifier for this variant. Used in results to distinguish variants."
_TOOLTIP_VARIANT_LABEL: Final[str] = "Human-readable label displayed in results tables to identify this variant."
_TOOLTIP_SYSTEM_PROMPT: Final[str] = "Optional system prompt. Leave blank to use no system message."
_TOOLTIP_USER_TEMPLATE: Final[str] = (
    f"User prompt template. Must contain {_PLACEHOLDER} as the task question placeholder."
)


def _next_unique_id(existing_ids: set[str], start_index: int) -> str:
    """Return the first ``variant_N`` ID not present in *existing_ids*."""
    idx = start_index
    while f"variant_{idx}" in existing_ids:
        idx += 1
    return f"variant_{idx}"


# ---------------------------------------------------------------------------
# Variant editor dialog
# ---------------------------------------------------------------------------


class VariantEditorDialog(QDialog):
    """Modal dialog for creating a new :class:`PromptVariantSpec`.

    Validates that ``variant_id``, ``variant_label``, and ``user_prompt_template``
    are non-empty and that the template contains the ``{question}`` placeholder
    before enabling the OK button.
    """

    def __init__(
        self,
        parent: QWidget | None = None,
        *,
        existing_ids: set[str] | None = None,
        default_index: int = 0,
    ) -> None:
        """Initialise the dialog and wire validation.

        Args:
            parent: Optional parent widget.
            existing_ids: Set of already-used variant IDs used to avoid collisions
                when auto-generating the default ID.
            default_index: Starting numeric suffix for the auto-generated ID.
        """
        super().__init__(parent)
        self._default_id = _next_unique_id(existing_ids or set(), default_index)
        self.setWindowTitle("Add Prompt Variant")
        self.setMinimumWidth(480)
        self._build_widgets()
        self._build_layout()
        self._connect_signals()
        self._validate()

    def _build_widgets(self) -> None:
        self._id_edit = QLineEdit()
        self._id_edit.setText(self._default_id)
        self._id_edit.setPlaceholderText("e.g. chain_of_thought_v1")
        self._id_edit.setToolTip(_TOOLTIP_VARIANT_ID)

        self._label_edit = QLineEdit()
        self._label_edit.setPlaceholderText("e.g. Chain-of-Thought v1")
        self._label_edit.setToolTip(_TOOLTIP_VARIANT_LABEL)

        self._system_edit = QPlainTextEdit()
        self._system_edit.setPlaceholderText("Optional system prompt…")
        self._system_edit.setToolTip(_TOOLTIP_SYSTEM_PROMPT)
        self._system_edit.setMinimumHeight(80)

        self._template_edit = QPlainTextEdit()
        self._template_edit.setPlaceholderText(f"Write your prompt. Use {_PLACEHOLDER} where the task goes.")
        self._template_edit.setToolTip(_TOOLTIP_USER_TEMPLATE)
        self._template_edit.setMinimumHeight(120)

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

        layout.addWidget(QLabel("Variant Label (required)"))
        layout.addWidget(self._label_edit)

        layout.addWidget(QLabel("System Prompt (optional)"))
        layout.addWidget(self._system_edit)

        layout.addWidget(QLabel(f"User Prompt Template (must contain {_PLACEHOLDER})"))
        layout.addWidget(self._template_edit)
        layout.addWidget(self._validation_label)

        layout.addWidget(self._button_box)

    def _connect_signals(self) -> None:
        self._id_edit.textChanged.connect(self._validate)
        self._label_edit.textChanged.connect(self._validate)
        self._template_edit.textChanged.connect(self._validate)
        self._button_box.accepted.connect(self.accept)
        self._button_box.rejected.connect(self.reject)

    def _validate(self) -> None:
        """Enable OK only when all required fields pass validation."""
        variant_id_ok = bool(self._id_edit.text().strip())
        label_ok = bool(self._label_edit.text().strip())
        template_ok = _PLACEHOLDER in self._template_edit.toPlainText()

        ok_button = self._button_box.button(QDialogButtonBox.StandardButton.Ok)
        if ok_button is not None:
            ok_button.setEnabled(variant_id_ok and label_ok and template_ok)

        self._validation_label.setText("" if template_ok else _TEMPLATE_ERROR)
        self._validation_label.setVisible(not template_ok)

    def get_variant(self) -> PromptVariantSpec:
        """Return the :class:`PromptVariantSpec` built from the dialog's inputs."""
        system_text = self._system_edit.toPlainText()
        return PromptVariantSpec(
            variant_id=self._id_edit.text().strip(),
            variant_label=self._label_edit.text().strip(),
            system_prompt=system_text if system_text.strip() else None,
            user_prompt_template=self._template_edit.toPlainText(),
        )


# ---------------------------------------------------------------------------
# Main widget
# ---------------------------------------------------------------------------


class PromptVariantsWidget(QWidget):
    """Widget for configuring prompt variants in Prompt Quality Analysis mode.

    Provides a managed list of :class:`PromptVariantSpec` objects. The list is
    populated via the :class:`VariantEditorDialog` and supports removal of selected
    items. Test-model selection is handled by the shared TestModelsWidget.
    """

    variants_changed = Signal()

    def __init__(self, parent: QWidget | None = None) -> None:
        """Initialise child widgets, layout, and signal connections."""
        super().__init__(parent)
        self._variants: list[PromptVariantSpec] = []
        self._task_preview_paths: list[Path] = []
        self._build_widgets()
        self._build_layout()
        self._connect_signals()
        self._update_remove_button()

    # ------------------------------------------------------------------
    # Widget construction
    # ------------------------------------------------------------------

    def _build_widgets(self) -> None:
        self._variants_label = QLabel("Prompt Variants")
        self._variants_list = QListWidget()
        self._variants_list.setToolTip(_TOOLTIP_VARIANTS)

        self._add_button = QPushButton("Add Variant")
        self._add_button.setToolTip(_TOOLTIP_ADD)

        self._remove_button = QPushButton("Remove")
        self._remove_button.setToolTip(_TOOLTIP_REMOVE)

        self._import_button = QPushButton("Import…")
        self._import_button.setToolTip(_TOOLTIP_IMPORT)

        self._preview_label = QLabel("Preview")
        self._preview_label.setProperty("role", "secondary")

        self._preview_edit = QTextEdit()
        self._preview_edit.setReadOnly(True)
        self._preview_edit.setMinimumHeight(80)
        self._preview_edit.setPlaceholderText(_PREVIEW_PLACEHOLDER)

    def _build_layout(self) -> None:
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(6)

        layout.addWidget(self._variants_label)
        layout.addWidget(self._variants_list)

        btn_row = QHBoxLayout()
        btn_row.setSpacing(8)
        btn_row.addWidget(self._add_button)
        btn_row.addWidget(self._remove_button)
        btn_row.addWidget(self._import_button)
        btn_row.addStretch()
        layout.addLayout(btn_row)

        layout.addWidget(self._preview_label)
        layout.addWidget(self._preview_edit)

    def _connect_signals(self) -> None:
        self._add_button.clicked.connect(self._on_add_clicked)
        self._remove_button.clicked.connect(self._on_remove_clicked)
        self._import_button.clicked.connect(self._on_import_clicked)
        self._variants_list.itemSelectionChanged.connect(self._update_remove_button)
        self._variants_list.currentRowChanged.connect(self._update_preview)

    # ------------------------------------------------------------------
    # Slots
    # ------------------------------------------------------------------

    def _on_add_clicked(self) -> None:
        """Open :class:`VariantEditorDialog` and append the new variant."""
        existing_ids = {v.variant_id for v in self._variants}
        dialog = VariantEditorDialog(parent=self, existing_ids=existing_ids, default_index=len(self._variants))
        if dialog.exec() != QDialog.DialogCode.Accepted:
            return
        variant = dialog.get_variant()
        existing_ids = {v.variant_id for v in self._variants}
        if variant.variant_id in existing_ids:
            QMessageBox.warning(
                self,
                "Duplicate Variant ID",
                f"A variant with ID '{variant.variant_id}' already exists. Please choose a unique variant ID.",
            )
            return
        self._append_variant(variant)
        self.variants_changed.emit()
        _logger.debug("prompt_variant_added", extra={"variant_id": variant.variant_id})

    def _on_remove_clicked(self) -> None:
        """Remove the currently selected variant from the list and internal store."""
        row = self._variants_list.currentRow()
        if row < 0:
            return
        self._variants.pop(row)
        self._variants_list.takeItem(row)
        self._update_remove_button()
        self.variants_changed.emit()
        _logger.debug("prompt_variant_removed", extra={"row": row})

    def _on_import_clicked(self) -> None:
        """Open file dialog and import variants from YAML or TXT files."""
        paths, _ = QFileDialog.getOpenFileNames(self, "Import Variants", "", _IMPORT_FILTER)
        if not paths:
            return
        imported_count = 0
        for path_str in paths:
            path = Path(path_str)
            if path.suffix.lower() in {".yaml", ".yml"}:
                imported_count += self._import_from_yaml(path)
            elif path.suffix.lower() == ".txt":
                imported_count += self._import_from_txt(path)
        if imported_count > 0:
            self.variants_changed.emit()
        _logger.debug("prompt_variants_imported", extra={"count": imported_count})

    def _import_from_yaml(self, path: Path) -> int:
        """Import variants from a YAML file. Return count of successfully imported entries.

        Accepts two root shapes:
        - A bare ``list`` of variant dicts.
        - A ``dict`` with a ``variants`` key whose value is a list.

        Each entry may use the long-form keys (``variant_id``, ``variant_label``,
        ``user_prompt_template``, ``system_prompt``) or the short-form keys
        (``id``, ``label``, ``template``, ``system``).  Long-form takes priority.
        """
        try:
            raw = yaml.safe_load(path.read_text(encoding="utf-8"))
        except Exception:
            _logger.warning("Failed to parse YAML variant file: %s", path, exc_info=True)
            return 0
        if isinstance(raw, dict) and "variants" in raw:
            entries = raw["variants"]
        elif isinstance(raw, list):
            entries = raw
        else:
            _logger.warning("YAML variant file must be a list or {variants: [...]}: %s", path)
            return 0
        existing_ids = {v.variant_id for v in self._variants}
        imported = 0
        for entry in entries:
            if not isinstance(entry, dict):
                continue
            variant_id = entry.get("variant_id") or entry.get("id")
            variant_label = entry.get("variant_label") or entry.get("label")
            user_prompt_template = entry.get("user_prompt_template") or entry.get("template")
            if not variant_id or not variant_label or not user_prompt_template:
                _logger.debug("Skipping invalid YAML variant entry (missing required fields)")
                continue
            if variant_id in existing_ids:
                _logger.debug("Skipping duplicate variant_id from YAML: %s", variant_id)
                continue
            system_prompt = entry.get("system_prompt") or entry.get("system") or None
            variant = PromptVariantSpec(
                variant_id=str(variant_id),
                variant_label=str(variant_label),
                user_prompt_template=str(user_prompt_template),
                system_prompt=str(system_prompt) if system_prompt else None,
            )
            self._append_variant(variant)
            existing_ids.add(str(variant_id))
            imported += 1
        return imported

    def _import_from_txt(self, path: Path) -> int:
        """Import a single variant from a TXT file. Return 1 on success, 0 on failure."""
        try:
            content = path.read_text(encoding="utf-8").strip()
        except Exception:
            _logger.warning("Failed to read TXT variant file: %s", path, exc_info=True)
            return 0
        if not content:
            return 0
        existing_ids = {v.variant_id for v in self._variants}
        idx = len(self._variants)
        variant_id = f"imported_{idx}"
        while variant_id in existing_ids:
            idx += 1
            variant_id = f"imported_{idx}"
        variant = PromptVariantSpec(
            variant_id=variant_id,
            variant_label=path.stem,
            user_prompt_template=content,
        )
        self._append_variant(variant)
        return 1

    def _update_remove_button(self) -> None:
        """Enable Remove only when a row is selected."""
        self._remove_button.setEnabled(self._variants_list.currentRow() >= 0)

    def _update_preview(self, row: int) -> None:
        """Render and display the preview for the selected variant row."""
        if row < 0 or row >= len(self._variants):
            self._preview_edit.setPlainText("")
            return
        variant = self._variants[row]
        question_text = self._load_first_task_question()
        if question_text is None:
            self._preview_edit.setPlainText(_PREVIEW_PLACEHOLDER)
            return
        rendered = variant.user_prompt_template.replace(_PLACEHOLDER, question_text)
        lines: list[str] = []
        if variant.system_prompt:
            lines.append(f"[System]\n{variant.system_prompt}\n")
        lines.append(f"[User]\n{rendered}")
        self._preview_edit.setPlainText("\n".join(lines))

    def _load_first_task_question(self) -> str | None:
        """Load the first task's question from the first task preview path, or None."""
        for path in self._task_preview_paths:
            try:
                raw = yaml.safe_load(path.read_text(encoding="utf-8"))
                if isinstance(raw, list) and raw:
                    first = raw[0]
                    if isinstance(first, dict) and "question" in first:
                        return str(first["question"])
            except Exception:
                _logger.debug("Failed to load task preview from %s", path, exc_info=True)
        return None

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------

    def _append_variant(self, variant: PromptVariantSpec) -> None:
        """Append *variant* to the internal list and add a display row."""
        self._variants.append(variant)
        self._append_list_item(variant)

    def _append_list_item(self, variant: PromptVariantSpec) -> None:
        """Add a display-only summary row for *variant* to the list widget."""
        summary = variant.user_prompt_template[:_MAX_SUMMARY_CHARS]
        if len(variant.user_prompt_template) > _MAX_SUMMARY_CHARS:
            summary += "…"
        item = QListWidgetItem(f"[{variant.variant_id}] {variant.variant_label} — {summary}")
        self._variants_list.addItem(item)

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def get_variants(self) -> list[PromptVariantSpec]:
        """Return a copy of all configured prompt variants.

        Returns:
            Ordered list of :class:`PromptVariantSpec` instances.
        """
        return list(self._variants)

    def set_task_preview_source(self, paths: list[Path]) -> None:
        """Update the task file paths used to render the live preview.

        Args:
            paths: List of task YAML file paths. The first loadable task's
                ``question`` field is used as the preview substitution value.
        """
        self._task_preview_paths = list(paths)
        self._update_preview(self._variants_list.currentRow())
