"""Integration test for ``StoreQtBridge`` crossing a real thread boundary (STORY-044-AC-2).

Wires the real ``WorkspaceStore`` (``backend/stores``, STORY-039) to the real
``StoreQtBridge`` (``adapters/store_qt_bridge``, STORY-044) and exercises the
``any -> UI`` threading rule genuinely: the store's ``set_active_workspace`` is called from a
background ``threading.Thread``, never from the Qt GUI thread. This crosses real thread and
Qt-delivery boundaries, so it lives in ``tests/integration/`` rather than the module's
colocated unit tests (``testing-standard-pyqt`` skill; ``07_TESTING_STANDARD.md`` layout),
mirroring ``tests/integration/test_qt_inference_activity_bridge.py`` (STORY-043).
"""

import threading

from PySide6.QtCore import QCoreApplication, QThread
from pytestqt.qtbot import QtBot

from ollama_llm_bench.adapters.store_qt_bridge import make_store_qt_bridge
from ollama_llm_bench.backend.stores import make_run_registry_store, make_workspace_store
from ollama_llm_bench.backend.stores.models import WorkspaceState


def test_workspace_change_from_worker_delivers_on_gui_thread(qtbot: QtBot) -> None:
    """Proves: STORY-044-AC-2

    Given the bridge is wired to a ``WorkspaceStore`` and a Qt slot connected to the bridge,
    when the store's ``active_workspace_changed`` psygnal fires from a non-GUI thread,
    then the connected Qt slot runs on the Qt main thread with the new ``WorkspaceState``
    snapshot.
    """
    # Arrange
    run_registry_store = make_run_registry_store()
    workspace_store = make_workspace_store()
    bridge = make_store_qt_bridge(
        run_registry_store=run_registry_store, workspace_store=workspace_store
    )
    received_states: list[WorkspaceState] = []
    received_threads: list[QThread] = []

    def _handler(state: WorkspaceState) -> None:
        received_states.append(state)
        received_threads.append(QThread.currentThread())

    bridge.active_workspace_changed.connect(_handler)
    worker = threading.Thread(target=lambda: workspace_store.set_active_workspace("task_editor"))

    # Act
    worker.start()
    worker.join(timeout=2)
    qtbot.waitUntil(lambda: len(received_states) == 1, timeout=2000)

    # Assert
    gui_thread = QCoreApplication.instance().thread()  # type: ignore[union-attr]
    assert received_states[0] == WorkspaceState(active_workspace="task_editor")
    assert received_threads[0] is gui_thread
