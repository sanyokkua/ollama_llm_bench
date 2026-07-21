"""``ProviderEditDialog`` -- the modal surface for creating or editing one
provider (``sub_dialogs/provider_edit.md``).

Both Test actions call ``SettingsGateway.test_provider(provider_id, model_name)``
against the in-memory working copy: an empty ``model_name`` runs the row-level
Test-reachability probe (mirroring ``ProvidersTabController.on_test_clicked``);
a non-empty ``model_name`` runs the end-to-end Test-inference call (§8.1, §8.2).
This single Gateway method is the only probe entry point ``SettingsGateway``
declares (08-E §7b.6) -- there is no separate reachability-only method.

The live in-flight progress sub-states of §8.2 (the two-line
``_inference_progress``-driven "testing waiting"/"testing receiving" indicator)
are not implemented this story -- out of this story's ``acceptance_criteria``;
only the outcome the call settles with is rendered inline.
"""

import os
from typing import override
import uuid

import msgspec
from PySide6.QtWidgets import (
    QCheckBox,
    QComboBox,
    QDialog,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QPushButton,
    QStackedWidget,
    QVBoxLayout,
    QWidget,
)
import structlog

from ollama_llm_bench.backend.domain import InferenceActivity, ProviderConfig, ProviderType
from ollama_llm_bench.backend.events import (
    SIGNAL_INFERENCE_ACTIVITY_CHANGED,
    InferenceActivityChangedEvent,
)
from ollama_llm_bench.ui.settings_dialog._internal.sub_dialogs.provider_edit_select import (
    DUPLICATE_NAME_MESSAGE,
    duplicate_name_conflict,
    env_var_diagnostic,
    env_var_name_error,
    gate_button_state,
    run_inference_test_enabled,
)
from ollama_llm_bench.ui.settings_dialog.models import ProviderEditCollaborators

__all__: list[str] = ["ProviderEditDialog", "make_provider_edit_dialog"]

logger = structlog.get_logger(__name__)

_PROVIDER_TYPE_LABELS: tuple[tuple[ProviderType, str], ...] = (
    (ProviderType.OPENAI_COMPATIBLE, "OpenAI-compatible"),
    (ProviderType.ANTHROPIC, "Anthropic"),
    (ProviderType.GEMINI, "Gemini"),
)


def _blank_draft() -> ProviderConfig:
    # A session-scoped placeholder id, never the final persisted `provider_id`
    # -- DD-33 reserves real UUID4 assignment to `ProvidersStore.add` at the
    # base dialog's Save Changes commit (a later story). Carried only so this
    # session's working row has a stable tracking identity before then.
    return ProviderConfig(
        provider_id=str(uuid.uuid4()),
        name="",
        provider_type=ProviderType.OPENAI_COMPATIBLE,
        enabled=True,
    )


