"""``SettingsController`` -- the dialog shell's chrome state, the auto-check-on-open
readiness request, the ``_app_readiness_changed`` subscription
(``description.md`` §14; STORY-066-AC-7), and the atomic Save / Export /
Import / Reset / Close transactions (STORY-067).

Depends only on ``SettingsGateway`` plus the retained UI collaborators
(``EventBus``, ``NativePickers``, ``Clipboard``, ``FileSystemActions``,
``NotificationService``) -- D-R-06 -- no backend Store/Service Protocol
reaches this controller. Cross-store atomicity is validate-first, not 2PC
(mirroring the established ``ImportExportServiceImpl`` precedent): every
transaction validates before either store write runs, then calls
``replace_providers`` followed by ``upsert_settings`` in sequence -- the real
cross-store commit is the concrete ``SettingsGateway``/store implementation's
responsibility (Phase 11), out of this story's scope.
"""

from datetime import UTC, datetime
from pathlib import Path
from typing import Protocol
import uuid

from PySide6.QtWidgets import QMessageBox
import structlog

from ollama_llm_bench.adapters.native_pickers.models import FilePickerOptions, SavePickerOptions
from ollama_llm_bench.backend.domain import ProviderConfig, ProviderType, SettingKey
from ollama_llm_bench.backend.errors import ConfigurationError, PersistenceError, TaskFileError
from ollama_llm_bench.backend.events import (
    SIGNAL_APP_READINESS_CHANGED,
    SIGNAL_APP_SETTINGS_CHANGED,
    SIGNAL_PROVIDER_REGISTRY_RELOADED,
    AppReadinessChangedEvent,
    AppSettingsChangedEvent,
    ProviderRegistryReloadedEvent,
)
from ollama_llm_bench.ui.settings_dialog._internal.general_tab.controller import (
    GeneralTabController,
)
from ollama_llm_bench.ui.settings_dialog._internal.providers_tab.controller import (
    ProvidersTabController,
)
from ollama_llm_bench.ui.settings_dialog._internal.sub_dialogs.import_preview_view import (
    make_provider_import_preview_dialog,
    make_settings_import_preview_dialog,
)
from ollama_llm_bench.ui.settings_dialog._internal.sub_dialogs.reset_confirmation_view import (
    make_reset_confirmation_dialog,
)
from ollama_llm_bench.ui.settings_dialog._internal.validation import save_enabled, validate_all
from ollama_llm_bench.ui.settings_dialog.models import (
    DialogChromeViewModel,
    GeneralFieldState,
    SettingsDialogCollaborators,
    Severity,
    ValidationFinding,
)

__all__: list[str] = ["SettingsController"]

logger = structlog.get_logger(__name__)

# The three bundled local providers re-seeded by Reset to Defaults
# (`sub_dialogs/reset_confirmation.md` §6) -- each carries a fresh session-
# local placeholder `provider_id`, mirroring `provider_edit_view._blank_draft`'s
# established pattern (the real store assigns the persisted UUID4 on write).
_BUNDLED_PROVIDER_SEEDS: tuple[tuple[str, str], ...] = (
    ("Ollama (local)", "http://localhost:11434/v1"),
    ("LM Studio (local)", "http://localhost:1234/v1"),
    ("llama.cpp (local)", "http://localhost:8080/v1"),
)


def _bundled_default_provider_drafts() -> tuple[ProviderConfig, ...]:
    """Build the three bundled local providers, freshly seeded (STORY-067-AC-5)."""
    return tuple(
        ProviderConfig(
            provider_id=str(uuid.uuid4()),
            name=name,
            provider_type=ProviderType.OPENAI_COMPATIBLE,
            base_url=base_url,
            enabled=False,
        )
        for name, base_url in _BUNDLED_PROVIDER_SEEDS
    )


class _ChromeApplier(Protocol):
    """Structural view of the dialog shell's public render methods.

    Declared locally rather than importing ``_internal.view.SettingsDialogView``
    -- that module imports this one to build ``SettingsController``, so a
    concrete-type import here would be a cycle.
    """

    def apply_chrome(self, chrome: DialogChromeViewModel) -> None: ...
    def push_general_field_states(self, states: tuple[GeneralFieldState, ...]) -> None: ...


