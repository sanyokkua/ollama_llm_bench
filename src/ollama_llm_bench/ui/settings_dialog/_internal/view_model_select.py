"""Pure derivation functions for ``ui/settings_dialog/`` (STORY-066).

Zero Qt involvement -- directly unit-testable with no ``QApplication``. Source of
truth: ``docs/v3_specification/06_Settings_Dialog/description.md`` §3.2 (Health Dot
/ Auth badge table), §3.4 (embedding bootstrap), §12 (auth model), §13 (probe
outcomes), §14 (auto-check-on-open and embedding bootstrap); STORY-066-AC-1.

The Health Dot and the Auth badge are deliberately **two independent axes**
(spec-conformance fix): the Health Dot is a pure function of
``ProviderTestStatus`` alone (``provider_test_status_to_health``); the Auth
badge is a pure function of ``(api_key_env_var_name, resolves)`` alone
(``provider_auth_badge``) and never reads ``ProviderTestStatus`` -- a healthy
provider with no key field reads ``"none"`` and an unreachable provider with a
resolving key reads ``"env ✓"``.
"""

from collections.abc import Callable

import msgspec

from ollama_llm_bench.backend.domain import (
    InferenceTestOutcome,
    ModelName,
    ProviderConfig,
    ProviderId,
    ProviderTestStatus,
)
from ollama_llm_bench.backend.model_helpers import is_embedding_model
from ollama_llm_bench.ui.settings_dialog.models import DialogChromeViewModel, ProviderRow
from ollama_llm_bench.ui.theme import HealthDisplayState

__all__: list[str] = [
    "embedding_diagnostic_text",
    "find_provider_id_by_name",
    "inference_test_outcome_to_provider_status",
    "merge_probe_fields",
    "provider_auth_badge",
    "provider_config_to_row",
    "provider_test_status_to_health",
    "resolve_embedding_bootstrap_pair",
    "select_dialog_chrome_view_model",
]

_HEALTH_BY_STATUS: dict[ProviderTestStatus, HealthDisplayState] = {
    ProviderTestStatus.READY: HealthDisplayState.LIVE,
    ProviderTestStatus.ZERO_MODELS: HealthDisplayState.REACHABLE_NO_MODELS,
    ProviderTestStatus.UNREACHABLE: HealthDisplayState.DOWN,
    ProviderTestStatus.MISSING_ENV: HealthDisplayState.DOWN,
    ProviderTestStatus.UNTESTED: HealthDisplayState.NOT_TESTED,
    ProviderTestStatus.TESTING: HealthDisplayState.CHECKING,
}

_OUTCOME_TO_STATUS: dict[InferenceTestOutcome, ProviderTestStatus] = {
    InferenceTestOutcome.SUCCESS: ProviderTestStatus.READY,
    InferenceTestOutcome.AUTH_FAILED: ProviderTestStatus.MISSING_ENV,
    InferenceTestOutcome.REACHABILITY_FAILED: ProviderTestStatus.UNREACHABLE,
    InferenceTestOutcome.TIMEOUT: ProviderTestStatus.UNREACHABLE,
    InferenceTestOutcome.PROVIDER_ERROR: ProviderTestStatus.UNREACHABLE,
    InferenceTestOutcome.MODEL_NOT_FOUND: ProviderTestStatus.UNREACHABLE,
}

_PROBE_FIELD_NAMES: tuple[str, ...] = (
    "last_probe_status",
    "last_probe_at",
    "last_probe_reachable",
    "last_probe_model_count",
    "last_probe_message",
)


def provider_test_status_to_health(status: ProviderTestStatus) -> HealthDisplayState:
    """Map a provider's ``last_probe_status`` to its Health Dot state
    (``description.md`` §3.2 table; STORY-066-AC-1).

    Pure function of ``status`` alone. This axis is entirely independent of the
    Auth badge (``provider_auth_badge``) -- a provider's reachability and its
    credential-resolution state are two unrelated signals (spec-conformance fix).

    Args:
        status: The provider's most recent reachability probe status.

    Returns:
        The Health Dot display state to render.
    """
    return _HEALTH_BY_STATUS[status]


def provider_auth_badge(*, api_key_env_var_name: str | None, resolves: bool) -> str:
    """Derive the Auth badge from credential-resolution state alone
    (``description.md`` §3.2, §12; STORY-066-AC-1; spec-conformance fix).

    This is a pure function of ``(api_key_env_var_name, resolves)`` -- it never
    reads ``ProviderTestStatus``. A provider with no key field (the three
    bundled local providers) always reads ``"none"`` regardless of its Health
    Dot; a cloud provider whose key resolves reads ``"env ✓"`` even while its
    endpoint is ``UNREACHABLE``.

    Args:
        api_key_env_var_name: The provider's configured credential
            environment-variable name (``ProviderConfig.api_key_raw``), or
            ``None``/empty when the provider has no key field configured.
        resolves: Whether the named environment variable currently resolves to
            a non-empty value in the process environment. Ignored when
            `api_key_env_var_name` is empty.

    Returns:
        ``"none"`` when no name is configured; ``"env ✓"`` when a name is
        configured and resolves; ``"env ✗"`` when a name is configured but does
        not resolve.
    """
    if not api_key_env_var_name:
        return "none"
    return "env ✓" if resolves else "env ✗"


