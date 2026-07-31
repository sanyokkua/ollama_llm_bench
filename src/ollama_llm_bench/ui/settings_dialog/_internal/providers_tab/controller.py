"""``ProvidersTabController`` -- owns the Providers tab's in-memory working
provider catalog, the per-row actions, and the table model built from it
(``description.md`` §3.2, §3.3; STORY-066-AC-1, AC-6).

Depends only on ``SettingsGateway`` plus ``NotificationService`` (D-R-06) -- no
backend Store/Service Protocol reaches this controller. Opening the Provider
Edit sub-dialog is a deferred import (matching
``ui.resume_benchmark._internal.controller``'s established precedent for
``ui.common_dialogs``) to avoid a module-import-order cycle between the two
sibling sub-packages.
"""

from collections.abc import Callable
import functools
import os

import msgspec
from PySide6.QtCore import QPoint
from PySide6.QtGui import QAction
from PySide6.QtWidgets import QDialog, QMenu
import structlog

from ollama_llm_bench.adapters.notification_service import NotificationService
from ollama_llm_bench.adapters.qt_table_models import make_providers_table_model
from ollama_llm_bench.adapters.qt_table_models.models import ProviderTableRow
from ollama_llm_bench.backend.domain import (
    InferenceTestResult,
    ProviderConfig,
    ProviderTestStatus,
)
from ollama_llm_bench.backend.events import EventBus
from ollama_llm_bench.ui.settings_dialog._internal.providers_tab.view import ProvidersTabWidget
from ollama_llm_bench.ui.settings_dialog._internal.view_model_select import (
    embedding_diagnostic_text,
    inference_test_outcome_to_provider_status,
    merge_probe_fields,
    provider_config_to_row,
)
from ollama_llm_bench.ui.settings_dialog.models import ProviderEditCollaborators, ProviderRow
from ollama_llm_bench.ui.settings_dialog.protocols import SettingsGateway

__all__: list[str] = ["ProvidersTabController"]

logger = structlog.get_logger(__name__)

_GATE_BUSY_MESSAGE = "Another inference activity is in flight — please wait."


def _api_key_resolves(config: ProviderConfig) -> bool:
    """Whether `config`'s credential env-var name currently resolves to a
    non-empty value (§12; STORY-066 spec-conformance fix) -- the established
    ``os.environ.get`` pattern already used by
    ``sub_dialogs.provider_edit_view``'s API-key diagnostic and
    ``backend.provider_registry``'s client builder."""
    return bool(config.api_key_raw) and bool(os.environ.get(config.api_key_raw or ""))


def _to_table_row(row: ProviderRow) -> ProviderTableRow:
    return ProviderTableRow(
        provider_id=row.provider_id,
        label=row.label,
        provider_type=row.provider_type,
        base_url_display=row.base_url_display,
        auth_badge=row.auth_badge,
        health=row.health,
        enabled=row.enabled,
    )


def _build_row_menu(*, parent: ProvidersTabWidget, has_unsaved_edits: bool) -> QMenu:
    menu = QMenu(parent)
    edit_action = QAction("Edit", menu)
    edit_action.setObjectName("action_edit")
    menu.addAction(edit_action)
    reset_action = QAction("Reset this provider", menu)
    reset_action.setObjectName("action_reset")
    reset_action.setEnabled(has_unsaved_edits)
    if not has_unsaved_edits:
        reset_action.setToolTip("No unsaved edits to revert")
    menu.addAction(reset_action)
    delete_action = QAction("Delete", menu)
    delete_action.setObjectName("action_delete")
    delete_action.setProperty("actionTone", "error")
    menu.addAction(delete_action)
    return menu


