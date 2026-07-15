"""Unit tests for ``StoreQtBridge`` (STORY-044-AC-1, STORY-044-AC-3).

These tests run against a real ``QApplication`` (via ``qtbot``) even though they are scoped
to this one module: each public signal is fed through a private
``Qt.ConnectionType.QueuedConnection`` relay signal, so delivery requires a running Qt event
loop even for a same-thread ``emit()`` call (see the bridge module docstring, and the
precedent in ``adapters/qt_event_bus/tests/test_deliverer.py``).
"""

from pytestqt.qtbot import QtBot

from ollama_llm_bench.adapters.store_qt_bridge import make_store_qt_bridge
from ollama_llm_bench.backend.stores.models import RunRegistryState, WorkspaceState
from ollama_llm_bench.backend.stores.testing import FakeRunRegistryStore, FakeWorkspaceStore

_SOME_RUN_ID = 42


def test_run_registry_psygnal_reemits_as_qt_signal(qtbot: QtBot) -> None:
    """Proves: STORY-044-AC-1

    Given the bridge is wired to a ``RunRegistryStore``,
    when the store's ``active_run_changed`` psygnal signal fires,
    then the bridge emits its corresponding Qt signal carrying the store's new
    ``RunRegistryState`` snapshot.
    """
    # Arrange
    run_registry_store = FakeRunRegistryStore()
    workspace_store = FakeWorkspaceStore()
    bridge = make_store_qt_bridge(
        run_registry_store=run_registry_store, workspace_store=workspace_store
    )
    collected: list[RunRegistryState] = []
    bridge.active_run_changed.connect(collected.append)

    # Act
    run_registry_store.set_active_run(_SOME_RUN_ID)
    qtbot.waitUntil(lambda: len(collected) == 1, timeout=2000)

    # Assert
    assert collected == [RunRegistryState(active_run_id=_SOME_RUN_ID)]


def test_dispose_unsubscribes_from_store_signals(qtbot: QtBot) -> None:
    """Proves: STORY-044-AC-3

    Given a bridge with active psygnal subscriptions,
    when the bridge is disposed,
    then it unsubscribes from every store's psygnal signal and a subsequent store change
    emits no Qt signal from the disposed bridge; disposing a second time does not raise.
    """
    # Arrange
    run_registry_store = FakeRunRegistryStore()
    workspace_store = FakeWorkspaceStore()
    bridge = make_store_qt_bridge(
        run_registry_store=run_registry_store, workspace_store=workspace_store
    )
    run_registry_collected: list[RunRegistryState] = []
    workspace_collected: list[WorkspaceState] = []
    bridge.active_run_changed.connect(run_registry_collected.append)
    bridge.active_workspace_changed.connect(workspace_collected.append)

    # Act
    bridge.dispose()
    bridge.dispose()  # idempotent — must not raise
    run_registry_store.set_active_run(_SOME_RUN_ID)
    workspace_store.set_active_workspace("task_editor")
    qtbot.wait(150)

    # Assert
    assert run_registry_collected == []
    assert workspace_collected == []
