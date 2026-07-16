"""Qt-bound workspace-switch coordinator (STORY-045).

Switches the main window between its two workspaces — ``"benchmark"`` and
``"task_editor"`` — constructing each workspace widget lazily on first entry (then
retaining it), writing the active workspace to the ``WorkspaceStore``, reapplying the
theme to the shown widget, applying an optional ``WorkspaceHint``, and emitting exactly
one ``_workspace_changed`` event per actual switch.

Source of truth: ``docs/v3_specification/08_Cross_Cutting/08-E_interfaces_contracts.md``
§19 and ``docs/v3_specification/08_Cross_Cutting/08-Q_event_payload_schemas.md`` §9.1.
"""

from ollama_llm_bench.adapters.workspace_controller.api import (
    WorkspaceController,
    WorkspaceHint,
    make_workspace_controller,
)

__all__: list[str] = ["WorkspaceController", "WorkspaceHint", "make_workspace_controller"]
