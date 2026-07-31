"""Frozen ViewModel structs + view-only enums for ``ui/settings_dialog/`` (STORY-066,
extended by STORY-067).

Source of truth: ``docs/v3_specification/06_Settings_Dialog/implementation_structure.md``
§4 (Providers tab row shape and dialog chrome -- STORY-066); ``description.md`` §15
(validation severities/findings) and ``10_Domain_and_Data/06_IMPORT_FORMATS.md`` §8
(import-preview grouping -- STORY-067). The import-preview DTOs are declared *locally*
here, shaped after ``backend.import_export.models``'s real DTOs without importing that
package directly -- ``ui/*`` may not import ``backend/import_export`` (see the
STORY-067 plan's "Resolved design gap" section and the story's own Notes).
"""

from collections.abc import Callable
from enum import StrEnum

import msgspec

from ollama_llm_bench.adapters.clipboard import Clipboard
from ollama_llm_bench.adapters.file_system_actions import FileSystemActions
from ollama_llm_bench.adapters.native_pickers import NativePickers
from ollama_llm_bench.adapters.notification_service import NotificationService
from ollama_llm_bench.backend.domain import (
    ProviderConfig,
    ProviderTestStatus,
    ProviderType,
    SettingKey,
)
from ollama_llm_bench.backend.events import EventBus
from ollama_llm_bench.ui.settings_dialog.protocols import (
    DiscoverModelsCallable,
    ProbeEmbeddingCallable,
    SettingsGateway,
)
from ollama_llm_bench.ui.theme import PlatformKind, ThemeManager

__all__: list[str] = [
    "DialogChromeViewModel",
    "EmbeddingSectionCollaborators",
    "GeneralFieldState",
    "PreviewGroup",
    "ProviderEditCollaborators",
    "ProviderImportPreview",
    "ProviderImportPreviewRow",
    "ProviderImportResult",
    "ProviderRow",
    "SettingsDialogCollaborators",
    "SettingsImportPreview",
    "SettingsImportPreviewRow",
    "SettingsImportResult",
    "SettingsTab",
    "Severity",
    "ValidationFinding",
]


class Severity(StrEnum):
    """The three-severity model shared by validation findings and import previews
    (``description.md`` §15; ``10_Domain_and_Data/06_IMPORT_FORMATS.md`` §2)."""

    HARD_ERROR = "hard_error"
    SOFT_WARNING = "soft_warning"
    SOFT_INFO = "soft_info"


class ValidationFinding(msgspec.Struct, frozen=True, kw_only=True, gc=False):
    """One cross-tab validation result (``description.md`` §15)."""

    severity: Severity
    target: str
    message: str


class GeneralFieldState(msgspec.Struct, frozen=True, kw_only=True, gc=False):
    """The working state of one General-tab control."""

    setting_key: SettingKey
    value: str
    has_error: bool


class PreviewGroup(StrEnum):
    """The Import-preview grouping (``10_Domain_and_Data/06_IMPORT_FORMATS.md`` §8)."""

    ADDED = "added"
    CHANGED = "changed"
    UNCHANGED = "unchanged"
    SKIPPED = "skipped"


class SettingsImportPreviewRow(msgspec.Struct, frozen=True, kw_only=True, gc=False):
    """One setting key's proposed import outcome."""

    setting_key: SettingKey
    current_value: str | None
    imported_value: str | None
    group: PreviewGroup


class SettingsImportPreview(msgspec.Struct, frozen=True, kw_only=True, gc=False):
    """The full settings-import preview, locally shaped to mirror
    ``backend.import_export.models.SettingsImportPreview`` without importing it
    (``ui/*`` may not import ``backend/import_export`` -- see the story's Notes)."""

    rows: tuple[SettingsImportPreviewRow, ...]
    findings: tuple[ValidationFinding, ...]
    resolved_values: dict[SettingKey, str]


class SettingsImportResult(msgspec.Struct, frozen=True, kw_only=True, gc=False):
    """The applied/skipped counts after a confirmed settings import."""

    applied_count: int
    skipped_count: int


class ProviderImportPreviewRow(msgspec.Struct, frozen=True, kw_only=True, gc=False):
    """One provider entry's proposed import outcome."""

    name: str
    group: PreviewGroup


class ProviderImportPreview(msgspec.Struct, frozen=True, kw_only=True, gc=False):
    """The full provider-config-import preview, locally shaped to mirror
    ``backend.import_export.models.ProviderImportPreview`` (see the story's Notes)."""

    rows: tuple[ProviderImportPreviewRow, ...]
    embedding_provider_name: str | None
    embedding_model_name: str | None
    findings: tuple[ValidationFinding, ...]


class ProviderImportResult(msgspec.Struct, frozen=True, kw_only=True, gc=False):
    """The applied/skipped counts after a confirmed provider-config import."""

    applied_count: int
    skipped_count: int


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
            fast-synchronous: returns before discovery completes; delivers
            via ``on_complete`` (ADR-0015, STORY-110).
        get_setting: Reads a persisted setting value -- used to read
            ``embedding.selected_provider_name`` / ``embedding.selected_model_name``
            at construction time (§1.4, §3.4).
        probe_embedding: Runs the user-initiated Test Embedding probe (§3.4).
            fast-synchronous: returns before the probe completes. Reports its
            outcome two ways (ADR-0015, ADR-0016): the app-wide readiness
            state updates, and reaches this widget's subscription one level
            up, only when the check's result actually changed the cached
            snapshot; the widget's own ``on_complete`` keyword-only callback
            always fires exactly once with the check's definite boolean
            outcome, so this widget's own click always gets a terminal
            repaint even when nothing changed or the gate was busy.
        event_bus: Rebuilds the provider dropdown on registry reload and gates
            the Test Embedding button on ``_inference_activity_changed`` (§13).
    """

    provider_configs_source: Callable[[], tuple[ProviderConfig, ...]]
    discover_models: DiscoverModelsCallable
    get_setting: Callable[[SettingKey], str | None]
    probe_embedding: ProbeEmbeddingCallable
    event_bus: EventBus


class DialogChromeViewModel(msgspec.Struct, frozen=True, kw_only=True, gc=False):
    """The dialog shell's chrome state (``description.md`` §2).

    Attributes:
        providers_tab_label: ``"Providers"``, or ``"Providers *"`` while dirty.
        general_tab_label: ``"General"``, or ``"General*"`` while dirty (STORY-067).
        save_state_text: The footer save-state indicator's text.
        dirty: Whether any working-copy field differs from its persisted value.
        save_enabled: Whether Save Changes is enabled -- dirty and no hard
            validation error (STORY-067-AC-2).
    """

    providers_tab_label: str
    general_tab_label: str
    save_state_text: str
    dirty: bool
    save_enabled: bool


class SettingsDialogCollaborators(msgspec.Struct, frozen=True, kw_only=True, gc=False):
    """Bundles ``make_settings_dialog``'s collaborators (coding-style.md's
    4-parameter hard maximum) -- one field per Protocol the module inventory
    row for ``ui/settings_dialog/`` names. Declared here (not in ``api.py``) so
    ``_internal/controller.py`` can depend on it directly without an
    ``_internal`` -> ``..api`` import cycle (``project-structure.md``); ``api.py``
    re-exports it unchanged.

    Attributes:
        gateway: The dialog's own ``SettingsGateway`` (D-R-06).
        event_bus: Emits ``_provider_registry_reloaded``/``_app_settings_changed``
            (STORY-067); subscribed to ``_app_readiness_changed`` (STORY-066).
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
