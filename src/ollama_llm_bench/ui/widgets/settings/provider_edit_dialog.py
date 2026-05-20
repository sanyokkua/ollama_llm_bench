"""ProviderEditDialog — modal dialog wrapping ProviderEditForm for table-row editing."""

from __future__ import annotations

from PySide6.QtWidgets import QDialog, QDialogButtonBox, QVBoxLayout, QWidget

from ollama_llm_bench.backend.core.models import ProviderConfig
from ollama_llm_bench.ui.widgets.settings.provider_edit_form import ProviderEditForm


class ProviderEditDialog(QDialog):
    """Modal dialog that wraps ProviderEditForm for add/edit operations in the table view.

    The dialog enables the Save button only when the form is valid. When editing
    an existing provider, the provider_id field and type combo are locked to prevent
    accidental changes that would invalidate historical run data.
    """

    def __init__(
        self,
        *,
        config: ProviderConfig,
        used_ids: set[str],
        is_new: bool = False,
        parent: QWidget | None = None,
    ) -> None:
        """Initialize the dialog.

        Args:
            config: Provider configuration to display in the form.
            used_ids: Provider IDs already in use by other providers (excluding config's own ID).
            is_new: When True, all fields are editable. When False, ID and type are locked.
            parent: Parent widget.
        """
        super().__init__(parent)
        self._original_provider_id = config.provider_id
        title = "Add Provider" if is_new else f"Edit — {config.label}"
        self.setWindowTitle(title)
        self.setMinimumWidth(540)

        self._form = ProviderEditForm(used_ids=used_ids, parent=self)
        self._form.populate(config, lock_type=not is_new)
        if not is_new:
            self._form.lock_provider_id()

        self._btn_box = QDialogButtonBox(QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel)
        self._save_btn = self._btn_box.button(QDialogButtonBox.StandardButton.Ok)
        self._save_btn.setText("Save")
        self._save_btn.setEnabled(self._form.is_valid)

        self._btn_box.accepted.connect(self._on_accept)
        self._btn_box.rejected.connect(self.reject)
        self._form.form_changed.connect(self._on_form_changed)

        layout = QVBoxLayout(self)
        layout.addWidget(self._form)
        layout.addWidget(self._btn_box)

    def _on_accept(self) -> None:
        if self._form.is_valid:
            self.accept()

    def _on_form_changed(self) -> None:
        self._save_btn.setEnabled(self._form.is_valid)

    @property
    def edited_config(self) -> ProviderConfig:
        """Return the config built from the form fields."""
        return self._form.get_config(original_provider_id=self._original_provider_id)
