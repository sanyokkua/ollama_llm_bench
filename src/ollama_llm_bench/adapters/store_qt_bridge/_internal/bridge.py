"""``StoreQtBridge`` — marshals the reactive stores' psygnal signals onto the Qt GUI thread.

Source of truth: ``docs/v3_specification/14_Process_and_Traceability/01_MODULE_INVENTORY.md``
§5 (``adapters/store_qt_bridge/`` is the only adapter allowed to subscribe to a psygnal signal
from a Qt thread), ``docs/v3_specification/08_Cross_Cutting/08-E_interfaces_contracts.md`` §19
(workspace state), and
``docs/v3_specification/16_Engineering_Standards/04_CONCURRENCY_STANDARD.md`` §8
(thread-boundary rules — a worker thread never touches a widget directly; every cross-thread
reactive update is marshalled onto the GUI thread through a queued connection).

``StoreQtBridge`` carries no store logic of its own — the ``RunRegistryStore`` and
``WorkspaceStore`` (``backend/stores/``) remain the single owners of their snapshots and their
psygnal change signals. This bridge only re-emits each store's psygnal signal as a same-named
Qt ``Signal`` carrying the store's frozen snapshot, delivered on the Qt GUI thread regardless
of which thread the psygnal signal fired on.

Unlike ``adapters/qt_event_bus/``'s ``_RelayCarrier`` nested-carrier pattern, this class
implements no Protocol requiring a method literally named ``emit``, so the
never-declare-``emit``-alongside-a-``Signal`` hazard
(``docs/v3_specification/16_Engineering_Standards/04_CONCURRENCY_STANDARD.md``;
``adapters/qt_event_bus/_internal/deliverer.py`` module docstring) does not apply here — the
two public signals and their private relay signals all live directly on this class.

A queued hop is still required: if the psygnal callback (which may run on any thread) emitted
the public signal directly, and a widget connected to it with a plain callable/lambda rather
than a bound ``QObject`` method, Qt's ``AutoConnection`` would deliver to that non-``QObject``
receiver directly and synchronously on the emitting thread — violating the GUI-thread-delivery
requirement regardless of the emitting thread. Each store therefore has one private, forced
``Qt.ConnectionType.QueuedConnection`` relay signal that re-emits the public signal once
delivery reaches the Qt GUI thread.
"""

from PySide6.QtCore import QObject, Qt, Signal, Slot

from ollama_llm_bench.backend.stores import RunRegistryStore, WorkspaceStore
from ollama_llm_bench.backend.stores.models import RunRegistryState, WorkspaceState

__all__: list[str] = ["StoreQtBridge"]


class StoreQtBridge(QObject):
    """Bridges ``RunRegistryStore``/``WorkspaceStore`` psygnal signals onto the Qt GUI thread.

    Public signal names match the source psygnal signal names verbatim
    (``active_run_changed``, ``active_workspace_changed``) — a same-named proxy with no
    translation step. Each public signal is fed through a private forced-queued relay signal
    so delivery always lands on the Qt GUI thread (see the module docstring).
    """

    active_run_changed = Signal(RunRegistryState)
    active_workspace_changed = Signal(WorkspaceState)

    _run_registry_relay = Signal(RunRegistryState)
    _workspace_relay = Signal(WorkspaceState)

    def __init__(
        self, *, run_registry_store: RunRegistryStore, workspace_store: WorkspaceStore
    ) -> None:
        """Subscribe to both stores' psygnal signals and wire the queued relay hops.

        Args:
            run_registry_store: The reactive store owning the active-run snapshot.
            workspace_store: The reactive store owning the active-workspace snapshot.
        """
        super().__init__()
        self._run_registry_store = run_registry_store
        self._workspace_store = workspace_store
        self._disposed = False
        self._run_registry_relay.connect(
            self._dispatch_run_registry, Qt.ConnectionType.QueuedConnection
        )
        self._workspace_relay.connect(self._dispatch_workspace, Qt.ConnectionType.QueuedConnection)
        self._run_registry_store.active_run_changed.connect(self._on_run_registry_store_changed)
        self._workspace_store.active_workspace_changed.connect(self._on_workspace_store_changed)

    def dispose(self) -> None:
        """Unsubscribe from both stores' psygnal signals.

        Idempotent — the first call disconnects both subscriptions; every subsequent call is
        a no-op. After disposal, no further store change reaches this bridge's Qt signals.
        """
        if self._disposed:
            return
        self._disposed = True
        self._run_registry_store.active_run_changed.disconnect(self._on_run_registry_store_changed)
        self._workspace_store.active_workspace_changed.disconnect(self._on_workspace_store_changed)

    def _on_run_registry_store_changed(self, state: RunRegistryState) -> None:
        """psygnal callback for ``RunRegistryStore.active_run_changed`` — any thread."""
        self._run_registry_relay.emit(state)

    def _on_workspace_store_changed(self, state: WorkspaceState) -> None:
        """psygnal callback for ``WorkspaceStore.active_workspace_changed`` — any thread."""
        self._workspace_relay.emit(state)

    @Slot(RunRegistryState)
    def _dispatch_run_registry(self, state: RunRegistryState) -> None:
        """Re-emit the run-registry snapshot on the public signal. Runs on the GUI thread."""
        self.active_run_changed.emit(state)

    @Slot(WorkspaceState)
    def _dispatch_workspace(self, state: WorkspaceState) -> None:
        """Re-emit the workspace snapshot on the public signal. Runs on the GUI thread."""
        self.active_workspace_changed.emit(state)
