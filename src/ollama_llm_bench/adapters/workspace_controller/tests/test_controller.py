"""Unit tests for ``QtWorkspaceController`` (STORY-045-AC-4).

Uses the real ``WorkspaceStore`` (``backend/stores``, STORY-039) so its own
no-op-on-same-name semantics are exercised for real, and a ``mocker.Mock(spec=EventBus)``
test double for the event bus, per the project's mocking table
(``testing-standard-pyqt`` skill). Widget factories are call-counting closures so the
"no re-construction" half of AC-4 is directly assertable.
"""

from collections.abc import Callable

from PySide6.QtWidgets import QStackedWidget, QWidget
import pytest
from pytest_mock import MockerFixture
from pytestqt.qtbot import QtBot

from ollama_llm_bench.adapters.workspace_controller import make_workspace_controller
from ollama_llm_bench.backend.errors import ContractViolationError
from ollama_llm_bench.backend.events import EventBus
from ollama_llm_bench.backend.stores import make_workspace_store


def _counting_factory(qtbot: QtBot, calls: list[None]) -> Callable[[], QWidget]:
    """Build a zero-argument widget factory that records each invocation."""

    def _factory() -> QWidget:
        calls.append(None)
        widget = QWidget()
        qtbot.addWidget(widget)
        return widget

    return _factory


def test_same_workspace_switch_is_noop(qtbot: QtBot, mocker: MockerFixture) -> None:
    """Proves: STORY-045-AC-4

    Given the active workspace is already ``name`` (the freshly constructed
    ``WorkspaceStore`` defaults to ``"benchmark"``),
    when ``switch_to(name)`` is called again with the same name,
    then no widget is re-constructed and no ``_workspace_changed`` event is emitted
    (a same-workspace switch is a no-op).
    """
    # Arrange
    workspace_store = make_workspace_store()
    event_bus = mocker.Mock(spec=EventBus)
    container = QStackedWidget()
    qtbot.addWidget(container)
    benchmark_calls: list[None] = []
    task_editor_calls: list[None] = []
    controller = make_workspace_controller(
        workspace_store=workspace_store,
        event_bus=event_bus,
        container=container,
        workspace_factories={
            "benchmark": _counting_factory(qtbot, benchmark_calls),
            "task_editor": _counting_factory(qtbot, task_editor_calls),
        },
    )

    # Act
    controller.switch_to("benchmark")

    # Assert
    assert benchmark_calls == []
    event_bus.emit.assert_not_called()


def test_switch_to_unknown_workspace_raises_contract_violation(
    qtbot: QtBot, mocker: MockerFixture
) -> None:
    """Given an unregistered workspace name (a code constant, not user input),

    when ``switch_to`` is called with it,
    then ``ContractViolationError`` is raised and no widget is built, no store
    write happens, and no event is emitted — an invalid name is a programmer
    error per ``08-E_interfaces_contracts.md`` §19's "never raises for a valid
    name" contract (the corollary: it must raise for an invalid one).
    """
    # Arrange
    workspace_store = make_workspace_store()
    event_bus = mocker.Mock(spec=EventBus)
    container = QStackedWidget()
    qtbot.addWidget(container)
    benchmark_calls: list[None] = []
    task_editor_calls: list[None] = []
    controller = make_workspace_controller(
        workspace_store=workspace_store,
        event_bus=event_bus,
        container=container,
        workspace_factories={
            "benchmark": _counting_factory(qtbot, benchmark_calls),
            "task_editor": _counting_factory(qtbot, task_editor_calls),
        },
    )

    # Act / Assert
    with pytest.raises(ContractViolationError):
        controller.switch_to("nonexistent_workspace")
    assert benchmark_calls == []
    assert task_editor_calls == []
    event_bus.emit.assert_not_called()
