"""Public factory for ``adapters/store_qt_bridge/`` (01_MODULE_INVENTORY.md §5).

Constructs the application's single ``StoreQtBridge`` — the only adapter allowed to
subscribe to a psygnal signal from a Qt thread, marshalling the ``RunRegistryStore`` and
``WorkspaceStore`` change signals onto the Qt GUI thread.
"""

import icontract
from PySide6.QtCore import QCoreApplication, QThread

from ollama_llm_bench.adapters.store_qt_bridge._internal.bridge import StoreQtBridge
from ollama_llm_bench.backend.stores import RunRegistryStore, WorkspaceStore

__all__: list[str] = ["StoreQtBridge", "make_store_qt_bridge"]


@icontract.require(
    lambda run_registry_store: run_registry_store is not None,
    "run_registry_store is a required collaborator wired by compose.py",
)
@icontract.require(
    lambda workspace_store: workspace_store is not None,
    "workspace_store is a required collaborator wired by compose.py",
)
@icontract.require(
    lambda: QCoreApplication.instance() is not None,
    "a QApplication must already exist — called once from compose.py during start-up",
)
@icontract.require(
    lambda: QThread.currentThread() is QCoreApplication.instance().thread(),  # type: ignore[union-attr]
    "make_store_qt_bridge must be called on the Qt GUI thread — every call site in this "
    "codebase is compose.py; a call from a worker thread is a programmer error",
)
@icontract.ensure(
    lambda result: result is not None,
    "make_store_qt_bridge must always return a usable bridge — a violation here means this "
    "factory's own wiring is broken, not that a caller passed bad input",
)
def make_store_qt_bridge(
    *, run_registry_store: RunRegistryStore, workspace_store: WorkspaceStore
) -> StoreQtBridge:
    """Construct the psygnal-to-Qt bridge over the run-registry and workspace stores.

    Args:
        run_registry_store: The reactive store owning the active-run snapshot; this
            bridge subscribes to its ``active_run_changed`` psygnal signal.
        workspace_store: The reactive store owning the active-workspace snapshot;
            this bridge subscribes to its ``active_workspace_changed`` psygnal signal.

    Returns:
        A ``StoreQtBridge`` whose ``active_run_changed``/``active_workspace_changed``
        Qt signals fire on the Qt GUI thread carrying each store's new frozen snapshot.
    """
    return StoreQtBridge(run_registry_store=run_registry_store, workspace_store=workspace_store)
