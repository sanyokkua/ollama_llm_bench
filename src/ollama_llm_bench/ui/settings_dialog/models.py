"""Frozen ViewModel structs + view-only enums for ``ui/settings_dialog/`` (STORY-066).

Source of truth: ``docs/v3_specification/06_Settings_Dialog/implementation_structure.md``
§4 -- the subset this story delivers (the Providers tab row shape and the dialog
chrome). The full ``SettingsViewModel`` (General tab fields, validation findings,
app-data path) is STORY-067's -- it owns the General tab and the Save/Import/Reset
transactions this story explicitly leaves out of scope.
"""

from collections.abc import Callable
from enum import StrEnum

import msgspec

from ollama_llm_bench.backend.domain import (
    AppReadinessSnapshot,
    ModelName,
    ProviderConfig,
    ProviderId,
    ProviderTestStatus,
    ProviderType,
    SettingKey,
)
from ollama_llm_bench.backend.events import EventBus
from ollama_llm_bench.ui.settings_dialog.protocols import SettingsGateway

__all__: list[str] = [
    "DialogChromeViewModel",
    "EmbeddingSectionCollaborators",
    "ProviderEditCollaborators",
    "ProviderRow",
    "SettingsTab",
]


class SettingsTab(StrEnum):
    """The dialog's two tabs (``description.md`` §2). Only ``PROVIDERS`` has
    content this story -- ``GENERAL`` is STORY-067's."""

    PROVIDERS = "providers"
    GENERAL = "general"


class ProviderRow(msgspec.Struct, frozen=True, kw_only=True, gc=False):
    """One Providers-tab row (``description.md`` §3.2).

    Attributes:
        provider_id: The row's identity -- the persisted UUID4, or a
            session-local placeholder for a row added this session and never
            saved (never displayed; carried only for lookup).
        label: ``ProviderConfig.name`` -- the sortable, user-facing column.
        provider_type: Selects which secret-card set the Edit sub-dialog shows.
        base_url_display: The resolved URL, ``"(default)"``, or the resolved
            Azure endpoint URL.
        auth_badge: One of ``"env ✓"``/``"env ✗"``/``"none"`` (§3.2).
        health: The most recent ``ProviderTestStatus`` driving the Health Dot.
        enabled: Bound to ``ProviderConfig.enabled``; toggling marks the
            dialog dirty.
        has_unsaved_edits: Whether this row differs from the value last
            loaded from ``SettingsGateway.list_providers()``.
        is_session_added: Whether this row was added this session and never
            persisted.
    """

    provider_id: str
    label: str
    provider_type: ProviderType
    base_url_display: str
    auth_badge: str
    health: ProviderTestStatus
    enabled: bool
    has_unsaved_edits: bool
    is_session_added: bool


class ProviderEditCollaborators(msgspec.Struct, frozen=True, kw_only=True, gc=False):
    """Dependency bundle for ``make_provider_edit_dialog`` (coding-style.md's
    4-parameter hard maximum -- the factory would otherwise take 5 keyword
    arguments across ``gateway``/``event_bus``/``config``/``existing_names``/
    ``parent``).

    Attributes:
        gateway: The Provider Edit sub-dialog's own ``SettingsGateway``
            (D-R-06) -- ``get_provider_by_name`` (live duplicate-name check)
            and ``test_provider`` (Test reachability / Test inference).
        event_bus: Subscribed to ``_inference_activity_changed`` to gate the
            Test reachability / Test inference buttons (§8.4).
    """

    gateway: SettingsGateway
    event_bus: EventBus


class EmbeddingSectionCollaborators(msgspec.Struct, frozen=True, kw_only=True, gc=False):
    """Dependency bundle for ``EmbeddingSectionWidget`` (coding-style.md's
    4-parameter hard maximum -- the widget would otherwise take 5 keyword
    arguments across ``provider_configs_source``/``discover_models``/
    ``get_setting``/``probe_embedding``/``event_bus``).

    The widget takes plain bound callables rather than the whole
    ``SettingsGateway`` (D-R-06 local-shim pattern, matching
    ``ui.new_benchmark._internal.judge_section``'s established shape) -- it
    never holds the Gateway Protocol itself, only the five collaborators it
    actually calls.

    Attributes:
        provider_configs_source: Reads the working provider catalog for the
            provider dropdown and the first-start embedding bootstrap search.
        discover_models: Discovers one provider's model list, for the model
            dropdown and the first-start embedding bootstrap search.
        get_setting: Reads a persisted setting value -- used to read
            ``embedding.selected_provider_name`` / ``embedding.selected_model_name``
            at construction time (§1.4, §3.4).
        probe_embedding: Runs the user-initiated Test Embedding probe (§3.4).
        event_bus: Rebuilds the provider dropdown on registry reload and gates
            the Test Embedding button on ``_inference_activity_changed`` (§13).
    """

    provider_configs_source: Callable[[], tuple[ProviderConfig, ...]]
    discover_models: Callable[[ProviderId], tuple[ModelName, ...]]
    get_setting: Callable[[SettingKey], str | None]
    probe_embedding: Callable[[], AppReadinessSnapshot]
    event_bus: EventBus


class DialogChromeViewModel(msgspec.Struct, frozen=True, kw_only=True, gc=False):
    """The dialog shell's chrome state (``description.md`` §2).

    Attributes:
        providers_tab_label: ``"Providers"``, or ``"Providers *"`` while dirty.
        save_state_text: The footer save-state indicator's text.
        dirty: Whether any working-copy field differs from its persisted value.
    """

    providers_tab_label: str
    save_state_text: str
    dirty: bool
