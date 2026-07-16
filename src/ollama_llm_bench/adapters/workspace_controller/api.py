"""Public factory for ``adapters/workspace_controller/`` (08-E §19, 08-Q §9.1).

Constructs the application's single ``QtWorkspaceController`` — the Qt-bound coordinator
that switches the main window between its ``"benchmark"`` and ``"task_editor"``
workspaces (``01_MODULE_INVENTORY.md`` §5).
"""

from collections.abc import Callable, Mapping

import icontract
from PySide6.QtWidgets import QStackedWidget, QWidget

from ollama_llm_bench.adapters.workspace_controller._internal.controller import (
    QtWorkspaceController,
)
from ollama_llm_bench.adapters.workspace_controller.models import WorkspaceHint
from ollama_llm_bench.adapters.workspace_controller.protocols import WorkspaceController
from ollama_llm_bench.backend.events import EventBus
from ollama_llm_bench.backend.stores import WorkspaceStore

__all__: list[str] = ["WorkspaceController", "WorkspaceHint", "make_workspace_controller"]

_REQUIRED_WORKSPACES: frozenset[str] = frozenset({"benchmark", "task_editor"})


@icontract.require(
    lambda workspace_store: workspace_store is not None,
    "workspace_store is a required collaborator wired by compose.py",
)
@icontract.require(
    lambda event_bus: event_bus is not None,
    "event_bus is a required collaborator wired by compose.py",
)
@icontract.require(
    lambda container: container is not None,
    "container is a required collaborator wired by compose.py",
)
@icontract.require(
    lambda workspace_factories: set(workspace_factories) == _REQUIRED_WORKSPACES,
    "workspace_factories must register exactly the benchmark and task_editor workspaces",
)
@icontract.ensure(
    lambda result: result is not None,
    "make_workspace_controller must always return a usable controller — a violation "
    "here means this factory's own wiring is broken, not that a caller passed bad input",
)
def make_workspace_controller(
    *,
    workspace_store: WorkspaceStore,
    event_bus: EventBus,
    container: QStackedWidget,
    workspace_factories: Mapping[str, Callable[[], QWidget]],
) -> WorkspaceController:
    """Construct the Qt-bound workspace-switch coordinator.

    Args:
        workspace_store: The reactive store this controller reads and writes
            the active workspace name through.
        event_bus: The bus this controller emits ``_workspace_changed`` on.
        container: The ``QStackedWidget`` region the two workspace widgets
            are shown in; owned by the caller (``compose.py`` / a future
            Main Window story).
        workspace_factories: Exactly one zero-argument widget factory per
            workspace name (``"benchmark"``, ``"task_editor"``), each
            invoked at most once, on first switch to that workspace.

    Returns:
        A ``WorkspaceController`` that lazily builds, shows, and retains the
        two workspace widgets on demand.
    """
    return QtWorkspaceController(
        workspace_store=workspace_store,
        event_bus=event_bus,
        container=container,
        workspace_factories=workspace_factories,
    )
