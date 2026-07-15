"""The concrete ``RunRegistryStore`` implementation (ADR-0002).

Source of truth: ``docs/v3_specification/01_Main_Window/implementation_structure.md`` §8
(stores fanout); ``docs/v3_specification/09_Task_Editor/implementation_structure.md`` §7.

No ``threading.Lock`` guards this store: it is a plain psygnal-driven reactive store owned by
the GUI thread, not one of the two explicitly-locked shared-mutable-state objects
(the inference-activity gate and the single DB writer) called out by
``16_Engineering_Standards/04_CONCURRENCY_STANDARD.md``.
"""

from psygnal import Signal

from ollama_llm_bench.backend.domain import RunId
from ollama_llm_bench.backend.stores.models import RunRegistryState

__all__: list[str] = [
    "RunRegistry",
]


class RunRegistry:
    """The application-wide active-run reactive store (ADR-0002).

    Holds an immutable ``RunRegistryState`` snapshot; every ``set_active_run``
    call that actually changes the active run atomically swaps the snapshot,
    then emits ``active_run_changed`` carrying the new snapshot.
    """

    active_run_changed = Signal(RunRegistryState)

    def __init__(self) -> None:
        """Construct a fresh store with no active run."""
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
