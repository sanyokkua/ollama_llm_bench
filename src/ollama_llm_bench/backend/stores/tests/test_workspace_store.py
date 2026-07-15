"""Shared contract-test suite for ``WorkspaceStore``, run against both the real
``Workspace`` and ``FakeWorkspaceStore`` (STORY-039)."""

import pytest

from ollama_llm_bench.backend.errors import ContractViolationError
from ollama_llm_bench.backend.stores._internal.workspace import Workspace
from ollama_llm_bench.backend.stores.protocols import WorkspaceStore
from ollama_llm_bench.backend.stores.testing import FakeWorkspaceStore

__all__: list[str] = []


@pytest.fixture(params=["real", "fake"])
def workspace_store(request: pytest.FixtureRequest) -> WorkspaceStore:
    """Provide both the real and the fake ``WorkspaceStore`` implementation."""
    if request.param == "real":
        return Workspace()
    return FakeWorkspaceStore()


def test_active_workspace_defaults_to_benchmark(workspace_store: WorkspaceStore) -> None:
    """Proves: STORY-039-AC-4

    A freshly constructed ``WorkspaceStore`` defaults to the benchmark workspace.
    """
    # Act / Assert
    assert workspace_store.active_workspace() == "benchmark"


def test_set_active_workspace_updates_snapshot_and_emits_signal(
    workspace_store: WorkspaceStore,
) -> None:
    """Proves: STORY-039-AC-5

    Setting a valid, different workspace name updates the snapshot and emits
    exactly one ``active_workspace_changed`` signal carrying the new
    ``WorkspaceState``.
    """
    # Arrange
    received: list[str] = []
    workspace_store.active_workspace_changed.connect(
        lambda state: received.append(state.active_workspace)
    )

    # Act
    workspace_store.set_active_workspace("task_editor")

    # Assert
    assert workspace_store.active_workspace() == "task_editor"
    assert received == ["task_editor"]


def test_invalid_workspace_name_raises_programmer_error_without_change(
    workspace_store: WorkspaceStore,
) -> None:
    """Proves: STORY-039-AC-6

    An invalid workspace name raises ``ContractViolationError`` and leaves the
    snapshot unchanged with no signal emitted.
    """
    # Arrange
    received: list[str] = []
    workspace_store.active_workspace_changed.connect(
        lambda state: received.append(state.active_workspace)
    )

    # Act / Assert
    with pytest.raises(ContractViolationError):
        workspace_store.set_active_workspace("not_a_real_workspace")
    assert workspace_store.active_workspace() == "benchmark"
    assert received == []


def test_signal_fires_after_snapshot_swap(workspace_store: WorkspaceStore) -> None:
    """Proves: STORY-039-AC-7

    A signal handler that reads the store while handling
    ``active_workspace_changed`` observes the post-change snapshot, proving
    the swap-then-signal ordering.
    """
    # Arrange
    observed_during_signal: list[str] = []
    workspace_store.active_workspace_changed.connect(
        lambda _state: observed_during_signal.append(workspace_store.active_workspace())
    )

    # Act
    workspace_store.set_active_workspace("task_editor")

    # Assert
    assert observed_during_signal == ["task_editor"]
