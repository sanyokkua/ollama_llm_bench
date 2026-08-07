"""The Import-preview sub-dialog (``06_Settings_Dialog/description.md`` §8,
``06_Settings_Dialog/mockup.html`` Import-preview modal).
"""

from PySide6.QtWidgets import (
    QDialog,
    QHBoxLayout,
    QLabel,
    QListWidget,
    QListWidgetItem,
    QPushButton,
    QVBoxLayout,
    QWidget,
)

from ollama_llm_bench.ui.settings_dialog._internal.sub_dialogs.import_preview_select import (
    has_hard_error,
)
from ollama_llm_bench.ui.settings_dialog.models import (
    PreviewGroup,
    ProviderImportPreview,
    SettingsImportPreview,
)

__all__: list[str] = [
    "ImportPreviewDialog",
    "make_provider_import_preview_dialog",
    "make_settings_import_preview_dialog",
]

_GROUP_BADGE: dict[PreviewGroup, str] = {
    PreviewGroup.ADDED: "+ Add",
    PreviewGroup.CHANGED: "⟲ Update",
    PreviewGroup.UNCHANGED: "= Unchanged",
    PreviewGroup.SKIPPED: "⊘ Skip",
}


class ImportPreviewDialog(QDialog):
    """Modal preview grouping a proposed import into Added/Changed/Unchanged/
    Skipped, plus every soft/hard finding, before the user confirms or cancels.
    """

    def __init__(
        self,
        *,
        title: str,
        row_lines: tuple[str, ...],
        finding_lines: tuple[str, ...],
        blocked: bool,
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        self.setObjectName("settings_dialog.import_preview")
        self.setWindowTitle(title)
        self.confirmed = False
        self._build_ui(row_lines=row_lines, finding_lines=finding_lines, blocked=blocked)

    def _build_ui(
        self, *, row_lines: tuple[str, ...], finding_lines: tuple[str, ...], blocked: bool
    ) -> None:
        rows_list = QListWidget()
        rows_list.setObjectName("settings_dialog.import_preview.rows")
        rows_list.setAccessibleName("Import preview rows")
        for line in row_lines:
            QListWidgetItem(line, rows_list)

        findings_label = QLabel("\n".join(finding_lines) if finding_lines else "No findings.")
        findings_label.setObjectName("settings_dialog.import_preview.findings")
        findings_label.setWordWrap(True)

        self.cancel_button = QPushButton("Cancel")
        self.cancel_button.setObjectName("settings_dialog.import_preview.cancel")
        self.cancel_button.setAccessibleName("Cancel")
        self.cancel_button.setProperty("role", "outlined-muted-button")
        self.cancel_button.clicked.connect(self._on_cancel_clicked)

        self.apply_button = QPushButton("Apply import")
        self.apply_button.setObjectName("settings_dialog.import_preview.apply")
        self.apply_button.setAccessibleName("Apply import")
        self.apply_button.setProperty("role", "primary-button")
        self.apply_button.setEnabled(not blocked)
        if blocked:
            self.apply_button.setToolTip("Fix the hard errors above before applying this import.")
        self.apply_button.clicked.connect(self._on_apply_clicked)

        footer_layout = QHBoxLayout()
        footer_layout.addStretch()
        footer_layout.addWidget(self.cancel_button)
        footer_layout.addWidget(self.apply_button)

        layout = QVBoxLayout(self)
        layout.addWidget(rows_list)
        layout.addWidget(findings_label)
        layout.addLayout(footer_layout)

    def _on_cancel_clicked(self) -> None:
        self.confirmed = False
        self.reject()

    def _on_apply_clicked(self) -> None:
        self.confirmed = True
        self.accept()


def _finding_lines(preview: SettingsImportPreview | ProviderImportPreview) -> tuple[str, ...]:
    return tuple(
        f"[{finding.severity.value}] {finding.target}: {finding.message}"
        for finding in preview.findings
    )


def make_settings_import_preview_dialog(
    *, preview: SettingsImportPreview, parent: QWidget | None = None
) -> ImportPreviewDialog:
    """Construct the Import-preview modal for a settings import.

    Args:
        preview: The full validated preview to render.
        parent: The Settings dialog this sub-dialog opens on top of, if any.

    Returns:
        The dialog, not yet shown; the caller calls ``.exec()`` then reads
        ``.confirmed``.
    """
    row_lines = tuple(
        f"{_GROUP_BADGE[row.group]}  {row.setting_key}: {row.current_value!r} -> {row.imported_value!r}"
        for row in preview.rows
    )
    return ImportPreviewDialog(
        title="Import preview — settings",
        row_lines=row_lines,
        finding_lines=_finding_lines(preview),
        blocked=has_hard_error(preview),
        parent=parent,
    )


def make_provider_import_preview_dialog(
    *, preview: ProviderImportPreview, parent: QWidget | None = None
) -> ImportPreviewDialog:
    """Construct the Import-preview modal for a provider-configuration import.

    Args:
        preview: The full validated preview to render.
        parent: The Settings dialog this sub-dialog opens on top of, if any.

    Returns:
        The dialog, not yet shown; the caller calls ``.exec()`` then reads
        ``.confirmed``.
    """
    row_lines = tuple(f"{_GROUP_BADGE[row.group]}  {row.name}" for row in preview.rows)
    return ImportPreviewDialog(
        title="Import preview — provider configuration",
        row_lines=row_lines,
        finding_lines=_finding_lines(preview),
        blocked=has_hard_error(preview),
        parent=parent,
    )
