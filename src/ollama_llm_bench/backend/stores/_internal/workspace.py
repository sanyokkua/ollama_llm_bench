"""The concrete ``WorkspaceStore`` implementation (ADR-0002).

Source of truth: ``docs/v3_specification/08_Cross_Cutting/08-E_interfaces_contracts.md`` §19
(workspace controller — the two workspace names and the current-workspace-held-as-store-state
statement); ``docs/v3_specification/08_Cross_Cutting/08-Q_event_payload_schemas.md`` §9.1.

No ``threading.Lock`` guards this store: it is a plain psygnal-driven reactive store owned by
the GUI thread, not one of the two explicitly-locked shared-mutable-state objects
(the inference-activity gate and the single DB writer) called out by
``16_Engineering_Standards/04_CONCURRENCY_STANDARD.md``.

The workspace name is a code-controlled constant, never user input, so an invalid name is
rejected by a plain guard clause raising ``ContractViolationError`` — not an ``icontract``
decorator, which only attaches to ``api.py`` public functions (``linting.md``) and raises the
wrong exception type (``icontract.errors.ViolationError``) for a concrete method.
"""

from typing import Final

from psygnal import Signal

from ollama_llm_bench.backend.errors import ContractViolationError
from ollama_llm_bench.backend.stores.models import WorkspaceState

__all__: list[str] = [
    "Workspace",
]

_VALID_WORKSPACES: Final[frozenset[str]] = frozenset({"benchmark", "task_editor"})


class Workspace:
    """The application-wide active-workspace reactive store (ADR-0002, 08-E §19).

    Holds an immutable ``WorkspaceState`` snapshot; every ``set_active_workspace``
    call that actually changes the active workspace atomically swaps the
    snapshot, then emits ``active_workspace_changed`` carrying the new snapshot.
    """

    active_workspace_changed = Signal(WorkspaceState)

    def __init__(self) -> None:
        """Construct a fresh store, defaulting to the benchmark workspace."""
        self._state = WorkspaceState(active_workspace="benchmark")

    def active_workspace(self) -> str:
        """Return the currently active workspace name."""
        return self._state.active_workspace

    def set_active_workspace(self, name: str) -> None:
        """Atomically swap the active workspace and, if it changed, emit the signal.

        Raises:
            ContractViolationError: ``name`` is neither ``"benchmark"`` nor
                ``"task_editor"`` — the workspace name is code-controlled, never
                user input, so an invalid value is a programmer error.
        """
        if name not in _VALID_WORKSPACES:
            raise ContractViolationError(
                message=f"invalid workspace name {name!r}; must be one of {sorted(_VALID_WORKSPACES)}"
            )
        if name == self._state.active_workspace:
            return
        self._state = WorkspaceState(active_workspace=name)
        self.active_workspace_changed.emit(self._state)
