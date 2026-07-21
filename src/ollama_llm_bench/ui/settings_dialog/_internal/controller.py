"""``SettingsController`` -- the dialog shell's chrome state, the auto-check-on-open
readiness request, and the ``_app_readiness_changed`` subscription
(``description.md`` §14; STORY-066-AC-7).

Depends only on ``SettingsGateway`` plus ``EventBus`` and ``NotificationService``
(D-R-06) -- no backend Store/Service Protocol reaches this controller.
"""

from typing import Protocol

import structlog

from ollama_llm_bench.backend.events import (
    SIGNAL_APP_READINESS_CHANGED,
    AppReadinessChangedEvent,
    EventBus,
)
from ollama_llm_bench.ui.settings_dialog._internal.providers_tab.controller import (
    ProvidersTabController,
)
from ollama_llm_bench.ui.settings_dialog._internal.view_model_select import (
    select_dialog_chrome_view_model,
)
from ollama_llm_bench.ui.settings_dialog.models import DialogChromeViewModel
from ollama_llm_bench.ui.settings_dialog.protocols import SettingsGateway

__all__: list[str] = ["SettingsController"]

logger = structlog.get_logger(__name__)


class _ChromeApplier(Protocol):
    """Structural view of the dialog shell's public ``apply_chrome`` method.

    Declared locally rather than importing ``_internal.view.SettingsDialogView``
    -- that module imports this one to build ``SettingsController``, so a
    concrete-type import here would be a cycle.
    """

    def apply_chrome(self, chrome: DialogChromeViewModel) -> None: ...


class SettingsController:
    """Owns the Settings dialog's chrome state and the auto-check-on-open request."""

    def __init__(
        self,
        *,
        gateway: SettingsGateway,
        event_bus: EventBus,
        providers_controller: ProvidersTabController,
    ) -> None:
        self._gateway = gateway
        self._event_bus = event_bus
        self.providers_controller = providers_controller
        self._view: _ChromeApplier | None = None
        logger.debug("settings_controller_constructed")

    def bind_view(self, view: _ChromeApplier) -> None:
        """Subscribe to the Event Bus, owner-bound to the dialog's lifetime."""
        self._view = view
        self._event_bus.subscribe(
            SIGNAL_APP_READINESS_CHANGED, self._on_readiness_changed, owner=view
        )

    def load(self) -> None:
        """Enter the Opening state: load the provider catalog and request the
        auto-check-on-open readiness refresh (§14; STORY-066-AC-7)."""
        self.providers_controller.reload()
        self._gateway.probe_all()
        self._push_chrome()
        logger.debug("settings_dialog_opening_probe_all_requested")

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
        chrome = select_dialog_chrome_view_model(dirty=self.providers_controller.is_dirty)
        if self._view is not None:
            self._view.apply_chrome(chrome)
