"""Integration tests for ``backend/persistence/model_capabilities/``.

Exercises the real ``ModelCapabilitiesStore`` public surface —
``create_model_capabilities_store`` and the ``SqliteModelCapabilitiesStore`` it
returns — against a real ``tmp_path`` SQLite database file, never ``:memory:``,
per ``testing.md``'s integration-tier rule.

Source of truth: STORY-013 acceptance criteria AC-1, AC-2, AC-3.
"""

from pathlib import Path

import pytest

from ollama_llm_bench.backend.domain import (
    CapabilitySource,
    ModelCapability,
    ModelCapabilityRecord,
    ProviderConfigDraft,
    ProviderId,
    ProviderType,
)
from ollama_llm_bench.backend.infra.protocols import Clock
from ollama_llm_bench.backend.persistence.app_settings import (
    ensure_schema,
    open_read_connection,
    open_write_connection,
)
from ollama_llm_bench.backend.persistence.model_capabilities import (
    ModelCapabilitiesStore,
    create_model_capabilities_store,
)
from ollama_llm_bench.backend.persistence.providers import ProvidersStore, create_providers_store


@pytest.fixture
def stores(db_path: Path, clock: Clock) -> tuple[ModelCapabilitiesStore, ProvidersStore]:
    """A ``ModelCapabilitiesStore`` and a ``ProvidersStore`` wired over the same
    fresh ``tmp_path`` database, sharing one write connection and lock.
    """
    write_conn, lock = open_write_connection(db_path)
    ensure_schema(write_conn, lock, clock=clock)
    read_conn_factory = lambda: open_read_connection(db_path)  # noqa: E731
    capabilities_store = create_model_capabilities_store(write_conn, lock, read_conn_factory)
    providers_store = create_providers_store(write_conn, lock, read_conn_factory)
    return capabilities_store, providers_store


def _add_provider(providers_store: ProvidersStore, *, name: str = "My Provider") -> ProviderId:
    """Insert a provider row via ``ProvidersStore.add`` to satisfy the FK."""
    draft = ProviderConfigDraft(
        name=name,
        provider_type=ProviderType.OPENAI_COMPATIBLE,
        enabled=True,
        base_url="http://localhost:11434/v1",
        default_models=("llama3",),
        provider_order=0,
    )
    return providers_store.add(draft)


def test_upsert_then_list_returns_record(
    stores: tuple[ModelCapabilitiesStore, ProvidersStore],
) -> None:
    """Proves: STORY-013-AC-1

    Given no cached capability for a model, when upsert_model_capability writes
    a record, then list_model_capabilities(provider_id, model_name) returns
    exactly that record with its supported, last_observed_at, observed_via, and
    detail values preserved.
    """
    capabilities_store, providers_store = stores
    provider_id = _add_provider(providers_store)

    record = ModelCapabilityRecord(
        provider_id=provider_id,
        model_name="llama3",
        capability=ModelCapability.STREAMING,
        supported=1,
        last_observed_at="2026-01-01T00:00:00+00:00",
        observed_via=CapabilitySource.PROBE,
        detail="observed during health probe",
    )

    # Act
    capabilities_store.upsert_model_capability(record)

    # Assert
    results = capabilities_store.list_model_capabilities(provider_id, "llama3")
    assert results == (record,)


def test_upsert_same_triple_updates_in_place(
    stores: tuple[ModelCapabilitiesStore, ProvidersStore],
) -> None:
    """Proves: STORY-013-AC-2

    Given a cached capability record for a (provider_id, model_name, capability)
    triple, when upsert_model_capability writes a new record for the same
    triple with a different supported value, then the existing row is updated
    in place and list_model_capabilities returns one row for that capability,
    not two.
    """
    capabilities_store, providers_store = stores
    provider_id = _add_provider(providers_store)

    first = ModelCapabilityRecord(
        provider_id=provider_id,
        model_name="llama3",
        capability=ModelCapability.THINKING,
        supported=-1,
        last_observed_at="2026-01-01T00:00:00+00:00",
        observed_via=CapabilitySource.PROBE,
        detail=None,
    )
    capabilities_store.upsert_model_capability(first)

    second = ModelCapabilityRecord(
        provider_id=provider_id,
        model_name="llama3",
        capability=ModelCapability.THINKING,
        supported=1,
        last_observed_at="2026-02-01T00:00:00+00:00",
        observed_via=CapabilitySource.INFERENCE,
        detail="confirmed via live inference",
    )

    # Act
    capabilities_store.upsert_model_capability(second)

    # Assert
    results = capabilities_store.list_model_capabilities(provider_id, "llama3")
    assert results == (second,)


def test_provider_delete_cascades_capabilities(
    stores: tuple[ModelCapabilitiesStore, ProvidersStore],
) -> None:
    """Proves: STORY-013-AC-3

    Given cached capability rows for a provider, when that provider is
    deleted, then list_model_capabilities returns an empty tuple for its
    models — the rows were cascade-removed.
    """
    capabilities_store, providers_store = stores
    provider_id = _add_provider(providers_store)

    record = ModelCapabilityRecord(
        provider_id=provider_id,
        model_name="llama3",
        capability=ModelCapability.REASONING_EFFORT,
        supported=0,
        last_observed_at="2026-01-01T00:00:00+00:00",
        observed_via=CapabilitySource.MANUAL,
        detail=None,
    )
    capabilities_store.upsert_model_capability(record)

    # Sanity — the row is visible before delete.
    assert capabilities_store.list_model_capabilities(provider_id, "llama3") == (record,)

    # Act
    providers_store.delete(provider_id)

    # Assert
    assert capabilities_store.list_model_capabilities(provider_id, "llama3") == ()
