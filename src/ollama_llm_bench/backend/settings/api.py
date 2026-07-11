"""Public factories for ``backend/settings/``.

Source of truth: ``docs/v3_specification/08_Cross_Cutting/08-E_interfaces_contracts.md``
§8 (Settings Service) and §8a (Run Snapshot Builder).
"""

import icontract

from ollama_llm_bench.backend.events import EventBus
from ollama_llm_bench.backend.persistence.app_settings import AppSettingsStore
from ollama_llm_bench.backend.settings._internal.run_snapshot_builder_impl import (
    RunSnapshotBuilderImpl,
)
from ollama_llm_bench.backend.settings._internal.settings_service_impl import (
    SettingsServiceImpl,
)
from ollama_llm_bench.backend.settings.protocols import RunSnapshotBuilder, SettingsService

__all__: list[str] = [
    "RunSnapshotBuilder",
    "SettingsService",
    "make_run_snapshot_builder",
    "make_settings_service",
]


@icontract.require(lambda store: store is not None, "store must be injected, not None")
@icontract.require(lambda event_bus: event_bus is not None, "event_bus must be injected, not None")
@icontract.ensure(lambda result: result is not None, "the factory must always return an instance")
def make_settings_service(*, store: AppSettingsStore, event_bus: EventBus) -> SettingsService:
    """Construct the concrete ``SettingsService`` over the given collaborators.

    Args:
        store: The user-saved settings layer.
        event_bus: The bus on which ``_app_settings_changed`` is emitted after
            every ``set``/``upsert`` call.

    Returns:
        A ``SettingsService`` resolving reads through the three-layer cascade
        and writing only to the user-saved layer.
    """
    return SettingsServiceImpl(store=store, event_bus=event_bus)


@icontract.require(lambda store: store is not None, "store must be injected, not None")
@icontract.ensure(lambda result: result is not None, "the factory must always return an instance")
def make_run_snapshot_builder(*, store: AppSettingsStore) -> RunSnapshotBuilder:
    """Construct the concrete ``RunSnapshotBuilder`` over the given store.

    Args:
        store: The user-saved settings layer consulted for every
            per-run-overridable key's ``User-Saved -> Default`` value.

    Returns:
        A ``RunSnapshotBuilder`` producing the exhaustive per-run snapshot.
    """
    return RunSnapshotBuilderImpl(store=store)
