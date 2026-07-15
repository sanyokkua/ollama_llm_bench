"""The ``RunRegistryStore`` and ``WorkspaceStore`` contracts owned by this module.

Source of truth: ``docs/v3_specification/14_Process_and_Traceability/01_MODULE_INVENTORY.md``
§4.2; ``docs/v3_specification/08_Cross_Cutting/08-E_interfaces_contracts.md`` §19 (workspace
controller); ``docs/v3_specification/09_Task_Editor/implementation_structure.md`` §7
(dependency Protocols); ``docs/v3_specification/01_Main_Window/implementation_structure.md``
§8 (stores fanout). Each Protocol's surface is deliberately minimal — exactly the methods and
signals its Phase-8 consumers call (ADR-0007) — no speculative methods.
"""

from typing import Protocol

from psygnal import SignalInstance

from ollama_llm_bench.backend.domain import RunId

__all__: list[str] = [
    "RunRegistryStore",
    "WorkspaceStore",
]


class RunRegistryStore(Protocol):
    """Reactive store holding which run is the application-wide "active" run.

    ``active_run_changed`` emits the new ``RunRegistryState`` snapshot every
    time the active run changes; a no-op ``set_active_run`` call (the same
    run id as the current one) emits no signal.
    """

    active_run_changed: SignalInstance

    def active_run_id(self) -> RunId | None:
        """Return the currently active run id, or ``None`` when no run is active."""
        ...

    def set_active_run(self, run_id: RunId | None) -> None:
        """Atomically swap the active run and, if it changed, emit ``active_run_changed``.

        Args:
            run_id: The run id to make active, or ``None`` to clear the active run.
        """
        ...


class WorkspaceStore(Protocol):
    """Reactive store holding which of the two workspaces is active.

    ``active_workspace_changed`` emits the new ``WorkspaceState`` snapshot
    every time the active workspace changes; a no-op ``set_active_workspace``
    call (the same name as the current one) emits no signal.
    """

    active_workspace_changed: SignalInstance

    def active_workspace(self) -> str:
        """Return the currently active workspace name (``"benchmark"`` or ``"task_editor"``)."""
        ...

    def set_active_workspace(self, name: str) -> None:
        """Atomically swap the active workspace and, if it changed, emit the signal.

        Args:
            name: The workspace name to make active — ``"benchmark"`` or
                ``"task_editor"``; any other value is a programmer error.
        """
        ...