class ProviderEditDialog(QDialog):
    """The Provider Edit modal: identity/endpoint fields, the API-key secret
    card, and the Test reachability / Test inference panels."""

    def __init__(
        self,
        *,
        collaborators: ProviderEditCollaborators,
        config: ProviderConfig | None,
        existing_names: tuple[str, ...],
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        self.setObjectName("settings_dialog.provider_edit")
        self._gateway = collaborators.gateway
        self._is_new = config is None
        self._working = config if config is not None else _blank_draft()
        self._existing_names = existing_names
        self.result_config: ProviderConfig | None = None
        self._gate_activity = InferenceActivity.IDLE
        self._activity_subscription = collaborators.event_bus.subscribe(
            SIGNAL_INFERENCE_ACTIVITY_CHANGED, self._on_inference_activity_changed
        )
        self._build_ui()
        self._apply_working_copy()
        logger.debug("provider_edit_dialog_constructed", is_new=self._is_new)

    def _build_ui(self) -> None:
        self.setWindowTitle(
            "Add Provider" if self._is_new else f"Edit Provider — {self._working.name}"
        )
        layout = QVBoxLayout(self)

        self._name_edit = QLineEdit()
        self._name_edit.setObjectName("settings_dialog.provider_edit.name")
        self._name_edit.textChanged.connect(self._on_name_changed)
        layout.addWidget(self._name_edit)
        self._name_error_label = QLabel("")
        self._name_error_label.setObjectName("settings_dialog.provider_edit.name_error")
        self._name_error_label.setProperty("role", "error-caption")
        layout.addWidget(self._name_error_label)

        self._type_combo = QComboBox()
        self._type_combo.setObjectName("settings_dialog.provider_edit.type")
        for provider_type, label in _PROVIDER_TYPE_LABELS:
            self._type_combo.addItem(label, provider_type.value)
        self._type_combo.setEnabled(self._is_new)
        layout.addWidget(self._type_combo)

        self._enabled_checkbox = QCheckBox("Enabled")
        self._enabled_checkbox.setObjectName("settings_dialog.provider_edit.enabled")
        layout.addWidget(self._enabled_checkbox)

        self._base_url_edit = QLineEdit()
        self._base_url_edit.setObjectName("settings_dialog.provider_edit.base_url")
        self._base_url_edit.setPlaceholderText("https://api.openai.com/v1")
        layout.addWidget(self._base_url_edit)

        self._api_key_edit = QLineEdit()
        self._api_key_edit.setObjectName("settings_dialog.provider_edit.api_key")
        self._api_key_edit.setPlaceholderText("OPENAI_API_KEY")
        self._api_key_edit.textChanged.connect(self._on_api_key_changed)
        layout.addWidget(self._api_key_edit)
        self._api_key_error_label = QLabel("")
        self._api_key_error_label.setObjectName("settings_dialog.provider_edit.api_key_error")
        self._api_key_error_label.setProperty("role", "error-caption")
        layout.addWidget(self._api_key_error_label)
        self._api_key_diagnostic_label = QLabel("")
        self._api_key_diagnostic_label.setObjectName(
            "settings_dialog.provider_edit.api_key_diagnostic"
        )
        layout.addWidget(self._api_key_diagnostic_label)

        self._result_label = QLabel("")
        self._result_label.setObjectName("settings_dialog.provider_edit.result")
        self._result_label.setWordWrap(True)
        layout.addWidget(self._result_label)

        layout.addWidget(self._build_inference_panel())
        layout.addLayout(self._build_footer())

    def _build_inference_panel(self) -> QWidget:
        self._inference_panel = QWidget()
        self._inference_panel.setObjectName("settings_dialog.provider_edit.inference_panel")
        self._inference_panel.setVisible(False)
        panel_layout = QVBoxLayout(self._inference_panel)
        panel_layout.setContentsMargins(0, 0, 0, 0)

        self._manual_entry_checkbox = QCheckBox("Enter model name manually")
        self._manual_entry_checkbox.setObjectName(
            "settings_dialog.provider_edit.manual_entry_toggle"
        )
        self._manual_entry_checkbox.toggled.connect(self._on_manual_entry_toggled)
        panel_layout.addWidget(self._manual_entry_checkbox)

        self._model_stack = QStackedWidget()
        self._model_dropdown = QComboBox()
        self._model_dropdown.setObjectName("settings_dialog.provider_edit.model_dropdown")
        self._model_dropdown.currentIndexChanged.connect(self._refresh_run_button_state)
        self._model_stack.addWidget(self._model_dropdown)
        self._manual_model_edit = QLineEdit()
        self._manual_model_edit.setObjectName("settings_dialog.provider_edit.manual_model")
        self._manual_model_edit.textChanged.connect(self._refresh_run_button_state)
        self._model_stack.addWidget(self._manual_model_edit)
        panel_layout.addWidget(self._model_stack)

        self._billing_warning_label = QLabel(
            "This call is billable on this provider — one short request will be "
            "sent to the selected model."
        )
        self._billing_warning_label.setObjectName("settings_dialog.provider_edit.billing_warning")
        self._billing_warning_label.setProperty("role", "warning-callout")
        self._billing_warning_label.setWordWrap(True)
        self._billing_warning_label.setVisible(False)
        panel_layout.addWidget(self._billing_warning_label)

        self._run_inference_button = QPushButton("Run inference test")
        self._run_inference_button.setObjectName("settings_dialog.provider_edit.run_inference")
        self._run_inference_button.clicked.connect(self._on_run_inference_clicked)
        panel_layout.addWidget(self._run_inference_button)
        return self._inference_panel

    def _build_footer(self) -> QHBoxLayout:
        footer = QHBoxLayout()
        self._test_reachability_button = QPushButton("Test reachability")
        self._test_reachability_button.setObjectName(
            "settings_dialog.provider_edit.test_reachability"
        )
        self._test_reachability_button.clicked.connect(self._on_test_reachability_clicked)
        footer.addWidget(self._test_reachability_button)

        self._test_inference_button = QPushButton("Test inference")
        self._test_inference_button.setObjectName("settings_dialog.provider_edit.test_inference")
        self._test_inference_button.clicked.connect(self._on_test_inference_toggled)
        footer.addWidget(self._test_inference_button)
        footer.addStretch()

        cancel_button = QPushButton("Cancel")
        cancel_button.setObjectName("settings_dialog.provider_edit.cancel")
        cancel_button.setProperty("role", "outlined-muted-button")
        cancel_button.clicked.connect(self.reject)
        footer.addWidget(cancel_button)

        self._save_button = QPushButton("Save")
        self._save_button.setObjectName("settings_dialog.provider_edit.save")
        self._save_button.setProperty("role", "primary-button")
        self._save_button.setDefault(True)
        self._save_button.clicked.connect(self._on_save_clicked)
        footer.addWidget(self._save_button)
        return footer

    def _apply_working_copy(self) -> None:
        self._name_edit.setText(self._working.name)
        index = self._type_combo.findData(self._working.provider_type.value)
        if index >= 0:
            self._type_combo.setCurrentIndex(index)
        self._enabled_checkbox.setChecked(self._working.enabled)
        self._base_url_edit.setText(self._working.base_url or "")
        self._api_key_edit.setText(self._working.api_key_raw or "")
        self._refresh_run_button_state()

    def _on_name_changed(self, text: str) -> None:
        trimmed = text.strip()
        persisted_match = self._gateway.get_provider_by_name(trimmed) if trimmed else None
        conflict = duplicate_name_conflict(
            name=text,
            editing_provider_id=None if self._is_new else self._working.provider_id,
            other_working_names=self._existing_names,
            persisted_match_provider_id=(
                persisted_match.provider_id if persisted_match is not None else None
            ),
        )
        self._name_error_label.setText(DUPLICATE_NAME_MESSAGE if conflict else "")
        self._refresh_save_button_state()

    def _on_api_key_changed(self, text: str) -> None:
        self._api_key_error_label.setText(env_var_name_error(text) or "")
        resolved = bool(text) and bool(os.environ.get(text))
        self._api_key_diagnostic_label.setText(env_var_diagnostic(name=text, resolved=resolved))
        self._refresh_save_button_state()

    def _refresh_save_button_state(self) -> None:
        """Combine the Name-uniqueness (§9; AC-3) and API-key entry-validation
        (§5.1; AC-2) findings into the Save button's enabled state."""
        name_ok = bool(self._name_edit.text().strip()) and not self._name_error_label.text()
        api_key_ok = env_var_name_error(self._api_key_edit.text()) is None
        self._save_button.setEnabled(name_ok and api_key_ok)

    def _on_manual_entry_toggled(self, checked: bool) -> None:  # noqa: FBT001  # Qt's own toggled(bool) signal signature
        self._model_stack.setCurrentWidget(
            self._manual_model_edit if checked else self._model_dropdown
        )
        self._refresh_run_button_state()

    def _on_test_inference_toggled(self) -> None:
        self._inference_panel.setVisible(not self._inference_panel.isVisible())
        self._refresh_run_button_state()

    def _dropdown_model(self) -> str | None:
        text = self._model_dropdown.currentText()
        return text or None

    def _refresh_run_button_state(self) -> None:
        gate_enabled, gate_tooltip = gate_button_state(self._gate_activity)
        self._test_reachability_button.setEnabled(gate_enabled)
        self._test_reachability_button.setToolTip(gate_tooltip)
        self._test_inference_button.setEnabled(gate_enabled)
        self._test_inference_button.setToolTip(gate_tooltip)
        is_cloud = self._working.provider_type is not ProviderType.OPENAI_COMPATIBLE or bool(
            self._working.base_url and "localhost" not in self._working.base_url
        )
        self._billing_warning_label.setVisible(is_cloud and self._inference_panel.isVisible())
        enabled, tooltip = run_inference_test_enabled(
            dropdown_model=self._dropdown_model(),
            manual_entry_enabled=self._manual_entry_checkbox.isChecked(),
            manual_text=self._manual_model_edit.text(),
            gate_activity=self._gate_activity,
        )
        self._run_inference_button.setEnabled(enabled)
        self._run_inference_button.setToolTip(tooltip)

    def _on_inference_activity_changed(self, payload: object) -> None:
        if not isinstance(payload, InferenceActivityChangedEvent):
            return
        self._gate_activity = payload.state.current
        self._refresh_run_button_state()

    def _on_test_reachability_clicked(self) -> None:
        logger.debug(
            "provider_edit_test_reachability_clicked", provider_id=self._working.provider_id
        )
        result = self._gateway.test_provider(self._working.provider_id, "")
        self._result_label.setText(f"Test reachability — {result.outcome.value}")

    def _on_run_inference_clicked(self) -> None:
        model_name = (
            self._manual_model_edit.text().strip()
            if self._manual_entry_checkbox.isChecked()
            else (self._dropdown_model() or "")
        )
        logger.debug(
            "provider_edit_run_inference_clicked",
            provider_id=self._working.provider_id,
            model_name=model_name,
        )
        result = self._gateway.test_provider(self._working.provider_id, model_name)
        self._result_label.setText(f"Test inference — {result.outcome.value} — {model_name}")

    def _on_save_clicked(self) -> None:
        trimmed_name = self._name_edit.text().strip()
        if not trimmed_name or self._name_error_label.text():
            return
        if env_var_name_error(self._api_key_edit.text()) is not None:
            return
        provider_type = ProviderType(self._type_combo.currentData())
        base_url = self._base_url_edit.text().strip() or None
        if provider_type is ProviderType.OPENAI_COMPATIBLE and not base_url:
            self._result_label.setText("Base URL is required for this provider type.")
            return
        self.result_config = msgspec.structs.replace(
            self._working,
            name=trimmed_name,
            provider_type=provider_type,
            enabled=self._enabled_checkbox.isChecked(),
            base_url=base_url,
            api_key_raw=self._api_key_edit.text() or None,
        )
        logger.debug("provider_edit_save_clicked", provider_id=self.result_config.provider_id)
        self._activity_subscription.cancel()
        self.accept()

    @override
    def reject(self) -> None:  # Qt override
        """Discard the form; the Providers tab table model is unchanged."""
        self._activity_subscription.cancel()
        super().reject()


def make_provider_edit_dialog(
    *,
    collaborators: ProviderEditCollaborators,
    config: ProviderConfig | None,
    existing_names: tuple[str, ...],
    parent: QWidget | None = None,
) -> ProviderEditDialog:
    """Construct the Provider Edit sub-dialog.

    Args:
        collaborators: The sub-dialog's ``SettingsGateway`` and ``EventBus``
            (D-R-06; coding-style.md's 4-parameter rule).
        config: The row's working copy to populate from, or ``None`` for a
            blank Add-Provider draft (§1).
        existing_names: Every other working row's current Name, for the live
            duplicate-name check (§9).
        parent: The dialog's parent widget, if any.

    Returns:
        The constructed, unshown ``ProviderEditDialog``. Its ``result_config``
        attribute is ``None`` until a successful Save.
    """
    return ProviderEditDialog(
        collaborators=collaborators, config=config, existing_names=existing_names, parent=parent
    )
