"""Snapshot DTOs owned by ``backend/stores/``: ``RunRegistryState`` and ``WorkspaceState``.

Source of truth: ``docs/v3_specification/08_Cross_Cutting/08-E_interfaces_contracts.md`` §19
(workspace names, active-workspace-as-store-state); ``docs/v3_specification/08_Cross_Cutting/
08-Q_event_payload_schemas.md`` §9.1 (``"benchmark"``/``"task_editor"`` values);
``docs/v3_specification/01_Main_Window/implementation_structure.md`` §8 (stores fanout);
``docs/v3_specification/09_Task_Editor/implementation_structure.md`` §7 (dependency Protocols).
"""

import msgspec

from ollama_llm_bench.backend.domain import RunId

__all__: list[str] = [
    "RunRegistryState",
    "WorkspaceState",
]


class RunRegistryState(msgspec.Struct, frozen=True, kw_only=True, gc=False):
    """Immutable snapshot of the active-run slice of state (ADR-0002).

    Attributes:
        active_run_id: The run id currently considered "active" app-wide, or
            ``None`` when no run is active.
    """

    active_run_id: RunId | None


class WorkspaceState(msgspec.Struct, frozen=True, kw_only=True, gc=False):
    """Immutable snapshot of the active-workspace slice of state (ADR-0002).

    Attributes:
        active_workspace: The currently active workspace name — either
            ``"benchmark"`` or ``"task_editor"`` (08-E §19). Plain ``str``, not
            a ``StrEnum``/``Literal``, matching the pre-existing
            ``WorkspaceChangedEvent.workspace: str`` field.
    """

    active_workspace: str
