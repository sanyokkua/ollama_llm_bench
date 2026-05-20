"""ProvidersTabWidget — tab content for provider management in the settings dialog."""

import logging
import os
import re
from datetime import UTC, datetime
from pathlib import Path
from typing import Final

from PySide6.QtCore import QModelIndex, Qt, QThreadPool, Slot
from PySide6.QtGui import QShowEvent
from PySide6.QtWidgets import (
    QAbstractItemView,
    QCheckBox,
    QComboBox,
    QDialog,
    QFileDialog,
    QGroupBox,
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QMessageBox,
    QPushButton,
    QTableView,
    QVBoxLayout,
    QWidget,
)
from shiboken6 import isValid

from ollama_llm_bench.backend.core.models import (
    AppReadinessChangedEvent,
    EmbeddingConfig,
    ProviderConfig,
    ProvidersConfig,
    ProviderType,
)
from ollama_llm_bench.backend.core.ui_controllers import SettingsWidgetControllerApi
from ollama_llm_bench.backend.services.provider_health_checker import HealthCheckResult, ProviderHealthChecker
from ollama_llm_bench.ui.models.provider_table_model import (
    COL_ACTIONS,
    COL_BASE_URL,
    COL_ENABLED,
    COL_HEALTH,
    COL_LABEL,
    COL_TYPE,
    ProviderTableModel,
)
from ollama_llm_bench.ui.qt_classes.drag_drop_handler import DragDropHandler
from ollama_llm_bench.ui.qt_classes.provider_health_runnable import ProviderHealthRunnable
from ollama_llm_bench.ui.style.style_utils import repolish
from ollama_llm_bench.ui.widgets.settings.env_var_conversion_dialog import EnvVarConversionDialog
from ollama_llm_bench.ui.widgets.settings.provider_actions_delegate import ProviderActionsDelegate
from ollama_llm_bench.ui.widgets.settings.provider_edit_dialog import ProviderEditDialog

logger = logging.getLogger(__name__)

_LABEL_NO_PROVIDERS: Final[str] = "No providers loaded."
_FILTER_YAML: Final[str] = "YAML Files (*.yaml *.yml)"
_DIALOG_TITLE_LOAD: Final[str] = "Load Providers Config"
_DIALOG_TITLE_SAVE: Final[str] = "Save Providers Config"
_DEFAULT_SAVE_FILENAME: Final[str] = "providers.yaml"
_ENV_VAR_RE: Final[re.Pattern[str]] = re.compile(r"^\$\{([A-Z_][A-Z0-9_]*)\}$")
_DISABLED_TOOLTIP: Final[str] = "Provider is disabled. Enable it in this tab to test its connection."
_ENV_MISSING_TOOLTIP: Final[str] = "Environment variable {var} is not set. The provider is unavailable at runtime."
_LOCAL_TRIVIAL_KEYS: Final[frozenset[str]] = frozenset(
    {
        "ollama",
        "lm-studio",
        "lmstudio",
        "none",
        "no-key",
        "sk-no-key-required",
        "",
    }
)
_LOCAL_HOST_RE: Final[re.Pattern[str]] = re.compile(r"^https?://(127\.0\.0\.1|localhost|0\.0\.0\.0)(:\d+)?(/.*)?$")
_ACTIONS_COL_MIN_WIDTH: Final[int] = 200


def _should_prompt_for_envvar(cfg: ProviderConfig) -> bool:
    """Return True when this provider's API key warrants an env-var conversion prompt."""
    if not cfg.api_key_raw:
        return False
    if _ENV_VAR_RE.fullmatch(cfg.api_key_raw):
        return False
    base_url: str = cfg.base_url or ""
    return not (cfg.api_key_raw.strip() in _LOCAL_TRIVIAL_KEYS and bool(_LOCAL_HOST_RE.match(base_url)))


