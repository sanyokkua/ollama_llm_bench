"""Public factory for ``ui/settings_dialog/`` (STORY-066).

Source of truth: ``docs/v3_specification/06_Settings_Dialog/description.md``,
``06_Settings_Dialog/implementation_structure.md`` §2, §6;
``08_Cross_Cutting/08-E_interfaces_contracts.md`` §7b.6. ``compose.py`` wiring is
explicitly out of scope for this story (Phase 11 owns it) -- this factory only
declares the collaborators a later composition-root story wires.
"""

import icontract
from PySide6.QtWidgets import QDialog, QWidget

from ollama_llm_bench.ui.settings_dialog._internal.controller import SettingsController
from ollama_llm_bench.ui.settings_dialog._internal.general_tab.controller import (
    GeneralTabController,
)
from ollama_llm_bench.ui.settings_dialog._internal.providers_tab.controller import (
    ProvidersTabController,
)
from ollama_llm_bench.ui.settings_dialog._internal.providers_tab.embedding_section import (
    EmbeddingSectionWidget,
)
from ollama_llm_bench.ui.settings_dialog._internal.providers_tab.view import ProvidersTabWidget
from ollama_llm_bench.ui.settings_dialog._internal.view import SettingsDialogView
from ollama_llm_bench.ui.settings_dialog.models import (
    EmbeddingSectionCollaborators,
    SettingsDialogCollaborators,
)

__all__: list[str] = ["SettingsDialogCollaborators", "make_settings_dialog"]


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
    general_tab_controller = GeneralTabController(gateway=collaborators.gateway)
    dialog = SettingsDialogView(providers_tab=providers_tab, parent=parent)
    controller = SettingsController(
        collaborators=collaborators,
        providers_controller=providers_controller,
        general_tab_controller=general_tab_controller,
    )
    controller.bind_view(dialog)
    dialog._controller = controller
    controller.load()
    return dialog
