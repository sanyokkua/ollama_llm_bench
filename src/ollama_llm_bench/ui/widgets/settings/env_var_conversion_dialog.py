"""EnvVarConversionDialog — batch dialog for converting plain API keys to env-var references."""

import dataclasses
import logging
import os
import platform
import re
from dataclasses import dataclass
from typing import Final

from PySide6.QtCore import QPoint
from PySide6.QtWidgets import (
    QButtonGroup,
    QDialog,
    QDialogButtonBox,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QMessageBox,
    QPushButton,
    QRadioButton,
    QScrollArea,
    QToolTip,
    QVBoxLayout,
    QWidget,
)

from ollama_llm_bench.backend.core.models import ProviderConfig

logger = logging.getLogger(__name__)

_ROLE_SAVE_PLAIN: Final[int] = 0
_ROLE_CONVERT: Final[int] = 1
_ROLE_SKIP: Final[int] = 2

_ENV_VAR_NAME_RE: Final[re.Pattern[str]] = re.compile(r"^[A-Z_][A-Z0-9_]*$")


@dataclass(slots=True, kw_only=True)  # mutable by design: fields read/written during dialog interaction
class _ProviderRow:
    config: ProviderConfig
    btn_group: QButtonGroup
    var_name_edit: QLineEdit
    test_btn: QPushButton


class EnvVarConversionDialog(QDialog):
    """Batch dialog for reviewing and converting plain API keys to environment variable references."""

    def __init__(
        self,
        *,
        configs_needing_action: list[ProviderConfig],
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        self.setWindowTitle("API Key Storage")
        self.setMinimumWidth(600)
        self._rows: list[_ProviderRow] = []
        self._build_ui(configs_needing_action)

    def _build_ui(self, configs: list[ProviderConfig]) -> None:
        outer_layout = QVBoxLayout(self)
        outer_layout.setContentsMargins(12, 12, 12, 12)
        outer_layout.setSpacing(8)

        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        inner = QWidget()
        inner_layout = QVBoxLayout(inner)
        inner_layout.setSpacing(8)

        for cfg in configs:
            self._build_row(cfg, inner_layout)

        inner_layout.addStretch()
        scroll.setWidget(inner)
        outer_layout.addWidget(scroll)

        if platform.system() == "Windows":
            hint = "To set a variable in PowerShell: $env:VAR='key'  (add to $PROFILE)"
        else:
            hint = "To set a variable in your shell: export VAR=key  (add to ~/.zshrc or ~/.bashrc)"

        footer = QLabel(hint)
        footer.setWordWrap(True)
        outer_layout.addWidget(footer)

        btn_box = QDialogButtonBox(QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel)
        btn_box.accepted.connect(self.accept)
        btn_box.rejected.connect(self.reject)
        outer_layout.addWidget(btn_box)

    def _build_row(self, cfg: ProviderConfig, parent_layout: QVBoxLayout) -> None:
        row_widget = QWidget()
        row_layout = QHBoxLayout(row_widget)
        row_layout.setContentsMargins(0, 0, 0, 0)
        row_layout.setSpacing(8)

        name_label = QLabel(cfg.label)
        name_label.setMinimumWidth(120)
        row_layout.addWidget(name_label)

        btn_group = QButtonGroup(row_widget)
        btn_group.setExclusive(True)

        save_plain_btn = QRadioButton("Save plain")
        convert_btn = QRadioButton("Convert to env var")
        skip_btn = QRadioButton("Skip")

        save_plain_btn.setChecked(True)
        btn_group.addButton(save_plain_btn, _ROLE_SAVE_PLAIN)
        btn_group.addButton(convert_btn, _ROLE_CONVERT)
        btn_group.addButton(skip_btn, _ROLE_SKIP)

        row_layout.addWidget(save_plain_btn)
        row_layout.addWidget(convert_btn)
        row_layout.addWidget(skip_btn)

        default_var = f"{cfg.provider_id.upper()}_API_KEY"
        var_name_edit = QLineEdit(default_var)
        var_name_edit.setEnabled(False)
        row_layout.addWidget(var_name_edit, stretch=1)

        test_btn = QPushButton("Test")
        test_btn.setFlat(True)
        test_btn.setEnabled(False)
        row_layout.addWidget(test_btn)

        provider_row = _ProviderRow(
            config=cfg,
            btn_group=btn_group,
            var_name_edit=var_name_edit,
            test_btn=test_btn,
        )
        self._rows.append(provider_row)

        btn_group.idToggled.connect(lambda role, checked, r=provider_row: self._on_role_changed(r, role, checked))
        test_btn.clicked.connect(lambda checked=False, r=provider_row: self._on_test_clicked(r))
        var_name_edit.textChanged.connect(lambda _text, r=provider_row: self._validate_var_name(r))

        parent_layout.addWidget(row_widget)

    def _validate_var_name(self, row: _ProviderRow) -> None:
        text = row.var_name_edit.text().strip()
        is_convert = row.btn_group.checkedId() == _ROLE_CONVERT
        invalid = is_convert and not (bool(text) and bool(_ENV_VAR_NAME_RE.match(text)))
        row.var_name_edit.setProperty("invalid", invalid)
        row.var_name_edit.style().unpolish(row.var_name_edit)
        row.var_name_edit.style().polish(row.var_name_edit)

    def _on_role_changed(self, row: _ProviderRow, role: int, checked: bool) -> None:
        is_convert = role == _ROLE_CONVERT and checked
        row.var_name_edit.setEnabled(is_convert)
        row.test_btn.setEnabled(is_convert)
        self._validate_var_name(row)

    def accept(self) -> None:
        for row in self._rows:
            if row.btn_group.checkedId() == _ROLE_CONVERT:
                var_name = row.var_name_edit.text().strip()
                if not (var_name and _ENV_VAR_NAME_RE.match(var_name)):
                    QMessageBox.warning(
                        self,
                        "Invalid Variable Name",
                        f"'{row.config.label}': enter a valid UPPER_SNAKE_CASE variable name "
                        "or choose 'Save plain' / 'Skip'.",
                    )
                    return
        super().accept()

    def _on_test_clicked(self, row: _ProviderRow) -> None:
        var_name = row.var_name_edit.text().strip()
        if not var_name:
            return
        value = os.environ.get(var_name)
        if value is None:
            msg = f"{var_name} is not set in the current environment."
        else:
            masked = "****" if len(value) <= 8 else f"{value[:4]}…{value[-4:]}"
            msg = f"{var_name} = {masked}"
        QToolTip.showText(row.test_btn.mapToGlobal(QPoint(0, row.test_btn.height())), msg)

    @property
    def resolved_configs(self) -> list[ProviderConfig]:
        """Return configs with API keys resolved according to each row's selection."""
        result: list[ProviderConfig] = []
        for row in self._rows:
            role = row.btn_group.checkedId()
            if role == _ROLE_CONVERT:
                var_name = row.var_name_edit.text().strip()
                if var_name and _ENV_VAR_NAME_RE.match(var_name):
                    resolved = dataclasses.replace(row.config, api_key="", api_key_raw=f"${{{var_name}}}")
                    result.append(resolved)
                else:
                    result.append(row.config)
            else:
                result.append(row.config)
        return result
