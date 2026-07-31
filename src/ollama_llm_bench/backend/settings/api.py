"""Public factories for ``backend/settings/``.

Source of truth: ``docs/v3_specification/08_Cross_Cutting/08-E_interfaces_contracts.md``
§8 (Settings Service) and §8a (Run Snapshot Builder).
"""

import sqlite3
import threading

import icontract

from ollama_llm_bench.backend.events import EventBus
from ollama_llm_bench.backend.persistence.app_settings import AppSettingsStore
from ollama_llm_bench.backend.persistence.providers import ProvidersStore
from ollama_llm_bench.backend.settings._internal.atomic_writer_impl import (
    SqliteSettingsAtomicWriter,
)
from ollama_llm_bench.backend.settings._internal.registry import DEFAULTS, PER_RUN_OVERRIDABLE
from ollama_llm_bench.backend.settings._internal.run_snapshot_builder_impl import (
    RunSnapshotBuilderImpl,
)
from ollama_llm_bench.backend.settings._internal.settings_service_impl import (
    SettingsServiceImpl,
)
from ollama_llm_bench.backend.settings.protocols import (
    RunSnapshotBuilder,
    SettingsAtomicWriter,
    SettingsService,
)

__all__: list[str] = [
    "DEFAULTS",
    "PER_RUN_OVERRIDABLE",
    "RunSnapshotBuilder",
    "SettingsAtomicWriter",
    "SettingsService",
    "make_run_snapshot_builder",
    "make_settings_atomic_writer",
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


@icontract.require(lambda write_conn: write_conn is not None, "write_conn is required")
@icontract.require(lambda lock: lock is not None, "lock is required")
@icontract.require(
    lambda providers_store: providers_store is not None, "providers_store is required"
)
@icontract.require(
    lambda app_settings_store: app_settings_store is not None, "app_settings_store is required"
)
@icontract.ensure(
    lambda result: result is not None,
    "make_settings_atomic_writer must always return a usable writer -- a violation here "
    "means this factory's own wiring is broken, not that a caller passed bad input",
)
def make_settings_atomic_writer(
    *,
    write_conn: sqlite3.Connection,
    lock: threading.Lock,
    providers_store: ProvidersStore,
    app_settings_store: AppSettingsStore,
) -> SettingsAtomicWriter:
    """Construct the cross-store atomic writer for Settings Save / Reset.

    Args:
        write_conn: The single shared write connection (the same one already
            injected into every other persistence store).
        lock: The lock guarding ``write_conn``.
        providers_store: Must be backed by the SAME ``write_conn``/``lock``
            pair -- constructed from a different connection would silently
            defeat atomicity.
        app_settings_store: Same requirement as ``providers_store``.

    Returns:
        A ``SettingsAtomicWriter`` ready to be handed to ``make_settings_gateway``.
    """
    return SqliteSettingsAtomicWriter(
        write_conn=write_conn,
        lock=lock,
        providers_store=providers_store,
        app_settings_store=app_settings_store,
    )
