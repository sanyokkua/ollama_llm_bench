"""Public factory for ``ui/settings_dialog/`` (STORY-066).

Source of truth: ``docs/v3_specification/06_Settings_Dialog/description.md``,
``06_Settings_Dialog/implementation_structure.md`` §2, §6;
``08_Cross_Cutting/08-E_interfaces_contracts.md`` §7b.6. ``compose.py`` wiring is
explicitly out of scope for this story (Phase 11 owns it) -- this factory only
declares the collaborators a later composition-root story wires.
"""

import icontract
import msgspec
from PySide6.QtWidgets import QDialog, QWidget

from ollama_llm_bench.adapters.clipboard import Clipboard
from ollama_llm_bench.adapters.file_system_actions import FileSystemActions
from ollama_llm_bench.adapters.native_pickers import NativePickers
from ollama_llm_bench.adapters.notification_service import NotificationService
from ollama_llm_bench.backend.events import EventBus
from ollama_llm_bench.ui.settings_dialog._internal.controller import SettingsController
from ollama_llm_bench.ui.settings_dialog._internal.providers_tab.controller import (
    ProvidersTabController,
)
from ollama_llm_bench.ui.settings_dialog._internal.providers_tab.embedding_section import (
    EmbeddingSectionWidget,
)
from ollama_llm_bench.ui.settings_dialog._internal.providers_tab.view import ProvidersTabWidget
from ollama_llm_bench.ui.settings_dialog._internal.view import SettingsDialogView
from ollama_llm_bench.ui.settings_dialog.models import EmbeddingSectionCollaborators
from ollama_llm_bench.ui.settings_dialog.protocols import SettingsGateway
from ollama_llm_bench.ui.theme import PlatformKind, ThemeManager

__all__: list[str] = ["SettingsDialogCollaborators", "make_settings_dialog"]


class SettingsDialogCollaborators(msgspec.Struct, frozen=True, kw_only=True, gc=False):
    """Bundles ``make_settings_dialog``'s collaborators (coding-style.md's
    4-parameter hard maximum) -- one field per Protocol the module inventory
    row for ``ui/settings_dialog/`` names (``EventBus``, ``NotificationService``,
    ``NativePickers``, ``Clipboard``, ``FileSystemActions``), even though this
    story's controller and sub-dialog actively call only ``EventBus`` and
    ``NotificationService`` -- the other three are retained collaborators
    STORY-067's General tab (Open-folder buttons, Export/Import pickers,
    Copy-path) uses without re-touching this factory's signature.

    Attributes:
        gateway: The dialog's own ``SettingsGateway`` (D-R-06).
        event_bus: Emits ``_provider_registry_reloaded``/``_app_settings_changed``
            (STORY-067); subscribed to ``_app_readiness_changed`` this story.
        native_pickers: The Export save picker / Import file picker (STORY-067).
        clipboard: The Copy App-folder-path action (STORY-067).
        file_system_actions: The three Open-folder buttons (STORY-067).
        notifications: The save/export/import/reset toasts and the row-level
            Test-connection gate-busy warning (STORY-066-AC-6).
        theme_manager: Resolves theme roles for the Health Dot / Auth badge /
            row-action delegates.
        platform_kind: The host platform classification passed alongside
            ``theme_manager`` to every themed custom-painted primitive.
    """

    gateway: SettingsGateway
    event_bus: EventBus
    native_pickers: NativePickers
    clipboard: Clipboard
    file_system_actions: FileSystemActions
    notifications: NotificationService
    theme_manager: ThemeManager | None = None
    platform_kind: PlatformKind = PlatformKind.UNKNOWN


@icontract.require(
    lambda collaborators: all(
        c is not None
        for c in (
            collaborators.gateway,
            collaborators.event_bus,
            collaborators.native_pickers,
            collaborators.clipboard,
            collaborators.file_system_actions,
            collaborators.notifications,
        )
    ),
    "every collaborator is required, wired by a later composition-root story",
)
@icontract.ensure(lambda result: isinstance(result, QDialog))
def make_settings_dialog(
    *, collaborators: SettingsDialogCollaborators, parent: QWidget | None = None
) -> QDialog:
    """Build the Settings Dialog as a modal ``QDialog``, fully wired, ready to
    ``exec()`` (§2, §6, §14).

    Constructs the controller, the dialog shell, the Providers tab, and the
    provider table model; wires the controller's Event Bus subscription
    owner-bound to the returned dialog; issues the auto-check-on-open
    ``probe_all()`` request; and returns the dialog. The General tab and the
    three modal sub-dialogs beyond Provider Edit (Reset confirmation, Import
    preview) are STORY-067's.

    Args:
        collaborators: Every collaborator this dialog and its controllers
            need, bundled per coding-style.md's 4-parameter hard maximum.
        parent: The Main Window the dialog is centred over, if any.

    Returns:
        The fully wired, modal ``QDialog``, opened into its ``Opening`` state.
    """
    providers_controller = ProvidersTabController(
        gateway=collaborators.gateway,
        event_bus=collaborators.event_bus,
        notifications=collaborators.notifications,
    )
    embedding_section = EmbeddingSectionWidget(
        collaborators=EmbeddingSectionCollaborators(
            provider_configs_source=collaborators.gateway.list_providers,
            discover_models=collaborators.gateway.discover_models,
            get_setting=collaborators.gateway.get_setting,
            probe_embedding=collaborators.gateway.probe_embedding,
            event_bus=collaborators.event_bus,
        )
    )
    providers_tab = ProvidersTabWidget(
        embedding_section=embedding_section,
        theme_manager=collaborators.theme_manager,
        platform_kind=collaborators.platform_kind,
    )
    providers_controller.bind(providers_tab)
    dialog = SettingsDialogView(providers_tab=providers_tab, parent=parent)
    controller = SettingsController(
        gateway=collaborators.gateway,
        event_bus=collaborators.event_bus,
        providers_controller=providers_controller,
    )
    controller.bind_view(dialog)
    controller.load()
    return dialog
