"""Fakes for ``RunRegistryStore`` and ``WorkspaceStore`` for downstream tests.

Each fake independently reimplements the real store's semantics — the same ``Signal`` class
attribute, the same swap-then-emit ordering, the same guard clauses — rather than subclassing
the real classes, mirroring the ``backend/stores/inference_activity/testing.py`` pattern.
"""

from typing import Final

from psygnal import Signal

from ollama_llm_bench.backend.domain import RunId
from ollama_llm_bench.backend.errors import ContractViolationError
from ollama_llm_bench.backend.stores.models import RunRegistryState, WorkspaceState

__all__: list[str] = [
    "FakeRunRegistryStore",
    "FakeWorkspaceStore",
]

_VALID_WORKSPACES: Final[frozenset[str]] = frozenset({"benchmark", "task_editor"})


class FakeRunRegistryStore:
    """An in-memory ``RunRegistryStore`` fake for downstream module tests."""

    active_run_changed = Signal(RunRegistryState)

    def __init__(self) -> None:
        self._state = RunRegistryState(active_run_id=None)

    def active_run_id(self) -> RunId | None:
        """Return the currently active run id, or ``None`` when no run is active."""
        return self._state.active_run_id

    def set_active_run(self, run_id: RunId | None) -> None:
        """Atomically swap the active run and, if it changed, emit ``active_run_changed``."""
        if run_id == self._state.active_run_id:
            return
        self._state = RunRegistryState(active_run_id=run_id)
        self.active_run_changed.emit(self._state)


class FakeWorkspaceStore:
    """An in-memory ``WorkspaceStore`` fake for downstream module tests."""

    active_workspace_changed = Signal(WorkspaceState)

    def __init__(self) -> None:
        self._state = WorkspaceState(active_workspace="benchmark")

    def active_workspace(self) -> str:
        """Return the currently active workspace name."""
        return self._state.active_workspace

    def set_active_workspace(self, name: str) -> None:
        """Atomically swap the active workspace and, if it changed, emit the signal.

        Raises:
            ContractViolationError: ``name`` is neither ``"benchmark"`` nor
                ``"task_editor"``.
        """
        if name not in _VALID_WORKSPACES:
            raise ContractViolationError(
                message=f"invalid workspace name {name!r}; must be one of {sorted(_VALID_WORKSPACES)}"
            )
        if name == self._state.active_workspace:
            return
        self._state = WorkspaceState(active_workspace=name)
        self.active_workspace_changed.emit(self._state)
