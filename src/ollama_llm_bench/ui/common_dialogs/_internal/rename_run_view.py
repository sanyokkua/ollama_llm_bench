"""``RenameRunDialog`` -- the Rename Run modal (STORY-056-AC-6, AC-7).

Source of truth: ``docs/v3_specification/07_Common_Dialogs/rename_run_dialog.md``
§3 (layout), §6 (Use Default), §7 (default state), §8 (button behaviour),
§10 (commit effects).
"""

from PySide6.QtCore import QTimer
from PySide6.QtWidgets import (
    QDialog,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QPushButton,
    QVBoxLayout,
    QWidget,
)
import structlog

from ollama_llm_bench.backend.domain import RunId
from ollama_llm_bench.ui.common_dialogs._internal.rename_run_select import validate_name
from ollama_llm_bench.ui.common_dialogs.protocols import RenameRunGateway

__all__: list[str] = ["RenameRunDialog"]

logger = structlog.get_logger(__name__)

_DEBOUNCE_MS = 150


class RenameRunDialog(QDialog):
    """The Rename Run confirmation dialog: live validation, Use default, Rename."""

    def __init__(
        self,
        *,
        gateway: RenameRunGateway,
        run_id: RunId,
        current_custom_name: str | None,
        computed_default_name: str,
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        self.setObjectName("common_dialogs.rename_run")
        self.setWindowTitle("Rename Run")
        self._gateway = gateway
        self._run_id = run_id
        self._computed_default_name = computed_default_name
        self._debounce_timer = QTimer(self)
        self._debounce_timer.setSingleShot(True)
        self._debounce_timer.setInterval(_DEBOUNCE_MS)
        self._debounce_timer.timeout.connect(self._run_validation_now)
        self._build_ui(current_custom_name)
        self._run_validation_now()
        logger.debug("rename_run_dialog_constructed", run_id=run_id)

    def _build_ui(self, current_custom_name: str | None) -> None:
        layout = QVBoxLayout(self)

        current_name_label = QLabel(current_custom_name or self._computed_default_name)
        current_name_label.setObjectName("common_dialogs.rename_run.current_name")
        layout.addWidget(current_name_label)

        self.new_name_edit = QLineEdit(current_custom_name or "")
        self.new_name_edit.setObjectName("common_dialogs.rename_run.new_name")
        self.new_name_edit.setAccessibleName("New run name")
        self.new_name_edit.setMinimumHeight(24)  # 08_ACCESSIBILITY_FLOOR.md §6
        self.new_name_edit.setPlaceholderText(self._computed_default_name)
        self.new_name_edit.textChanged.connect(self._on_text_changed)
        layout.addWidget(self.new_name_edit)

        self._default_preview_label = QLabel()
        self._default_preview_label.setObjectName("common_dialogs.rename_run.default_preview")
        self._default_preview_label.setProperty("role", "muted-caption")
        layout.addWidget(self._default_preview_label)

        self._validation_label = QLabel()
        self._validation_label.setObjectName("common_dialogs.rename_run.validation_strip")
        layout.addWidget(self._validation_label)

        layout.addLayout(self._build_footer())

    def _build_footer(self) -> QHBoxLayout:
        footer = QHBoxLayout()
        self.use_default_button = QPushButton("Use default")
        self.use_default_button.setObjectName("common_dialogs.rename_run.use_default_button")
        self.use_default_button.setAccessibleName("Use default")
        self.use_default_button.setProperty("role", "outlined-muted-button")
        self.use_default_button.clicked.connect(self._on_use_default_clicked)
        footer.addWidget(self.use_default_button)
        footer.addStretch()

        self.cancel_button = QPushButton("Cancel")
        self.cancel_button.setObjectName("common_dialogs.rename_run.cancel_button")
        self.cancel_button.setAccessibleName("Cancel")
        self.cancel_button.setProperty("role", "outlined-muted-button")
        self.cancel_button.clicked.connect(self.reject)
        footer.addWidget(self.cancel_button)

        self.rename_button = QPushButton("Rename")
        self.rename_button.setObjectName("common_dialogs.rename_run.rename_button")
        self.rename_button.setAccessibleName("Rename")
        self.rename_button.setProperty("role", "primary-button")
        self.rename_button.setDefault(True)
        self.rename_button.clicked.connect(self._on_rename_clicked)
        footer.addWidget(self.rename_button)
        return footer

    def _on_text_changed(self, _text: str) -> None:
        self._debounce_timer.start()

    def _on_use_default_clicked(self) -> None:
        logger.debug("rename_run_use_default_clicked", run_id=self._run_id)
        self.new_name_edit.setText("")
        self._run_validation_now()

    def _run_validation_now(self) -> None:
        existing_names = frozenset(
            run.run_name.strip().lower()
            for run in self._gateway.list_runs()
            if run.run_id != self._run_id and run.run_name
        )
        result = validate_name(
            self.new_name_edit.text(), existing_names=existing_names, excluded_run_id_name=None
        )
        self._default_preview_label.setText(
            f"Will use: {self._computed_default_name}" if result.is_default_intent else ""
        )
        self._validation_label.setText(result.message or "")
        self.rename_button.setEnabled(result.is_valid)
        self.rename_button.setToolTip("" if result.is_valid else (result.message or ""))

    def _on_rename_clicked(self) -> None:
        trimmed = self.new_name_edit.text().strip()
        name = trimmed if trimmed else None
        logger.debug("rename_run_committed", run_id=self._run_id, is_default_intent=name is None)
        self._gateway.rename_run(self._run_id, name)
        self.accept()