class SettingsController:
    """Owns the Settings dialog's chrome state, the auto-check-on-open
    request, and the atomic Save/Export/Import/Reset/Close transactions."""

    def __init__(
        self,
        *,
        collaborators: SettingsDialogCollaborators,
        providers_controller: ProvidersTabController,
        general_tab_controller: GeneralTabController,
    ) -> None:
        self._gateway = collaborators.gateway
        self._event_bus = collaborators.event_bus
        self._native_pickers = collaborators.native_pickers
        self._clipboard = collaborators.clipboard
        self._file_system_actions = collaborators.file_system_actions
        self._notifications = collaborators.notifications
        self.providers_controller = providers_controller
        self._general_tab_controller = general_tab_controller
        self._view: _ChromeApplier | None = None
        logger.debug("settings_controller_constructed")

    def bind_view(self, view: "_ChromeApplier") -> None:
        """Subscribe to the Event Bus, owner-bound to the dialog's lifetime."""
        self._view = view
        self._event_bus.subscribe(
            SIGNAL_APP_READINESS_CHANGED, self._on_readiness_changed, owner=view
        )

    def load(self) -> None:
        """Enter the Opening state: load both tabs and request the
        auto-check-on-open readiness refresh (§14; STORY-066-AC-7)."""
        self.providers_controller.reload()
        self._general_tab_controller.reload()
        self._gateway.probe_all()
        self._push_chrome()
        logger.debug("settings_dialog_opening_probe_all_requested")

    @property
    def is_dirty(self) -> bool:
        """Whether either tab's working copy differs from its persisted value."""
        return self.providers_controller.is_dirty or self._general_tab_controller.is_dirty

    def _current_findings(self) -> tuple[ValidationFinding, ...]:
        return validate_all(
            providers=self.providers_controller.working_configs,
            general_values=self._general_tab_controller.values_for_save(),
        )

    def _on_readiness_changed(self, payload: object) -> None:
        if not isinstance(payload, AppReadinessChangedEvent):
            return
        logger.debug(
            "settings_controller_readiness_changed_received",
            embedding_reachable=payload.embedding_reachable,
        )
        self.providers_controller.apply_readiness_refresh()
        self.providers_controller.apply_embedding_diagnostic(reachable=payload.embedding_reachable)
        self._push_chrome()

    def _push_chrome(self) -> None:
        findings = self._current_findings()
        chrome = DialogChromeViewModel(
            providers_tab_label="Providers *"
            if self.providers_controller.is_dirty
            else "Providers",
            general_tab_label="General*" if self._general_tab_controller.is_dirty else "General",
            save_state_text="Unsaved changes" if self.is_dirty else "No changes",
            dirty=self.is_dirty,
            save_enabled=save_enabled(findings, is_dirty=self.is_dirty),
        )
        if self._view is not None:
            self._view.apply_chrome(chrome)
            self._view.push_general_field_states(self._general_field_states_with_errors(findings))

    def _general_field_states_with_errors(
        self, findings: tuple[ValidationFinding, ...]
    ) -> tuple[GeneralFieldState, ...]:
        hard_error_targets = {f.target for f in findings if f.severity is Severity.HARD_ERROR}
        return tuple(
            GeneralFieldState(
                setting_key=state.setting_key,
                value=state.value,
                has_error=state.setting_key in hard_error_targets,
            )
            for state in self._general_tab_controller.field_states()
        )

    def on_general_field_edited(self, setting_key: SettingKey, text: str) -> None:
        """Handle a General-tab control edit (STORY-067-AC-1): update the
        working copy and recompute chrome/validation."""
        self._general_tab_controller.set_value(setting_key, text)
        self._push_chrome()

    def on_copy_app_data_path_clicked(self) -> None:
        """Copy the resolved app-data path to the clipboard (§4.9)."""
        self._clipboard.copy_text(self._resolve_app_data_path())

    def on_open_app_folder_clicked(self) -> None:
        """Open ``<app_data>/`` in the OS file manager (§4.9, §11)."""
        self._file_system_actions.open_in_file_manager(self._resolve_app_data_path())

    def on_open_run_logs_folder_clicked(self) -> None:
        """Open ``<app_data>/logs/run/`` in the OS file manager (§4.7, §11)."""
        self._file_system_actions.open_in_file_manager(
            str(Path(self._resolve_app_data_path()) / "logs" / "run")
        )

    def on_open_app_logs_folder_clicked(self) -> None:
        """Open ``<app_data>/logs/app/`` in the OS file manager (§4.8, §11)."""
        self._file_system_actions.open_in_file_manager(
            str(Path(self._resolve_app_data_path()) / "logs" / "app")
        )

    def _resolve_app_data_path(self) -> str:
        """Derive ``<app_data>/`` from ``exports_folder_path()``'s parent
        (STORY-067's Notes: no dedicated Gateway/Protocol method returns the
        app-data root directly)."""
        return str(Path(self._file_system_actions.exports_folder_path()).parent)

    def on_save_clicked(self) -> None:
        """Commit both tabs atomically through the Gateway (§6; STORY-067-AC-3)."""
        findings = self._current_findings()
        if not save_enabled(findings, is_dirty=self.is_dirty):
            logger.debug("settings_save_blocked", finding_count=len(findings))
            return
        try:
            self._gateway.replace_providers(self.providers_controller.working_configs)
            self._gateway.upsert_settings(self._general_tab_controller.values_for_save())
        except PersistenceError as exc:
            logger.warning("settings_save_failed", error=str(exc))
            self._notifications.show_error("Settings could not be saved.")
            return
        self._emit_commit_events(reload_cause="save")
        self.providers_controller.reload()
        self._general_tab_controller.reload()
        self._notifications.show_info("Settings saved")
        logger.debug("settings_saved")
        self._push_chrome()

    def on_export_clicked(self) -> None:
        """Write the current configuration to a user-chosen YAML file (§7)."""
        options = SavePickerOptions(
            title="Export Settings",
            suggested_name=f"ollama_bench_settings_{datetime.now(UTC).date().isoformat()}.yaml",
            filters=("YAML (*.yaml *.yml)",),
        )
        path = self._native_pickers.save_file(options)
        if path is None:
            return
        payload = self._gateway.export_settings()
        self._file_system_actions.write_text_file(path=path, content=payload.decode("utf-8"))
        self._notifications.show_info(f"Exported to {path}")
        logger.debug("settings_exported", path=path)

    def on_import_clicked(self) -> None:
        """Parse, preview, and apply a settings-import YAML file (§8; STORY-067-AC-4)."""
        paths = self._native_pickers.open_file(
            FilePickerOptions(
                title="Import Settings", filters=("YAML (*.yaml *.yml)",), allow_multiple=False
            )
        )
        if not paths:
            return
        try:
            preview = self._gateway.build_settings_import_preview(paths[0])
        except (TaskFileError, ConfigurationError) as exc:
            self._notifications.show_error(f"Import failed: {exc}")
            return
        preview_dialog = make_settings_import_preview_dialog(preview=preview)
        preview_dialog.exec()
        if not preview_dialog.confirmed:
            return
        self._gateway.apply_settings_import(preview)
        self._emit_settings_changed(changed_keys=tuple(preview.resolved_values))
        self._general_tab_controller.reload()
        self._notifications.show_info("Settings imported")
        logger.debug("settings_imported")
        self._push_chrome()

    def on_import_provider_config_clicked(self) -> None:
        """Parse, preview, and apply a provider-configuration import file (§8)."""
        paths = self._native_pickers.open_file(
            FilePickerOptions(
                title="Import Provider Configuration",
                filters=("YAML (*.yaml *.yml)",),
                allow_multiple=False,
            )
        )
        if not paths:
            return
        try:
            preview = self._gateway.build_provider_import_preview(paths[0])
        except (TaskFileError, ConfigurationError) as exc:
            self._notifications.show_error(f"Import failed: {exc}")
            return
        preview_dialog = make_provider_import_preview_dialog(preview=preview)
        preview_dialog.exec()
        if not preview_dialog.confirmed:
            return
        self._gateway.apply_provider_import(preview)
        self._emit_registry_reloaded(provider_count=len(preview.rows), reload_cause="import")
        self.providers_controller.reload()
        self._notifications.show_info("Provider configuration imported")
        logger.debug("provider_config_imported")
        self._push_chrome()

    def on_reset_clicked(self) -> None:
        """Wipe and re-seed the whole configuration on confirm (§9; STORY-067-AC-5)."""
        confirmation_dialog = make_reset_confirmation_dialog()
        confirmation_dialog.exec()
        if not confirmation_dialog.confirmed:
            return
        bundled_providers = _bundled_default_provider_drafts()
        self._gateway.replace_providers(bundled_providers)
        self._gateway.upsert_settings(
            self._general_tab_controller.values_for_reset_defaults()
            | {"embedding.selected_provider_name": "", "embedding.selected_model_name": ""}
        )
        self._emit_registry_reloaded(provider_count=len(bundled_providers), reload_cause="reset")
        self._emit_settings_changed(
            changed_keys=(
                *self._general_tab_controller.values_for_reset_defaults(),
                "embedding.selected_provider_name",
                "embedding.selected_model_name",
            )
        )
        self.providers_controller.reload()
        self._general_tab_controller.reload()
        self._notifications.show_info("Settings reset to defaults")
        logger.debug("settings_reset")
        self._push_chrome()

    def on_close_requested(self) -> bool:
        """Whether the dialog should actually close now (§10; STORY-067-AC-6)."""
        if not self.is_dirty:
            return True
        return self._confirm_discard_changes()

    def _confirm_discard_changes(self) -> bool:
        message_box = QMessageBox()
        message_box.setWindowTitle("Discard changes?")
        message_box.setText("You have unsaved changes. Discard them and close?")
        discard_button = message_box.addButton("Discard", QMessageBox.ButtonRole.DestructiveRole)
        message_box.addButton("Cancel", QMessageBox.ButtonRole.RejectRole)
        message_box.exec()
        return message_box.clickedButton() is discard_button

    def _emit_commit_events(self, *, reload_cause: str) -> None:
        self._emit_registry_reloaded(
            provider_count=len(self.providers_controller.working_configs), reload_cause=reload_cause
        )
        self._emit_settings_changed(
            changed_keys=tuple(self._general_tab_controller.values_for_save())
        )

    def _emit_registry_reloaded(self, *, provider_count: int, reload_cause: str) -> None:
        self._event_bus.emit(
            SIGNAL_PROVIDER_REGISTRY_RELOADED,
            ProviderRegistryReloadedEvent(
                provider_count=provider_count,
                enabled_provider_ids=tuple(
                    p.provider_id for p in self.providers_controller.working_configs if p.enabled
                ),
                reload_cause=reload_cause,
            ),
        )

    def _emit_settings_changed(self, *, changed_keys: tuple[str, ...]) -> None:
        self._event_bus.emit(
            SIGNAL_APP_SETTINGS_CHANGED, AppSettingsChangedEvent(changed_keys=changed_keys)
        )
