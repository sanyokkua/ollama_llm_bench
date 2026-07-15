"""Shared contract-test suite for ``RunRegistryStore``, run against both the real
``RunRegistry`` and ``FakeRunRegistryStore`` (STORY-039)."""

from typing import Final

import pytest

from ollama_llm_bench.backend.stores._internal.run_registry import RunRegistry
from ollama_llm_bench.backend.stores.protocols import RunRegistryStore
from ollama_llm_bench.backend.stores.testing import FakeRunRegistryStore

__all__: list[str] = []

_FIRST_RUN_ID: Final[int] = 42
_SECOND_RUN_ID: Final[int] = 7
_THIRD_RUN_ID: Final[int] = 99


@pytest.fixture(params=["real", "fake"])
def run_registry_store(request: pytest.FixtureRequest) -> RunRegistryStore:
    """Provide both the real and the fake ``RunRegistryStore`` implementation."""
    if request.param == "real":
        return RunRegistry()
    return FakeRunRegistryStore()


def test_active_run_id_is_none_at_construction(run_registry_store: RunRegistryStore) -> None:
    """Proves: STORY-039-AC-1

    A freshly constructed ``RunRegistryStore`` has no active run.
    """
    # Act / Assert
    assert run_registry_store.active_run_id() is None


def test_set_active_run_updates_snapshot_and_emits_signal(
    run_registry_store: RunRegistryStore,
) -> None:
    """Proves: STORY-039-AC-2

    Setting a different active run updates the snapshot and emits exactly one
    ``active_run_changed`` signal carrying the new ``RunRegistryState``.
    """
    # Arrange
    received: list[int | None] = []
    run_registry_store.active_run_changed.connect(
        lambda state: received.append(state.active_run_id)
    )

    # Act
    run_registry_store.set_active_run(_FIRST_RUN_ID)

    # Assert
    assert run_registry_store.active_run_id() == _FIRST_RUN_ID
    assert received == [_FIRST_RUN_ID]


def test_noop_set_active_run_emits_no_signal(run_registry_store: RunRegistryStore) -> None:
    """Proves: STORY-039-AC-3

    Re-setting the same active run id is a no-op: the snapshot is unchanged
    and no ``active_run_changed`` signal is emitted.
    """
    # Arrange
    run_registry_store.set_active_run(_SECOND_RUN_ID)
    received: list[int | None] = []
    run_registry_store.active_run_changed.connect(
        lambda state: received.append(state.active_run_id)
    )

    # Act
    run_registry_store.set_active_run(_SECOND_RUN_ID)

    # Assert
    assert run_registry_store.active_run_id() == _SECOND_RUN_ID
    assert received == []


def test_signal_fires_after_snapshot_swap(run_registry_store: RunRegistryStore) -> None:
    """Proves: STORY-039-AC-7

    A signal handler that reads the store while handling ``active_run_changed``
    observes the post-change snapshot, proving the swap-then-signal ordering.
    """
    # Arrange
    observed_during_signal: list[int | None] = []
    run_registry_store.active_run_changed.connect(
        lambda _state: observed_during_signal.append(run_registry_store.active_run_id())
    )

    # Act
    run_registry_store.set_active_run(_THIRD_RUN_ID)

    # Assert
    assert observed_during_signal == [_THIRD_RUN_ID]
