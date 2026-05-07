"""ProvidersTabWidget — tab content for provider management in the settings dialog."""

import logging
import os
import re
from pathlib import Path
from typing import Final

from PySide6.QtCore import QThreadPool, Slot
from PySide6.QtGui import QShowEvent
from PySide6.QtWidgets import (
    QComboBox,
    QFileDialog,
    QGroupBox,
    QHBoxLayout,
    QInputDialog,
    QLabel,
    QLineEdit,
    QMessageBox,
    QPushButton,
    QScrollArea,
    QVBoxLayout,
    QWidget,
)

from ollama_llm_bench.backend.core.models import (
    EmbeddingConfig,
    ProviderConfig,
    ProvidersConfig,
    ProviderType,
)
from ollama_llm_bench.backend.core.ui_controllers import SettingsWidgetControllerApi
from ollama_llm_bench.backend.services.provider_health_checker import HealthCheckResult, ProviderHealthChecker
from ollama_llm_bench.ui.qt_classes.drag_drop_handler import DragDropHandler
from ollama_llm_bench.ui.qt_classes.provider_health_runnable import ProviderHealthRunnable
from ollama_llm_bench.ui.style.style_utils import repolish
from ollama_llm_bench.ui.widgets.settings.provider_card_widget import ProviderCardWidget

logger = logging.getLogger(__name__)

_LABEL_NO_PROVIDERS: Final[str] = "No providers loaded."
_DEFAULT_EMBEDDING_MODEL: Final[str] = "bge-m3"
_FILTER_YAML: Final[str] = "YAML Files (*.yaml *.yml)"
_DIALOG_TITLE_LOAD: Final[str] = "Load Providers Config"
_DIALOG_TITLE_SAVE: Final[str] = "Save Providers Config"
_DEFAULT_SAVE_FILENAME: Final[str] = "providers.yaml"
_PLAIN_KEY_RE: Final[re.Pattern[str]] = re.compile(r"^\$\{[A-Z_][A-Z0-9_]*\}$")
_ENV_VAR_RE: Final[re.Pattern[str]] = re.compile(r"^\$\{([A-Z_][A-Z0-9_]*)\}$")
_DISABLED_TOOLTIP: Final[str] = "Provider is disabled. Enable it in this tab to test its connection."
_ENV_MISSING_TOOLTIP: Final[str] = "Environment variable {var} is not set. The provider is unavailable at runtime."


