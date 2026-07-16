"""Integration tests for the workspace controller (STORY-045).

Wires the real ``WorkspaceStore`` (``backend/stores``, STORY-039) to the real
``QtWorkspaceController`` (``adapters/workspace_controller``) through a bare
``QStackedWidget`` container and a ``mocker.Mock(spec=EventBus)`` test double for the
event bus, per the project's mocking table (``testing-standard-pyqt`` skill). This
crosses the real store/controller/Qt-container boundary, so it lives in
``tests/integration/`` rather than the module's colocated unit tests.
"""

from collections.abc import Callable

from PySide6.QtWidgets import QLabel, QStackedWidget, QWidget
from pytest_mock import MockerFixture
from pytestqt.qtbot import QtBot

from ollama_llm_bench.adapters.workspace_controller import (
    WorkspaceHint,
    make_workspace_controller,
)
from ollama_llm_bench.backend.events import (
    SIGNAL_WORKSPACE_CHANGED,
    EventBus,
    WorkspaceChangedEvent,
)
from ollama_llm_bench.backend.stores import make_workspace_store


class _HintAwareWidget(QWidget):
    """A minimal workspace-widget stand-in satisfying the private ``_SupportsOpenPaths``
    shape, so the hint-forwarding half of AC-3 can be observed."""

    def __init__(self) -> None:
        super().__init__()
        self.opened_paths: tuple[str, ...] | None = None
        self.focus_target = QLabel(self)
        self.focus_target.setObjectName("result_summary")

    def open_paths(self, paths: tuple[str, ...]) -> None:
        """Record the pre-open paths forwarded by the controller."""
        self.opened_paths = paths


def _counting_factory(qtbot: QtBot, calls: list[None]) -> Callable[[], QWidget]:
    """Build a zero-argument widget factory that records each invocation."""

    def _factory() -> QWidget:
        calls.append(None)
        widget = QWidget()
        qtbot.addWidget(widget)
        return widget

    return _factory


def test_destination_widget_is_constructed_lazily_once(qtbot: QtBot, mocker: MockerFixture) -> None:
    """Proves: STORY-045-AC-1

    Given the controller has never shown the task-editor workspace,
    when ``switch_to("task_editor")`` is called,
    then the task-editor widget factory is invoked exactly once to construct the
    widget, and a second ``switch_to("task_editor")`` after switching away and back
    does not construct it again (lazy-once, then retained).
    """
    # Arrange
    workspace_store = make_workspace_store()
    event_bus = mocker.Mock(spec=EventBus)
    container = QStackedWidget()
    qtbot.addWidget(container)
    task_editor_calls: list[None] = []
    benchmark_calls: list[None] = []
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
    controller.switch_to("task_editor")
    controller.switch_to("benchmark")
    controller.switch_to("task_editor")

    # Assert
    expected_built_widget_count = 2  # one for benchmark, one for task_editor — ever
    assert len(task_editor_calls) == 1
    assert container.count() == expected_built_widget_count


def test_switch_updates_store_and_emits_workspace_changed(
    qtbot: QtBot, mocker: MockerFixture
) -> None:
    """Proves: STORY-045-AC-2

    Given the active workspace is ``"benchmark"``,
    when ``switch_to("task_editor")`` is called,
    then the ``WorkspaceStore`` active workspace becomes ``"task_editor"``,
    ``active()`` returns ``"task_editor"``, and exactly one ``_workspace_changed``
    event is emitted carrying ``workspace="task_editor"`` and
    ``previous_workspace="benchmark"``.
    """
    # Arrange
    workspace_store = make_workspace_store()
    event_bus = mocker.Mock(spec=EventBus)
    container = QStackedWidget()
    qtbot.addWidget(container)
    controller = make_workspace_controller(
        workspace_store=workspace_store,
        event_bus=event_bus,
        container=container,
        workspace_factories={
            "benchmark": _counting_factory(qtbot, []),
            "task_editor": _counting_factory(qtbot, []),
        },
    )

    # Act
    controller.switch_to("task_editor")

    # Assert
    assert workspace_store.active_workspace() == "task_editor"
    assert controller.active() == "task_editor"
    event_bus.emit.assert_called_once_with(
        SIGNAL_WORKSPACE_CHANGED,
        WorkspaceChangedEvent(workspace="task_editor", previous_workspace="benchmark"),
    )


def test_switch_reapplies_theme_and_applies_hint(qtbot: QtBot, mocker: MockerFixture) -> None:
    """Proves: STORY-045-AC-3

    Given a ``switch_to(name, hint)`` call with a non-empty ``WorkspaceHint``,
    when the switch completes,
    then the destination workspace has the theme reapplied and the hint applied
    (focus widget / pre-open paths forwarded to the shown workspace).
    """
    # Arrange
    workspace_store = make_workspace_store()
    event_bus = mocker.Mock(spec=EventBus)
    container = QStackedWidget()
    qtbot.addWidget(container)
    # Reparented under `container` by the controller's `addWidget` call on first
    # build, so its lifetime is already tied to `container` — not separately added
    # to `qtbot` (double-close at teardown would raise on the reparented C++ object).
    hint_widget = _HintAwareWidget()
    controller = make_workspace_controller(
        workspace_store=workspace_store,
        event_bus=event_bus,
        container=container,
        workspace_factories={
            "benchmark": _counting_factory(qtbot, []),
            "task_editor": lambda: hint_widget,
        },
    )
    widget_style = hint_widget.style()
    unpolish_spy = mocker.spy(widget_style, "unpolish")
    polish_spy = mocker.spy(widget_style, "polish")
    update_spy = mocker.spy(hint_widget, "update")
    focus_spy = mocker.spy(hint_widget.focus_target, "setFocus")
    hint = WorkspaceHint(open_paths=("a.yaml", "b.yaml"), focus_widget="result_summary")

    # Act
    controller.switch_to("task_editor", hint=hint)

    # Assert theme reapply
    unpolish_spy.assert_called_once_with(hint_widget)
    polish_spy.assert_called_once_with(hint_widget)
    update_spy.assert_called_once()
    # Assert hint applied
    focus_spy.assert_called_once()
    assert hint_widget.opened_paths == ("a.yaml", "b.yaml")
