"""Public surface for ``backend/stores/``: the ``RunRegistryStore`` and ``WorkspaceStore``
factories.

The composition root constructs each store once and injects it wherever an
``RunRegistryStore``/``WorkspaceStore`` is needed — the Main Window's stores fanout and the
Task Editor's dependency Protocols each read/write these two reactive stores directly, with the
psygnal-to-Qt bridge (``adapters/store_qt_bridge/``, STORY-044) and the workspace controller
(``adapters/workspace_controller/``, STORY-045) wired on top.

Source of truth: ``docs/v3_specification/14_Process_and_Traceability/01_MODULE_INVENTORY.md``
§4.2.
"""

import icontract

from ollama_llm_bench.backend.stores._internal.run_registry import RunRegistry
from ollama_llm_bench.backend.stores._internal.workspace import Workspace
from ollama_llm_bench.backend.stores.protocols import RunRegistryStore, WorkspaceStore

__all__: list[str] = [
    "RunRegistryStore",
    "WorkspaceStore",
    "make_run_registry_store",
    "make_workspace_store",
]


@icontract.ensure(
    lambda result: result.active_run_id() is None,
    "a freshly constructed run registry store has no active run",
)
def make_run_registry_store() -> RunRegistryStore:
    """Construct the application-wide active-run reactive store.

    Returns:
        A fresh ``RunRegistryStore``, starting with no active run.
    """
    return RunRegistry()


@icontract.ensure(
    lambda result: result.active_workspace() == "benchmark",
    "a freshly constructed workspace store defaults to the benchmark workspace",
)
def make_workspace_store() -> WorkspaceStore:
    """Construct the application-wide active-workspace reactive store.

    Returns:
        A fresh ``WorkspaceStore``, defaulting to the ``"benchmark"`` workspace.
    """
    return Workspace()