def inference_test_outcome_to_provider_status(
    outcome: InferenceTestOutcome,
) -> ProviderTestStatus | None:
    """Map a Test-connection ``InferenceTestResult.outcome`` to the row's new
    ``ProviderTestStatus`` (STORY-066-AC-6).

    Args:
        outcome: The outcome of the just-completed per-row Test connection probe.

    Returns:
        The status to paint onto the row's Health Dot, or ``None`` for
        ``GATE_BUSY`` -- the probe never ran, so the row's health is left
        unchanged (EC-PROV-5b's row-level analogue).
    """
    if outcome is InferenceTestOutcome.GATE_BUSY:
        return None
    return _OUTCOME_TO_STATUS[outcome]


def merge_probe_fields(*, current: ProviderConfig, fresh: ProviderConfig) -> ProviderConfig:
    """Fold `fresh`'s probe-result fields onto `current`, preserving every other
    unsaved working-copy edit (STORY-066-AC-7).

    A readiness refresh (`_app_readiness_changed`) re-reads the persisted
    catalog via `SettingsGateway.list_providers()`, which would otherwise
    silently discard a session-only edit (a renamed provider, a toggled
    Enabled flag) that never reached the persisted row. Only the probe-result
    columns are ever safe to overwrite from a fresh read, since those are
    exactly the fields the readiness probe itself just recomputed.

    Args:
        current: The working-copy row as currently displayed (with any local edits).
        fresh: The same provider's freshly re-read persisted row.

    Returns:
        `current` with only its probe-result fields replaced by `fresh`'s.
    """
    probe_updates = {name: getattr(fresh, name) for name in _PROBE_FIELD_NAMES}
    return msgspec.structs.replace(current, **probe_updates)


def provider_config_to_row(
    *,
    config: ProviderConfig,
    original: ProviderConfig | None,
    is_session_added: bool,
    api_key_resolves: bool,
) -> ProviderRow:
    """Derive one Providers-tab display row from a working-copy `ProviderConfig`.

    Args:
        config: The row's current working-copy value.
        original: The same `provider_id`'s value as last loaded from the
            gateway, or `None` for a row with no persisted counterpart.
        is_session_added: Whether this row was added this session and never
            persisted (drives the `(new)` marker and Reset-removes-row rule).
        api_key_resolves: Whether `config.api_key_raw` currently resolves to a
            non-empty value in the process environment. Ignored when
            `config.api_key_raw` is empty. Caller-supplied because resolution
            reads the process environment, which this pure module never does.

    Returns:
        The immutable `ProviderRow` the Providers tab table renders.
    """
    auth_badge = provider_auth_badge(
        api_key_env_var_name=config.api_key_raw, resolves=api_key_resolves
    )
    base_url_display = config.base_url or "(default)"
    return ProviderRow(
        provider_id=config.provider_id,
        label=config.name,
        provider_type=config.provider_type,
        base_url_display=base_url_display,
        auth_badge=auth_badge,
        health=config.last_probe_status,
        enabled=config.enabled,
        has_unsaved_edits=original is not None and original != config,
        is_session_added=is_session_added,
    )


def find_provider_id_by_name(*, providers: tuple[ProviderConfig, ...], name: str) -> str | None:
    """Look up a provider's id by its persisted display name (§3.4 embedding
    provider-dropdown initialisation; STORY-066 spec-conformance fix).

    Args:
        providers: The full working provider catalog to search.
        name: The persisted ``embedding.selected_provider_name`` value.

    Returns:
        The matching provider's ``provider_id``, or ``None`` when no provider
        in `providers` carries that name.
    """
    return next((provider.provider_id for provider in providers if provider.name == name), None)


def resolve_embedding_bootstrap_pair(
    *,
    enabled_providers: tuple[ProviderConfig, ...],
    models_by_provider: Callable[[ProviderId], tuple[ModelName, ...]],
) -> tuple[ProviderId, ModelName] | None:
    """Find the first available embedding-likely model across all enabled
    providers (§14 first-start embedding bootstrap; STORY-066 spec-conformance
    fix).

    Args:
        enabled_providers: Every enabled provider, in the catalog's display
            order -- the order the bootstrap search walks.
        models_by_provider: Discovers one provider's model list (typically
            ``SettingsGateway.discover_models``).

    Returns:
        The first ``(provider_id, model_name)`` pair, in provider order, whose
        model name is embedding-likely; ``None`` when no enabled provider
        offers any embedding-likely model.
    """
    for provider in enabled_providers:
        for model in models_by_provider(provider.provider_id):
            if is_embedding_model(model):
                return provider.provider_id, model
    return None


def embedding_diagnostic_text(*, embedding_reachable: bool) -> str:
    """Render the embedding section's readiness diagnostic (STORY-066-AC-7).

    Args:
        embedding_reachable: ``AppReadinessSnapshot.embedding_reachable`` /
            ``AppReadinessChangedEvent.embedding_reachable`` from the
            auto-check-on-open probe.

    Returns:
        A short reachability line for the embedding section.
    """
    return "✓ embedding reachable" if embedding_reachable else "✗ embedding unreachable"


def select_dialog_chrome_view_model(*, dirty: bool) -> DialogChromeViewModel:
    """Derive the dialog shell's chrome state (``description.md`` §2).

    STORY-067 note: ``general_tab_label``/``save_enabled`` are placeholder
    values here (``"General"``, ``dirty``) pending the General tab and the
    cross-tab validation cascade this function has no access to; STORY-067's
    ``SettingsController._push_chrome`` computes the real values directly.

    Args:
        dirty: Whether any working-copy field differs from its persisted value.

    Returns:
        The tab label (asterisked while dirty) and the footer save-state text.
    """
    return DialogChromeViewModel(
        providers_tab_label="Providers *" if dirty else "Providers",
        general_tab_label="General",
        save_state_text="Unsaved changes" if dirty else "No changes",
        dirty=dirty,
        save_enabled=dirty,
    )