class ProvidersTabController:
    """Owns the Providers tab's working provider catalog and per-row actions."""

    def __init__(
        self,
        *,
        gateway: SettingsGateway,
        event_bus: EventBus,
        notifications: NotificationService,
    ) -> None:
        self._gateway = gateway
        self._event_bus = event_bus
        self._notifications = notifications
        self._configs: tuple[ProviderConfig, ...] = ()
        self._original_by_id: dict[str, ProviderConfig] = {}
        self._session_added_ids: set[str] = set()
        self.table_model = make_providers_table_model(rows=())
        self._view: ProvidersTabWidget | None = None
        self._on_changed: Callable[[], None] = lambda: None
        logger.debug("providers_tab_controller_constructed")

    def set_on_changed(self, callback: Callable[[], None]) -> None:
        """Register a callback invoked after every working-catalog mutation
        (spec-conformance fix): wired by ``api.py`` to the parent
        ``SettingsController.on_providers_changed`` so the dialog chrome
        (dirty asterisk, save-state text, Save-button enablement) stays live
        after a Providers-tab-only change, without requiring an unrelated
        General-tab edit to trigger the next chrome push."""
        self._on_changed = callback

    @property
    def is_dirty(self) -> bool:
        """Whether the working catalog differs from what was last loaded."""
        if self._session_added_ids:
            return True
        return any(
            config != self._original_by_id.get(config.provider_id) for config in self._configs
        ) or len(self._configs) != len(self._original_by_id)

    @property
    def working_configs(self) -> tuple[ProviderConfig, ...]:
        """The current in-memory provider catalog (STORY-067 Save/Reset/
        validation read this to assemble the atomic-transaction payload)."""
        return self._configs

    def bind(self, view: ProvidersTabWidget) -> None:
        """Wire the view's Qt signals to this controller's handlers."""
        self._view = view
        view.add_clicked.connect(self.on_add_clicked)
        view.test_clicked.connect(self.on_test_clicked)
        view.edit_clicked.connect(self.on_edit_clicked)
        view.enabled_toggled.connect(self.on_enabled_toggled)
        view.more_clicked.connect(self.on_more_clicked)

    def reload(self) -> None:
        """Load the provider catalog fresh from the gateway (dialog Opening)."""
        configs = self._gateway.list_providers()
        self._configs = configs
        self._original_by_id = {c.provider_id: c for c in configs}
        self._session_added_ids = set()
        logger.debug("providers_tab_reloaded", provider_count=len(configs))
        self._rebuild()

    def apply_readiness_refresh(self) -> None:
        """Fold a fresh readiness-triggered re-read's probe fields onto the
        working catalog, preserving every other unsaved edit (STORY-066-AC-7)."""
        fresh_by_id = {c.provider_id: c for c in self._gateway.list_providers()}
        merged = tuple(
            merge_probe_fields(current=config, fresh=fresh_by_id[config.provider_id])
            if config.provider_id in fresh_by_id
            else config
            for config in self._configs
        )
        self._configs = merged
        logger.debug("providers_tab_readiness_refresh_applied")
        self._rebuild()

    def apply_embedding_diagnostic(self, *, reachable: bool) -> None:
        """Repaint the embedding section's diagnostic from the readiness
        snapshot's ``embedding_reachable`` flag (STORY-066-AC-7)."""
        if self._view is not None:
            self._view.embedding_section.set_diagnostic(
                embedding_diagnostic_text(embedding_reachable=reachable)
            )

    def on_test_clicked(self, view_row: int) -> None:
        """Run the row-level Test connection probe against the working copy (AC-6).

        Paints the row's health dot ``TESTING`` immediately; the real outcome
        is applied only when the gateway's ``on_complete`` callback fires
        (ADR-0015, STORY-110-AC-9).
        """
        config = self._configs[view_row]
        logger.debug("providers_tab_test_connection_clicked", provider_id=config.provider_id)
        previous_status = config.last_probe_status
        self._replace_config(
            msgspec.structs.replace(config, last_probe_status=ProviderTestStatus.TESTING)
        )
        self._gateway.test_provider(
            config.provider_id,
            "",
            on_complete=functools.partial(self._on_test_completed, view_row, previous_status),
        )

    def _on_test_completed(
        self,
        view_row: int,
        previous_status: ProviderTestStatus,
        result: InferenceTestResult,
    ) -> None:
        """Apply a deferred ``test_provider`` outcome, tolerating a row that
        moved or disappeared before the callback fired. A ``GATE_BUSY``
        outcome reverts the row to ``previous_status`` -- the probe never
        ran, so the optimistic ``TESTING`` paint must not stick."""
        if view_row >= len(self._configs):
            return
        config = self._configs[view_row]
        if config.provider_id != result.provider_id:
            return
        new_status = inference_test_outcome_to_provider_status(result.outcome)
        if new_status is None:
            self._notifications.show_warning(_GATE_BUSY_MESSAGE)
            self._replace_config(msgspec.structs.replace(config, last_probe_status=previous_status))
            return
        self._replace_config(msgspec.structs.replace(config, last_probe_status=new_status))

    def on_enabled_toggled(self, view_row: int) -> None:
        """Flip the row's working ``enabled`` flag (§3.2)."""
        config = self._configs[view_row]
        logger.debug("providers_tab_enabled_toggled", provider_id=config.provider_id)
        self._replace_config(msgspec.structs.replace(config, enabled=not config.enabled))

    def on_add_clicked(self) -> None:
        """Open a blank Provider Edit sub-dialog; append the row only on Save (§3.1)."""
        if self._view is None:
            return
        from ollama_llm_bench.ui.settings_dialog._internal.sub_dialogs.provider_edit_view import (  # noqa: PLC0415  # deferred: avoids a sibling-sub-package import-order cycle
            make_provider_edit_dialog,
        )

        existing_names = tuple(c.name for c in self._configs)
        dialog = make_provider_edit_dialog(
            collaborators=self._provider_edit_collaborators(),
            config=None,
            existing_names=existing_names,
            parent=self._view,
        )
        logger.debug("providers_tab_add_clicked")
        if dialog.exec() != QDialog.DialogCode.Accepted or dialog.result_config is None:
            return
        result = dialog.result_config
        self._configs = (*self._configs, result)
        self._session_added_ids.add(result.provider_id)
        self._rebuild()

    def on_edit_clicked(self, view_row: int) -> None:
        """Open the Provider Edit sub-dialog populated from the row's working copy (§3.3)."""
        if self._view is None:
            return
        from ollama_llm_bench.ui.settings_dialog._internal.sub_dialogs.provider_edit_view import (  # noqa: PLC0415  # deferred: avoids a sibling-sub-package import-order cycle
            make_provider_edit_dialog,
        )

        config = self._configs[view_row]
        existing_names = tuple(c.name for c in self._configs if c.provider_id != config.provider_id)
        dialog = make_provider_edit_dialog(
            collaborators=self._provider_edit_collaborators(),
            config=config,
            existing_names=existing_names,
            parent=self._view,
        )
        logger.debug("providers_tab_edit_clicked", provider_id=config.provider_id)
        if dialog.exec() != QDialog.DialogCode.Accepted or dialog.result_config is None:
            return
        self._replace_config(dialog.result_config)

    def on_reset_clicked(self, view_row: int) -> None:
        """Revert the row to its persisted value, or remove it if session-added (§3.3)."""
        config = self._configs[view_row]
        logger.debug("providers_tab_reset_clicked", provider_id=config.provider_id)
        if config.provider_id in self._session_added_ids:
            self._remove_config(config.provider_id)
            self._session_added_ids.discard(config.provider_id)
            return
        original = self._original_by_id.get(config.provider_id)
        if original is not None:
            self._replace_config(original)

    def on_delete_clicked(self, view_row: int) -> None:
        """Remove the row from the working catalog (§3.3)."""
        config = self._configs[view_row]
        logger.debug("providers_tab_delete_clicked", provider_id=config.provider_id)
        self._remove_config(config.provider_id)
        self._session_added_ids.discard(config.provider_id)

    def on_more_clicked(self, view_row: int, global_pos: QPoint) -> None:
        """Open the row's Edit / Reset / Delete overflow menu."""
        if self._view is None:
            return
        config = self._configs[view_row]
        row = provider_config_to_row(
            config=config,
            original=self._original_by_id.get(config.provider_id),
            is_session_added=config.provider_id in self._session_added_ids,
            api_key_resolves=_api_key_resolves(config),
        )
        menu = _build_row_menu(
            parent=self._view,
            has_unsaved_edits=row.has_unsaved_edits or row.is_session_added,
        )
        self._wire_row_menu(menu, view_row)
        menu.exec(global_pos)

    def _provider_edit_collaborators(self) -> ProviderEditCollaborators:
        return ProviderEditCollaborators(gateway=self._gateway, event_bus=self._event_bus)

    def _wire_row_menu(self, menu: QMenu, view_row: int) -> None:
        for action in menu.actions():
            if action.objectName() == "action_edit":
                action.triggered.connect(lambda: self.on_edit_clicked(view_row))
            elif action.objectName() == "action_reset":
                action.triggered.connect(lambda: self.on_reset_clicked(view_row))
            elif action.objectName() == "action_delete":
                action.triggered.connect(lambda: self.on_delete_clicked(view_row))

    def _replace_config(self, updated: ProviderConfig) -> None:
        self._configs = tuple(
            updated if c.provider_id == updated.provider_id else c for c in self._configs
        )
        self._rebuild()

    def _remove_config(self, provider_id: str) -> None:
        self._configs = tuple(c for c in self._configs if c.provider_id != provider_id)
        self._rebuild()

    def _rebuild(self) -> None:
        rows = tuple(
            provider_config_to_row(
                config=config,
                original=self._original_by_id.get(config.provider_id),
                is_session_added=config.provider_id in self._session_added_ids,
                api_key_resolves=_api_key_resolves(config),
            )
            for config in self._configs
        )
        self.table_model = make_providers_table_model(rows=tuple(_to_table_row(r) for r in rows))
        if self._view is not None:
            self._view.set_table_model(self.table_model)
        self._on_changed()