class ProvidersTabWidget(QWidget):
    """Tab content for provider management in the settings dialog.

    Shows a QTableView of provider rows, file management buttons, and
    the embedding provider/model selection at the bottom.
    """

    def __init__(self, *, controller: SettingsWidgetControllerApi) -> None:
        """Initialize the providers tab.

        Args:
            controller: Settings controller for provider and config operations.
        """
        super().__init__()
        self._controller: SettingsWidgetControllerApi = controller
        self._in_flight: set[str] = set()
        self._pending_enable: set[str] = set()
        self._last_health: dict[str, HealthCheckResult] = {}
        self._health_checker: ProviderHealthChecker = ProviderHealthChecker()
        self._is_dirty: bool = False
        self._discovered_embedding_models: list[str] = []
        self._saved_embedding_model: str = ""
        self._model: ProviderTableModel = ProviderTableModel([])
        self._delegate: ProviderActionsDelegate = ProviderActionsDelegate(self)
        self._setup_ui()
        self._setup_signals()
        self._populate_providers()

    def _setup_ui(self) -> None:
        # Button row
        self._save_changes_btn: QPushButton = QPushButton("Save Changes")
        self._save_changes_btn.setProperty("role", "primary")
        self._save_changes_btn.setToolTip(
            "Save providers to the database. A YAML backup is also written to the application data folder."
        )

        self._import_btn: QPushButton = QPushButton("Import config…")
        self._import_btn.setToolTip("Replace your current providers list by importing a .yaml file.")

        self._export_btn: QPushButton = QPushButton("Export config…")
        self._export_btn.setToolTip("Save the current providers list to a file you choose (for sharing / backup).")

        self._reload_btn: QPushButton = QPushButton("Reload")
        self._reload_btn.setToolTip("Discard unsaved changes and reload providers from the database.")

        self._reset_defaults_btn: QPushButton = QPushButton("Reset to Defaults")
        self._reset_defaults_btn.setProperty("role", "danger")
        self._reset_defaults_btn.setToolTip(
            "Restore all providers to factory defaults. Your customisations will be lost."
        )

        button_row: QHBoxLayout = QHBoxLayout()
        button_row.addWidget(self._save_changes_btn)
        button_row.addWidget(self._import_btn)
        button_row.addWidget(self._export_btn)
        button_row.addWidget(self._reload_btn)
        button_row.addWidget(self._reset_defaults_btn)
        button_row.addStretch()

        # Add Provider button
        self._add_provider_btn: QPushButton = QPushButton("Add Provider")
        self._add_provider_btn.setToolTip("Add a new provider entry to the list.")

        # Providers table
        self._table: QTableView = QTableView()
        self._table.setModel(self._model)
        self._table.setItemDelegateForColumn(COL_ACTIONS, self._delegate)
        self._table.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        self._table.setSelectionMode(QAbstractItemView.SelectionMode.SingleSelection)
        self._table.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        self._table.verticalHeader().setVisible(False)
        self._table.setAlternatingRowColors(True)
        header: QHeaderView = self._table.horizontalHeader()
        header.setSectionResizeMode(COL_HEALTH, QHeaderView.ResizeMode.ResizeToContents)
        header.setSectionResizeMode(COL_LABEL, QHeaderView.ResizeMode.Stretch)
        header.setSectionResizeMode(COL_TYPE, QHeaderView.ResizeMode.Interactive)
        header.setSectionResizeMode(COL_BASE_URL, QHeaderView.ResizeMode.Stretch)
        header.setSectionResizeMode(COL_ENABLED, QHeaderView.ResizeMode.ResizeToContents)
        header.setSectionResizeMode(COL_ACTIONS, QHeaderView.ResizeMode.Interactive)
        self._table.setColumnWidth(COL_ACTIONS, _ACTIONS_COL_MIN_WIDTH)

        # Embedding section
        self._embedding_provider_combo: QComboBox = QComboBox()
        self._embedding_model_combo: QComboBox = QComboBox()
        self._embedding_model_combo.setEditable(True)
        self._embedding_model_combo.setInsertPolicy(QComboBox.InsertPolicy.NoInsert)
        self._embedding_model_combo.setPlaceholderText("Select embedding model")
        self._embedding_model_combo.setEnabled(False)
        self._embedding_model_combo.setToolTip(
            "Select a discovered model or type a custom model name. Models are fetched from the selected provider."
        )
        self._embedding_show_all_check: QCheckBox = QCheckBox("Show all models")
        self._embedding_show_all_check.setToolTip(
            "Show all models from the provider, not just embedding-classified ones."
        )

        self._embedding_test_button: QPushButton = QPushButton("Test Embedding")
        self._embedding_test_button.setProperty("size", "small")
        self._embedding_test_button.setToolTip(
            "Sends a test string to verify the embedding model is reachable and producing vectors."
        )
        self._embedding_status_label: QLabel = QLabel()
        self._embedding_status_label.setProperty("role", "status")
        self._embedding_status_label.setVisible(False)

        test_row: QHBoxLayout = QHBoxLayout()
        test_row.addWidget(self._embedding_test_button)
        test_row.addWidget(self._embedding_status_label)
        test_row.addStretch()

        provider_desc: QLabel = QLabel("Provider that serves the embedding model for semantic similarity grading.")
        provider_desc.setWordWrap(True)
        model_desc: QLabel = QLabel(
            "Embedding model for semantic similarity grading. Must be available on the selected provider."
        )
        model_desc.setWordWrap(True)

        model_row: QHBoxLayout = QHBoxLayout()
        model_row.addWidget(self._embedding_model_combo, stretch=1)
        model_row.addWidget(self._embedding_show_all_check)

        embedding_layout: QVBoxLayout = QVBoxLayout()
        embedding_layout.addWidget(provider_desc)
        embedding_layout.addWidget(QLabel("Provider:"))
        embedding_layout.addWidget(self._embedding_provider_combo)
        embedding_layout.addWidget(model_desc)
        embedding_layout.addWidget(QLabel("Model:"))
        embedding_layout.addLayout(model_row)
        embedding_layout.addLayout(test_row)

        embedding_group: QGroupBox = QGroupBox("Embedding")
        embedding_group.setLayout(embedding_layout)

        # Root layout
        root: QVBoxLayout = QVBoxLayout()
        root.addLayout(button_row)
        root.addWidget(self._add_provider_btn)
        root.addWidget(self._table)
        root.addWidget(embedding_group)
        self.setLayout(root)

    def _setup_signals(self) -> None:
        self._save_changes_btn.clicked.connect(self._handle_save_changes)
        self._import_btn.clicked.connect(self._handle_import_config)
        self._export_btn.clicked.connect(self._handle_export_config)
        self._reload_btn.clicked.connect(self._handle_reload)
        self._reset_defaults_btn.clicked.connect(self._handle_reset_to_defaults)
        self._add_provider_btn.clicked.connect(self._handle_add_provider)
        self._embedding_test_button.clicked.connect(self._handle_test_embedding)
        self._embedding_provider_combo.currentIndexChanged.connect(self._handle_embedding_provider_changed)
        self._embedding_show_all_check.toggled.connect(lambda _: self._handle_embedding_provider_changed())

        self._table.clicked.connect(self._on_table_cell_clicked)
        self._model.provider_user_edited.connect(self._on_model_user_edit)
        self._delegate.signals.test_requested.connect(self._on_test_requested)
        self._delegate.signals.edit_requested.connect(self._on_edit_requested)
        self._delegate.signals.delete_requested.connect(self._on_delete_requested)
        self._delegate.signals.reset_requested.connect(self._on_reset_provider_requested)

        self._drag_handler: DragDropHandler = DragDropHandler(parent=self)
        self._drag_handler.install_on(self)
        self._drag_handler.yaml_file_dropped.connect(self._handle_dropped_yaml)

        self._controller.subscribe_to_provider_registry_reloaded(self._on_provider_registry_reloaded, parent=self)
        self._controller.subscribe_to_app_readiness_changed(self._on_readiness_changed, parent=self)

    def _set_dirty(self, dirty: bool) -> None:
        self._is_dirty = dirty
        label = "Save Changes *" if dirty else "Save Changes"
        self._save_changes_btn.setText(label)

    @property
    def is_dirty(self) -> bool:
        """Return True if there are unsaved changes."""
        return self._is_dirty

    def _populate_providers(self) -> None:
        if not isValid(self):
            return

        self._close_all_persistent_editors()

        config: ProvidersConfig | None = self._controller.get_providers_config()
        if config is None or not config.providers:
            self._model = ProviderTableModel([])
            self._table.setModel(self._model)
            self._model.provider_user_edited.connect(self._on_model_user_edit)
            self._embedding_provider_combo.clear()
            return

        self._model = ProviderTableModel(list(config.providers))
        self._table.setModel(self._model)
        self._model.provider_user_edited.connect(self._on_model_user_edit)
        self._open_all_persistent_editors()

        for cfg in config.providers:
            if cfg.last_test_status is not None:
                self._last_health[cfg.provider_id] = HealthCheckResult(
                    provider_id=cfg.provider_id,
                    is_healthy=(cfg.last_test_status == "healthy"),
                    model_count=0,
                    error_message=cfg.last_test_message or "",
                    latency_ms=0,
                )

        saved_model = config.embedding.model or ""
        self._saved_embedding_model = saved_model
        saved_id = config.embedding.provider_id

        self._embedding_provider_combo.blockSignals(True)
        self._embedding_provider_combo.clear()
        for provider_config in config.providers:
            if provider_config.enabled:
                self._embedding_provider_combo.addItem(provider_config.label, provider_config.provider_id)
        for i in range(self._embedding_provider_combo.count()):
            if self._embedding_provider_combo.itemData(i) == saved_id:
                self._embedding_provider_combo.setCurrentIndex(i)
                break
        self._embedding_provider_combo.blockSignals(False)

        if saved_model:
            self._embedding_model_combo.setCurrentText(saved_model)

        self._handle_embedding_provider_changed()

        self._check_env_warnings()

    def _open_all_persistent_editors(self) -> None:
        for row in range(self._model.rowCount()):
            self._table.openPersistentEditor(self._model.index(row, COL_ACTIONS))

    def _close_all_persistent_editors(self) -> None:
        for row in range(self._model.rowCount()):
            self._table.closePersistentEditor(self._model.index(row, COL_ACTIONS))

    def _refresh_persistent_editors(self, from_row: int = 0) -> None:
        """Close and reopen persistent editors from from_row onward to refresh row-index closures."""
        for row in range(from_row, self._model.rowCount()):
            idx = self._model.index(row, COL_ACTIONS)
            self._table.closePersistentEditor(idx)
            self._table.openPersistentEditor(idx)

    @Slot(QModelIndex)
    def _on_table_cell_clicked(self, index: QModelIndex) -> None:
        if index.column() != COL_ENABLED:
            return
        current = self._model.data(index, Qt.ItemDataRole.CheckStateRole)
        new_state = Qt.CheckState.Unchecked if current == Qt.CheckState.Checked else Qt.CheckState.Checked
        self._model.setData(index, new_state, Qt.ItemDataRole.CheckStateRole)

    def _on_model_user_edit(self, provider_id: str) -> None:
        """Mark dirty when the user directly toggles the Enabled checkbox in the table."""
        self._set_dirty(True)
        if self._model.is_enabled(provider_id):
            self._gate_enable(provider_id)

    def _gate_enable(self, provider_id: str) -> None:
        """Block enabling a provider unless it has a passing health result.

        If the provider has no passing health result on record, reverts the enable flag,
        marks it as testing, and queues a health check. _on_health_check_completed will
        enable it on success once the check completes.
        """
        health = self._last_health.get(provider_id)
        if health is not None and health.is_healthy:
            return  # already tested and healthy — allow enable immediately
        self._model.set_enable(provider_id, False)
        self._model.set_health(provider_id, "testing", "Testing connection before enabling…")
        self._pending_enable.add(provider_id)
        self._run_health_check_for(provider_id)

    def showEvent(self, event: QShowEvent) -> None:
        super().showEvent(event)
        self._run_initial_health_checks()

    def _run_initial_health_checks(self) -> None:
        for row in range(self._model.rowCount()):
            config = self._model.get_config(row)
            if not config.enabled:
                self._model.set_health(config.provider_id, "unknown", _DISABLED_TOOLTIP)
                continue
            m = _ENV_VAR_RE.fullmatch(config.api_key_raw)
            if m:
                var_name: str = m.group(1)
                if not os.environ.get(var_name):
                    self._model.set_health(
                        config.provider_id,
                        "down",
                        _ENV_MISSING_TOOLTIP.format(var=var_name),
                    )
                    continue
            self._run_health_check_for(config.provider_id)

    def _run_health_check_for(self, provider_id: str) -> None:
        if provider_id in self._in_flight:
            return
        provider = self._controller.get_provider_instance(provider_id)
        if provider is None:
            self._pending_enable.discard(provider_id)
            self._model.set_health(provider_id, "unknown", "Save providers before testing.")
            return
        self._in_flight.add(provider_id)
        runnable = ProviderHealthRunnable(provider=provider, checker=self._health_checker)
        runnable.signals.completed.connect(self._on_health_check_completed)
        QThreadPool.globalInstance().start(runnable)

    @Slot(object)
    def _on_health_check_completed(self, result: object) -> None:
        if not isinstance(result, HealthCheckResult):
            return
        self._in_flight.discard(result.provider_id)
        self._last_health[result.provider_id] = result
        self._model.apply_health_result(result)
        if result.provider_id in self._pending_enable:
            self._pending_enable.discard(result.provider_id)
            if result.is_healthy:
                self._model.set_enable(result.provider_id, True)
        self._controller.set_last_test_status(
            result.provider_id,
            "healthy" if result.is_healthy else "down",
            datetime.now(UTC).isoformat(),
            result.error_message,
        )

    def _on_test_requested(self, row: int) -> None:
        """Handle Test button click for a table row."""
        config = self._model.get_config(row)
        m = _ENV_VAR_RE.fullmatch(config.api_key_raw)
        if m:
            var_name: str = m.group(1)
            if not os.environ.get(var_name):
                self._model.set_health(
                    config.provider_id,
                    "down",
                    _ENV_MISSING_TOOLTIP.format(var=var_name),
                )
                return
        self._model.set_health(config.provider_id, "testing", "Testing…")
        self._run_health_check_for(config.provider_id)

    def _on_edit_requested(self, row: int) -> None:
        """Open the edit dialog for the given table row."""
        config = self._model.get_config(row)
        all_ids = {c.provider_id for c in self._model.all_configs()} - {config.provider_id}
        dlg = ProviderEditDialog(config=config, used_ids=all_ids, is_new=False, parent=self)
        if dlg.exec() == QDialog.DialogCode.Accepted:
            self._model.update_config(row, dlg.edited_config)
            self._set_dirty(True)

    @Slot(int)
    def _on_reset_provider_requested(self, row: int) -> None:
        """Revert the provider at the given row to its YAML defaults."""
        config = self._model.get_config(row)
        default_config = self._controller.get_default_provider_config(config.provider_id)
        if default_config is None:
            QMessageBox.information(
                self,
                "No Factory Default",
                f"'{config.label}' is a custom provider and has no factory default to reset to.",
            )
            return
        self._model.update_config(row, default_config)
        self._set_dirty(True)

    def _on_delete_requested(self, row: int) -> None:
        """Confirm and remove the provider at the given table row."""
        config = self._model.get_config(row)
        raw_id: object = self._embedding_provider_combo.currentData()
        if isinstance(raw_id, str) and raw_id == config.provider_id:
            QMessageBox.information(
                self,
                "Embedding provider removed",
                "The deleted provider was selected as the embedding provider. "
                "Please select another provider in the Embedding section.",
            )
        answer = QMessageBox.question(
            self,
            "Delete Provider",
            f"Delete provider '{config.label}'?",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.Cancel,
            QMessageBox.StandardButton.Cancel,
        )
        if answer != QMessageBox.StandardButton.Yes:
            return
        self._model.remove_row_for_provider(config.provider_id)
        self._refresh_persistent_editors(from_row=row)
        self._set_dirty(True)

    def _handle_add_provider(self) -> None:
        """Add a new provider via dialog."""
        existing_ids: set[str] = {c.provider_id for c in self._model.all_configs()}
        n = 1
        while f"new_provider_{n}" in existing_ids:
            n += 1
        new_id = f"new_provider_{n}"
        new_config = ProviderConfig(
            provider_id=new_id,
            label="New provider",
            provider_type=ProviderType.OPENAI_COMPATIBLE,
            api_key="",
            api_key_raw="",
            enabled=False,
        )
        row = self._model.append_config(new_config)
        self._table.openPersistentEditor(self._model.index(row, COL_ACTIONS))

        used_ids = existing_ids  # new_id not yet committed — exclude it from "used" for uniqueness check
        dlg = ProviderEditDialog(config=new_config, used_ids=used_ids, is_new=True, parent=self)
        if dlg.exec() == QDialog.DialogCode.Accepted:
            self._model.update_config(row, dlg.edited_config)
            self._set_dirty(True)
        else:
            self._table.closePersistentEditor(self._model.index(row, COL_ACTIONS))
            self._model.remove_row_for_provider(new_id)

    def _handle_test_embedding(self) -> None:
        raw_id: object = self._embedding_provider_combo.currentData()
        provider_id: str = raw_id if isinstance(raw_id, str) else ""
        model: str = self._embedding_model_combo.currentText().strip()

        if not provider_id:
            self._embedding_status_label.setText("No provider selected")
            self._embedding_status_label.setProperty("status_tone", "error")
            self._embedding_status_label.setVisible(True)
            repolish(self._embedding_status_label)
            return

        self._embedding_test_button.setEnabled(False)
        self._embedding_status_label.setText("Testing…")
        self._embedding_status_label.setProperty("status_tone", "neutral")
        self._embedding_status_label.setVisible(True)
        repolish(self._embedding_status_label)

        def _on_result(is_working: bool, dim: int, message: str) -> None:
            if not isValid(self):
                return
            self._embedding_test_button.setEnabled(True)
            tone = "success" if is_working else "error"
            self._embedding_status_label.setText(message)
            self._embedding_status_label.setProperty("status_tone", tone)
            self._embedding_status_label.setVisible(True)
            repolish(self._embedding_status_label)

        self._controller.test_embedding_connection(provider_id, model, _on_result, parent=self)

    def _handle_save_changes(self) -> None:
        configs = self._model.all_configs()
        needing_action = [c for c in configs if _should_prompt_for_envvar(c)]
        if needing_action:
            dialog = EnvVarConversionDialog(configs_needing_action=needing_action, parent=self)
            if dialog.exec() != QDialog.DialogCode.Accepted:
                return
            resolved_map = {c.provider_id: c for c in dialog.resolved_configs}
            for i, orig_cfg in enumerate(configs):
                resolved = resolved_map.get(orig_cfg.provider_id)
                if resolved is not None and resolved.api_key_raw != orig_cfg.api_key_raw:
                    self._model.update_config(i, resolved)

        collected = tuple(self._model.all_configs())
        raw_id: object = self._embedding_provider_combo.currentData()
        embedding_provider_id: str = raw_id if isinstance(raw_id, str) else ""
        embedding_model = self._embedding_model_combo.currentText().strip()

        if embedding_provider_id:
            provider_enabled = any(c.provider_id == embedding_provider_id and c.enabled for c in collected)
            if not provider_enabled:
                QMessageBox.warning(
                    self,
                    "Embedding Provider Disabled",
                    "The selected embedding provider is disabled. "
                    "Cosine-similarity grading will be unavailable until an enabled provider is chosen.",
                )

        if (
            embedding_model
            and self._discovered_embedding_models
            and embedding_model not in self._discovered_embedding_models
        ):
            QMessageBox.information(
                self,
                "Unknown Model Name",
                f"'{embedding_model}' was not found in the discovered model list. "
                "Saving anyway — verify the name is correct.",
            )

        config = ProvidersConfig(
            providers=collected,
            embedding=EmbeddingConfig(provider_id=embedding_provider_id, model=embedding_model),
        )

        if self._controller.save_providers_config_to_standard_path(config):
            self._set_dirty(False)
        else:
            QMessageBox.warning(
                self,
                "Save Failed",
                "Could not save provider configuration. Check the log for details.",
            )

    def _handle_embedding_provider_changed(self, _index: int = 0) -> None:
        raw_id: object = self._embedding_provider_combo.currentData()
        provider_id: str = raw_id if isinstance(raw_id, str) else ""
        if not provider_id:
            return

        _LOADING = "Loading…"
        live = self._embedding_model_combo.currentText()
        saved = live if (live and live != _LOADING) else self._saved_embedding_model

        self._embedding_model_combo.clear()
        self._embedding_model_combo.addItem(_LOADING)
        self._embedding_model_combo.setEnabled(False)

        def _on_models(names: list[str]) -> None:
            if not isValid(self):
                return
            show_all = self._embedding_show_all_check.isChecked()
            filtered = [n for n in names if self._controller.is_embedding_model(n)]
            display = names if (show_all or not filtered) else filtered
            self._embedding_model_combo.clear()
            self._embedding_model_combo.setEnabled(True)
            self._discovered_embedding_models = list(display)
            if display:
                self._embedding_model_combo.addItems(display)
                if saved and saved in display:
                    self._embedding_model_combo.setCurrentText(saved)
                else:
                    self._embedding_model_combo.setCurrentIndex(0)
            else:
                self._embedding_status_label.setText(
                    "No embedding-capable models found. Cosine-similarity grading will be unavailable."
                )
                self._embedding_status_label.setVisible(True)

        self._controller.get_models_for_provider(provider_id, _on_models, parent=self)

    def _handle_import_config(self) -> None:
        if self._is_dirty:
            answer = QMessageBox.question(
                self,
                "Unsaved Changes",
                "Replace your current configuration with the imported file?",
                QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.Cancel,
                QMessageBox.StandardButton.Cancel,
            )
            if answer != QMessageBox.StandardButton.Yes:
                return
        path_str, _ = QFileDialog.getOpenFileName(self, _DIALOG_TITLE_LOAD, "", _FILTER_YAML)
        if not path_str:
            return
        if self._controller.load_providers_yaml(Path(path_str)):
            self._set_dirty(False)
            self._populate_providers()
        else:
            QMessageBox.warning(self, "Import Failed", "Could not import the selected YAML file.")

    def _handle_export_config(self) -> None:
        if self._model.rowCount() == 0:
            return
        collected = tuple(self._model.all_configs())
        raw_id: object = self._embedding_provider_combo.currentData()
        embedding_provider_id: str = raw_id if isinstance(raw_id, str) else ""
        embedding_model = self._embedding_model_combo.currentText().strip()
        config = ProvidersConfig(
            providers=collected,
            embedding=EmbeddingConfig(provider_id=embedding_provider_id, model=embedding_model),
        )
        path_str, _ = QFileDialog.getSaveFileName(self, _DIALOG_TITLE_SAVE, _DEFAULT_SAVE_FILENAME, _FILTER_YAML)
        if not path_str:
            return
        self._controller.save_providers_yaml(Path(path_str), config)

    def _handle_reload(self) -> None:
        if self._is_dirty:
            answer = QMessageBox.question(
                self,
                "Discard Changes",
                "Discard unsaved changes and reload provider configuration from the database?",
                QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.Cancel,
                QMessageBox.StandardButton.Cancel,
            )
            if answer != QMessageBox.StandardButton.Yes:
                return
        self._controller.reload_providers()
        self._set_dirty(False)
        self._populate_providers()

    def _handle_reset_to_defaults(self) -> None:
        """Restore all providers to factory defaults after confirmation."""
        answer = QMessageBox.question(
            self,
            "Reset to Defaults",
            "This will restore all providers to factory defaults.\nYour customisations will be lost. Proceed?",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.Cancel,
            QMessageBox.StandardButton.Cancel,
        )
        if answer != QMessageBox.StandardButton.Yes:
            return
        self._controller.reset_providers_to_defaults()  # emits provider_registry_reloaded → _populate_providers
        self._set_dirty(False)

    def _check_env_warnings(self) -> None:
        for config in self._model.all_configs():
            m = _ENV_VAR_RE.fullmatch(config.api_key_raw)
            if m:
                var_name = m.group(1)
                if not os.environ.get(var_name):
                    tooltip = _ENV_MISSING_TOOLTIP.format(var=var_name)
                    row = self._model.find_row(config.provider_id)
                    if row >= 0:
                        current_state = self._model.get_health_state(config.provider_id)
                        if current_state == "unknown":
                            self._model.set_health(config.provider_id, "down", tooltip)

    def _handle_dropped_yaml(self, path: Path) -> None:
        if self._controller.load_providers_yaml(path):
            self._set_dirty(False)
            self._populate_providers()
        else:
            logger.warning("dropped_yaml_load_failed", extra={"path": str(path)})

    @Slot()
    def _on_provider_registry_reloaded(self) -> None:
        self._populate_providers()

    def _on_readiness_changed(self, event: AppReadinessChangedEvent) -> None:
        """Update the embedding status label based on app readiness state.

        Args:
            event: AppReadinessChangedEvent snapshot emitted after a background probe.
        """
        if event.embedding_ok:
            tone = "success"
            text = "✓ Embedding available"
        elif event.embedding_error:
            tone = "error"
            text = f"✗ {event.embedding_error}"
        else:
            return
        self._embedding_status_label.setText(text)
        self._embedding_status_label.setProperty("status_tone", tone)
        self._embedding_status_label.setVisible(True)
        repolish(self._embedding_status_label)