class ProvidersTabWidget(QWidget):
    """Tab content for provider management in the settings dialog.

    Shows scrollable provider cards, file management buttons, and
    the embedding provider/model selection at the bottom.
    """

    def __init__(self, *, controller: SettingsWidgetControllerApi) -> None:
        """Initialize the providers tab.

        Args:
            controller: Settings controller for provider and config operations.
        """
        super().__init__()
        self._controller: SettingsWidgetControllerApi = controller
        self._cards: list[ProviderCardWidget] = []
        self._in_flight: set[str] = set()
        self._health_checker: ProviderHealthChecker = ProviderHealthChecker()
        self._is_dirty: bool = False
        self._setup_ui()
        self._setup_signals()
        self._populate_providers()

    def _setup_ui(self) -> None:
        # Button row
        self._save_changes_btn: QPushButton = QPushButton("Save Changes")
        self._save_changes_btn.setProperty("role", "primary")
        self._save_changes_btn.setToolTip(
            "Save current providers list to providers.yaml in the application data folder."
        )

        self._import_btn: QPushButton = QPushButton("Import config…")
        self._import_btn.setToolTip("Replace your current providers list by importing a .yaml file.")

        self._export_btn: QPushButton = QPushButton("Export config…")
        self._export_btn.setToolTip("Save the current providers list to a file you choose (for sharing / backup).")

        self._reload_btn: QPushButton = QPushButton("Reload")
        self._reload_btn.setToolTip(
            "Discard unsaved changes and re-read providers.yaml from disk. Useful if you edited the file externally."
        )

        button_row: QHBoxLayout = QHBoxLayout()
        button_row.addWidget(self._save_changes_btn)
        button_row.addWidget(self._import_btn)
        button_row.addWidget(self._export_btn)
        button_row.addWidget(self._reload_btn)
        button_row.addStretch()

        # Add Provider button
        self._add_provider_btn: QPushButton = QPushButton("Add Provider")
        self._add_provider_btn.setToolTip("Add a new provider entry to the list.")

        # Cards scroll area
        self._cards_layout: QVBoxLayout = QVBoxLayout()
        self._cards_layout.setContentsMargins(16, 16, 16, 16)

        cards_container: QWidget = QWidget()
        cards_container.setLayout(self._cards_layout)

        scroll: QScrollArea = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setWidget(cards_container)

        # Embedding section
        self._embedding_provider_combo: QComboBox = QComboBox()
        self._embedding_model_combo: QComboBox = QComboBox()
        self._embedding_model_combo.setEditable(True)
        self._embedding_model_combo.setInsertPolicy(QComboBox.InsertPolicy.NoInsert)
        self._embedding_model_combo.addItem(_DEFAULT_EMBEDDING_MODEL)
        self._embedding_model_combo.setCurrentText(_DEFAULT_EMBEDDING_MODEL)
        self._embedding_model_combo.setToolTip(
            "Select a discovered model or type a custom model name. Models are fetched from the selected provider."
        )
        self._embedding_model_combo.setPlaceholderText("Select or type model name")

        # Test button + status label
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
        model_desc: QLabel = QLabel("Embedding model name (e.g. bge-m3). Must be available on the selected provider.")
        model_desc.setWordWrap(True)

        embedding_layout: QVBoxLayout = QVBoxLayout()
        embedding_layout.addWidget(provider_desc)
        embedding_layout.addWidget(QLabel("Provider:"))
        embedding_layout.addWidget(self._embedding_provider_combo)
        embedding_layout.addWidget(model_desc)
        embedding_layout.addWidget(QLabel("Model:"))
        embedding_layout.addWidget(self._embedding_model_combo)
        embedding_layout.addLayout(test_row)

        embedding_group: QGroupBox = QGroupBox("Embedding")
        embedding_group.setLayout(embedding_layout)

        # Root layout
        root: QVBoxLayout = QVBoxLayout()
        root.addLayout(button_row)
        root.addWidget(self._add_provider_btn)
        root.addWidget(scroll)
        root.addWidget(embedding_group)
        self.setLayout(root)

    def _setup_signals(self) -> None:
        self._save_changes_btn.clicked.connect(self._handle_save_changes)
        self._import_btn.clicked.connect(self._handle_import_config)
        self._export_btn.clicked.connect(self._handle_export_config)
        self._reload_btn.clicked.connect(self._handle_reload)
        self._add_provider_btn.clicked.connect(self._handle_add_provider)
        self._embedding_test_button.clicked.connect(self._handle_test_embedding)
        self._embedding_provider_combo.currentIndexChanged.connect(self._handle_embedding_provider_changed)

        self._drag_handler: DragDropHandler = DragDropHandler(parent=self)
        self._drag_handler.install_on(self)
        self._drag_handler.yaml_file_dropped.connect(self._handle_dropped_yaml)

    def _set_dirty(self, dirty: bool) -> None:
        """Update dirty state and reflect it in the Save Changes button label.

        Args:
            dirty: True if there are unsaved changes.
        """
        self._is_dirty = dirty
        label = "Save Changes *" if dirty else "Save Changes"
        self._save_changes_btn.setText(label)

    @property
    def is_dirty(self) -> bool:
        """Return True if there are unsaved changes."""
        return self._is_dirty

    def _populate_providers(self) -> None:
        # Remove existing cards from layout and list
        for card in self._cards:
            card.setParent(None)
            card.deleteLater()
        self._cards.clear()

        # Remove trailing stretch if present
        last_idx = self._cards_layout.count() - 1
        if last_idx >= 0:
            item = self._cards_layout.itemAt(last_idx)
            if item is not None and item.spacerItem() is not None:
                self._cards_layout.removeItem(item)

        config: ProvidersConfig | None = self._controller.get_providers_config()
        if config is None or not config.providers:
            self._cards_layout.addWidget(QLabel(_LABEL_NO_PROVIDERS))
            self._cards_layout.addStretch()
            self._embedding_provider_combo.clear()
            return

        all_ids: set[str] = {pc.provider_id for pc in config.providers}
        for provider_config in config.providers:
            card = ProviderCardWidget(
                config=provider_config,
                used_ids=all_ids - {provider_config.provider_id},
            )
            card.test_config_requested.connect(self._handle_test_connection)
            card.card_changed.connect(self._on_card_changed)
            card.delete_requested.connect(self._handle_delete_provider)
            self._cards.append(card)
            self._cards_layout.addWidget(card)
        self._cards_layout.addStretch()

        self._embedding_provider_combo.clear()
        for provider_config in config.providers:
            if provider_config.enabled:
                self._embedding_provider_combo.addItem(provider_config.label, provider_config.provider_id)

        saved_model = config.embedding.model or _DEFAULT_EMBEDDING_MODEL
        self._embedding_model_combo.setCurrentText(saved_model)
        saved_id = config.embedding.provider_id
        for i in range(self._embedding_provider_combo.count()):
            if self._embedding_provider_combo.itemData(i) == saved_id:
                self._embedding_provider_combo.setCurrentIndex(i)
                break

        # Trigger model list fetch for initially selected provider
        initial_id: object = self._embedding_provider_combo.currentData()
        if isinstance(initial_id, str) and initial_id:
            self._handle_embedding_provider_changed(self._embedding_provider_combo.currentIndex())

        self._check_env_warnings()

    def _on_card_changed(self) -> None:
        """Handle changes from any provider card — mark dirty and validate all cards."""
        self._set_dirty(True)
        any_invalid = any(not card.is_form_valid for card in self._cards)
        self._save_changes_btn.setEnabled(not any_invalid)

    def _handle_embedding_provider_changed(self, _index: int) -> None:
        """Fetch available models from the newly selected embedding provider.

        Replaces the model combo items with discovered model names while
        preserving any previously typed or selected model text.
        """
        raw_id: object = self._embedding_provider_combo.currentData()
        provider_id: str = raw_id if isinstance(raw_id, str) else ""
        if not provider_id:
            return

        current_text = self._embedding_model_combo.currentText()
        self._embedding_model_combo.clear()
        self._embedding_model_combo.addItem("Loading…")
        self._embedding_model_combo.setEnabled(False)

        def _on_models(names: list[str]) -> None:
            self._embedding_model_combo.clear()
            self._embedding_model_combo.setEnabled(True)
            if names:
                for name in names:
                    self._embedding_model_combo.addItem(name)
            # Restore previous selection or typed text
            if current_text and current_text != "Loading…":
                idx = self._embedding_model_combo.findText(current_text)
                if idx >= 0:
                    self._embedding_model_combo.setCurrentIndex(idx)
                else:
                    self._embedding_model_combo.setCurrentText(current_text)
            elif names:
                self._embedding_model_combo.setCurrentIndex(0)

        self._controller.get_models_for_provider(provider_id, _on_models)

    def showEvent(self, event: QShowEvent) -> None:
        super().showEvent(event)
        self._run_initial_health_checks()

    def _run_initial_health_checks(self) -> None:
        for card in self._cards:
            config: ProviderConfig = card.get_edited_config()
            if not config.enabled:
                card.set_health(state="unknown", tooltip=_DISABLED_TOOLTIP)
                continue
            m = _ENV_VAR_RE.fullmatch(config.api_key_raw)
            if m:
                var_name: str = m.group(1)
                if not os.environ.get(var_name):
                    card.set_health(
                        state="down",
                        tooltip=_ENV_MISSING_TOOLTIP.format(var=var_name),
                    )
                    continue
            self._run_health_check_for(config.provider_id)

    def _run_health_check_for(self, provider_id: str) -> None:
        if provider_id in self._in_flight:
            return
        provider = self._controller.get_provider_instance(provider_id)
        if provider is None:
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
        for card in self._cards:
            if card.get_edited_config().provider_id == result.provider_id:
                if result.is_healthy:
                    card.set_health(
                        state="live",
                        tooltip=f"{result.model_count} models available · {result.latency_ms} ms",
                        model_count=result.model_count,
                        latency_ms=result.latency_ms,
                    )
                else:
                    card.set_health(
                        state="down",
                        tooltip=result.error_message or "Provider unreachable.",
                        error_message=result.error_message,
                    )
                return

    def _handle_test_connection(self, config: object) -> None:
        """Handle a test connection request from a provider card.

        Args:
            config: ProviderConfig emitted by the card's test_config_requested signal.
        """
        if not isinstance(config, ProviderConfig):
            return
        typed_config: ProviderConfig = config
        for card in self._cards:
            if card.get_edited_config().provider_id == typed_config.provider_id:
                card.reset_health()
                break
        self._run_health_check_for(typed_config.provider_id)

    def _handle_test_embedding(self) -> None:
        """Test the selected embedding provider and model, updating the status label."""
        raw_id: object = self._embedding_provider_combo.currentData()
        provider_id: str = raw_id if isinstance(raw_id, str) else ""
        model: str = self._embedding_model_combo.currentText().strip() or _DEFAULT_EMBEDDING_MODEL

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
            self._embedding_test_button.setEnabled(True)
            tone = "success" if is_working else "error"
            self._embedding_status_label.setText(message)
            self._embedding_status_label.setProperty("status_tone", tone)
            self._embedding_status_label.setVisible(True)
            repolish(self._embedding_status_label)

        self._controller.test_embedding_connection(provider_id, model, _on_result)

    def _handle_delete_provider(self, provider_id: str) -> None:
        """Remove the provider card matching provider_id from the layout and list.

        Args:
            provider_id: The provider_id of the card to remove.
        """
        for card in self._cards:
            if card.get_edited_config().provider_id == provider_id:
                raw_id: object = self._embedding_provider_combo.currentData()
                if isinstance(raw_id, str) and raw_id == provider_id:
                    QMessageBox.information(
                        self,
                        "Embedding provider removed",
                        "The deleted provider was selected as the embedding provider. "
                        "Please select another provider in the Embedding section.",
                    )
                self._cards.remove(card)
                self._cards_layout.removeWidget(card)
                card.setParent(None)
                card.deleteLater()
                self._set_dirty(True)
                return

    def _handle_add_provider(self) -> None:
        """Add a new blank provider card to the list."""
        existing_ids: set[str] = {c.get_edited_config().provider_id for c in self._cards}
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
        all_ids = existing_ids | {new_id}
        card = ProviderCardWidget(
            config=new_config,
            used_ids=all_ids - {new_id},
        )
        card.test_config_requested.connect(self._handle_test_connection)
        card.card_changed.connect(self._on_card_changed)
        card.delete_requested.connect(self._handle_delete_provider)

        # Insert before the trailing stretch
        insert_pos = self._cards_layout.count()
        last = self._cards_layout.itemAt(insert_pos - 1)
        if last is not None and last.spacerItem() is not None:
            insert_pos -= 1
        self._cards_layout.insertWidget(insert_pos, card)
        self._cards.append(card)

        # Auto-expand the new card
        card._edit_button.click()

        self._set_dirty(True)

    def _handle_save_changes(self) -> None:
        """Validate, optionally convert plain API keys, then save to the standard path."""
        for card in self._cards:
            cfg = card.get_edited_config()
            raw_key = cfg.api_key_raw
            if raw_key and not _PLAIN_KEY_RE.match(raw_key):
                provider_label = cfg.label
                msg_box = QMessageBox(self)
                msg_box.setWindowTitle("Plain API key detected")
                msg_box.setText(
                    f"Provider '{provider_label}' has a plain API key value.\n"
                    "It is recommended to store it as an environment variable reference."
                )
                msg_box.addButton("Save plain value", QMessageBox.ButtonRole.DestructiveRole)
                convert_btn = msg_box.addButton("Save as env var (recommended)", QMessageBox.ButtonRole.AcceptRole)
                cancel_btn = msg_box.addButton("Cancel", QMessageBox.ButtonRole.RejectRole)
                msg_box.exec()
                clicked = msg_box.clickedButton()
                if clicked is cancel_btn:
                    return
                if clicked is convert_btn:
                    default_var = f"{cfg.provider_id.upper()}_API_KEY"
                    var_name, ok = QInputDialog.getText(
                        self,
                        "Environment variable name",
                        (f"Save as environment variable (add to your shell profile):\nexport {default_var}=<your_key>"),
                        QLineEdit.EchoMode.Normal,
                        default_var,
                    )
                    if not ok or not var_name.strip():
                        return
                    updated_config = ProviderConfig(
                        provider_id=cfg.provider_id,
                        label=cfg.label,
                        provider_type=cfg.provider_type,
                        api_key="",
                        api_key_raw=f"${{{var_name.strip()}}}",
                        enabled=cfg.enabled,
                        base_url=cfg.base_url,
                        default_models=cfg.default_models,
                        azure_deployment=cfg.azure_deployment,
                        azure_api_version=cfg.azure_api_version,
                    )
                    card._edit_form.populate(updated_config)

        # Collect all configs
        collected = tuple(card.get_edited_config() for card in self._cards)
        raw_id: object = self._embedding_provider_combo.currentData()
        embedding_provider_id: str = raw_id if isinstance(raw_id, str) else ""
        embedding_model = self._embedding_model_combo.currentText().strip() or _DEFAULT_EMBEDDING_MODEL
        config = ProvidersConfig(
            providers=collected,
            embedding=EmbeddingConfig(provider_id=embedding_provider_id, model=embedding_model),
        )

        if self._controller.save_providers_config_to_standard_path(config):
            self._set_dirty(False)
            self._populate_providers()
        else:
            QMessageBox.warning(
                self,
                "Save Failed",
                "Could not save providers.yaml. Check the log for details.",
            )

    def _handle_import_config(self) -> None:
        """Import providers config from a user-selected YAML file.

        Prompts before discarding unsaved changes.
        """
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
        """Export the current providers config to a user-chosen YAML file."""
        if not self._cards:
            return
        collected = tuple(card.get_edited_config() for card in self._cards)
        raw_id: object = self._embedding_provider_combo.currentData()
        embedding_provider_id: str = raw_id if isinstance(raw_id, str) else ""
        embedding_model = self._embedding_model_combo.currentText().strip() or _DEFAULT_EMBEDDING_MODEL
        config = ProvidersConfig(
            providers=collected,
            embedding=EmbeddingConfig(provider_id=embedding_provider_id, model=embedding_model),
        )
        path_str, _ = QFileDialog.getSaveFileName(self, _DIALOG_TITLE_SAVE, _DEFAULT_SAVE_FILENAME, _FILTER_YAML)
        if not path_str:
            return
        self._controller.save_providers_yaml(Path(path_str), config)

    def _handle_reload(self) -> None:
        """Discard unsaved changes and reload providers from disk.

        Prompts the user before discarding changes when dirty.
        """
        if self._is_dirty:
            answer = QMessageBox.question(
                self,
                "Discard Changes",
                "Discard unsaved changes and reload providers.yaml from disk?",
                QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.Cancel,
                QMessageBox.StandardButton.Cancel,
            )
            if answer != QMessageBox.StandardButton.Yes:
                return
        self._controller.reload_providers()
        self._set_dirty(False)
        self._populate_providers()

    def _check_env_warnings(self) -> None:
        """Inspect each card's API key and show/hide env-var warning labels."""
        for card in self._cards:
            cfg = card.get_edited_config()
            m = _ENV_VAR_RE.match(cfg.api_key_raw)
            if m:
                var_name = m.group(1)
                if not os.environ.get(var_name):
                    card.show_unset_env_warning(var_name)
                else:
                    card.hide_env_warning()
            else:
                card.hide_env_warning()

    def _handle_dropped_yaml(self, path: Path) -> None:
        if self._controller.load_providers_yaml(path):
            self._set_dirty(False)
            self._populate_providers()
        else:
            logger.warning("dropped_yaml_load_failed", extra={"path": str(path)})
