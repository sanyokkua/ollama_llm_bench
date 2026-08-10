"""Integration tests: dropping YAML task files and folders onto the New Benchmark
Task Files section (STORY-084; EC-TASK-1).

Lives in ``tests/integration/`` rather than the colocated
``ui/new_benchmark/tests/`` because it drives the real ``backend/task_files``
loader against real files on disk, crossing a module boundary
(07_TESTING_STANDARD.md layout rule).
"""

from collections.abc import Callable
from pathlib import Path
from typing import cast

from PySide6.QtCore import QMimeData, QPoint, QPointF, Qt, QUrl
from PySide6.QtGui import QDragEnterEvent, QDropEvent
from PySide6.QtWidgets import QApplication, QLabel
from pytestqt.qtbot import QtBot

from ollama_llm_bench.adapters.native_pickers.testing import FakeNativePickers
from ollama_llm_bench.adapters.workspace_controller.testing import FakeWorkspaceController
from ollama_llm_bench.backend.domain import RunMode
from ollama_llm_bench.backend.events import EventBus, Subscription
from ollama_llm_bench.backend.mode_visibility import visible_sections
from ollama_llm_bench.backend.task_files import make_task_file_loader
from ollama_llm_bench.ui.new_benchmark import NewBenchmarkCollaborators, make_new_benchmark_widget
from ollama_llm_bench.ui.new_benchmark._internal.view import NewBenchmarkView
from ollama_llm_bench.ui.new_benchmark.testing import FakeNewBenchmarkGateway, FakeRunValidator
from ollama_llm_bench.ui.theme import PlatformKind, ThemeSetting, make_theme_manager

_VALID_YAML = "tasks:\n  - task_id: t1\n    question: Q?\n"
_TWO_TASK_YAML = "tasks:\n  - task_id: t1\n    question: Q?\n  - task_id: t2\n    question: Q2?\n"
_UNPARSEABLE_YAML = "tasks:\n  - task_id: [unclosed\n"


class _FakeSubscription:
    """A cancellable handle mirroring the real EventBus's Subscription contract."""

    def __init__(self, cancel_fn: Callable[[], None]) -> None:
        self._cancel_fn = cancel_fn

    def cancel(self) -> None:
        self._cancel_fn()


class _FakeEventBus:
    """A synchronous, in-process EventBus test double, local to this integration test."""

    def __init__(self) -> None:
        self._handlers: dict[str, list[Callable[[object], None]]] = {}

    def subscribe(
        self, signal_name: str, handler: Callable[[object], None], owner: object | None = None
    ) -> Subscription:
        self._handlers.setdefault(signal_name, []).append(handler)
        return _FakeSubscription(lambda: self._handlers[signal_name].remove(handler))

    def emit(self, signal_name: str, payload: object) -> None:
        for handler in list(self._handlers.get(signal_name, [])):
            handler(payload)


class _RealBackedModeVisibilityPolicy:
    """Wraps the real backend.mode_visibility.visible_sections."""

    def visible_sections(self, mode: RunMode) -> tuple:  # type: ignore[type-arg]  # matches Protocol's bare tuple return
        return visible_sections(mode)


def _build_view(qtbot: QtBot, qapp: QApplication) -> NewBenchmarkView:
    """Build the real New Benchmark widget in Task Benchmark mode, real task-file loader."""
    theme_manager = make_theme_manager(
        app=qapp, theme_setting=ThemeSetting.DARK, platform_kind=PlatformKind.MACOS
    )
    event_bus: EventBus = _FakeEventBus()
    collaborators = NewBenchmarkCollaborators(
        gateway=FakeNewBenchmarkGateway(),
        event_bus=event_bus,
        task_file_loader=make_task_file_loader(),
        mode_visibility_policy=_RealBackedModeVisibilityPolicy(),
        run_validator=FakeRunValidator(entries=()),
        native_pickers=FakeNativePickers(),
        workspace=FakeWorkspaceController(),
        theme_manager=theme_manager,
        platform_kind=PlatformKind.MACOS,
    )
    view = make_new_benchmark_widget(collaborators=collaborators)
    assert isinstance(view, NewBenchmarkView)
    qtbot.addWidget(view)
    view.mode_selector.select_mode_for_test(RunMode.TASKS)
    return view


def _mime_for(paths: tuple[Path, ...]) -> QMimeData:
    """Build a drag payload carrying ``paths`` as local-file URLs."""
    mime = QMimeData()
    mime.setUrls([QUrl.fromLocalFile(str(path)) for path in paths])
    return mime


def _drag_enter_event(mime: QMimeData) -> QDragEnterEvent:
    """Build a drag-enter event over ``mime``; the caller must keep ``mime`` alive."""
    return QDragEnterEvent(
        QPoint(1, 1),
        Qt.DropAction.CopyAction,
        mime,
        Qt.MouseButton.LeftButton,
        Qt.KeyboardModifier.NoModifier,
    )


def _drop_event(mime: QMimeData) -> QDropEvent:
    """Build a drop event over ``mime``; the caller must keep ``mime`` alive."""
    return QDropEvent(
        QPointF(1.0, 1.0),
        Qt.DropAction.CopyAction,
        mime,
        Qt.MouseButton.LeftButton,
        Qt.KeyboardModifier.NoModifier,
    )


def test_drag_enter_accepts_yaml_files_in_task_modes(
    qtbot: QtBot, qapp: QApplication, tmp_path: Path
) -> None:
    """Proves: STORY-084-AC-1

    Given the Task Files section in Task Benchmark mode -- where the real
    mode-visibility policy makes it visible, and therefore reachable by a drag --
    when a drag carrying a local YAML task-file path enters it, the drag-enter
    event is accepted so the drop is permitted (description.md §5).
    """
    # Arrange
    view = _build_view(qtbot, qapp)
    assert view.task_files_section.isVisibleTo(view)
    task_file = tmp_path / "a.yaml"
    task_file.write_text(_VALID_YAML, encoding="utf-8")
    mime = _mime_for((task_file,))
    event = _drag_enter_event(mime)
    # Act
    view.task_files_section.dragEnterEvent(event)
    # Assert
    assert event.isAccepted()


def test_drag_enter_ignores_a_drag_without_yaml_paths(
    qtbot: QtBot, qapp: QApplication, tmp_path: Path
) -> None:
    """Proves: STORY-084-AC-1

    The negative half: a drag carrying a local file that is neither a YAML file
    nor a folder is ignored, so the cursor never signals a drop the widget cannot
    honour (description.md §5).
    """
    # Arrange
    view = _build_view(qtbot, qapp)
    other_file = tmp_path / "notes.json"
    other_file.write_text("{}", encoding="utf-8")
    mime = _mime_for((other_file,))
    event = _drag_enter_event(mime)
    # Act
    view.task_files_section.dragEnterEvent(event)
    # Assert
    assert not event.isAccepted()


def test_dropping_valid_task_files_appends_rows(
    qtbot: QtBot, qapp: QApplication, tmp_path: Path
) -> None:
    """Proves: STORY-084-AC-2

    Given valid YAML task files dropped onto the Task Files list, each file is
    parsed by the real TaskFileLoader and appended as a row carrying its parsed
    task count (description.md §4.3, flow_diagram.md §4).
    """
    # Arrange
    view = _build_view(qtbot, qapp)
    one_task = tmp_path / "one.yaml"
    one_task.write_text(_VALID_YAML, encoding="utf-8")
    two_tasks = tmp_path / "two.yaml"
    two_tasks.write_text(_TWO_TASK_YAML, encoding="utf-8")
    mime = _mime_for((one_task, two_tasks))
    event = _drop_event(mime)
    # Act
    with qtbot.waitSignal(view.task_files_section.rows_changed, timeout=1000):
        view.task_files_section.dropEvent(event)
    # Assert
    assert [(row.file_name, row.task_count) for row in view.task_files_section.rows] == [
        ("one.yaml", 1),
        ("two.yaml", 2),
    ]


def test_dropping_malformed_file_shows_inline_error_and_adds_no_row(
    qtbot: QtBot, qapp: QApplication, tmp_path: Path
) -> None:
    """Proves: STORY-084-AC-3

    Covers: EC-TASK-1

    Given a YAML file whose text does not parse is dropped onto the Task Files
    list, the TaskFileLoader rejects it, the widget surfaces a visible inline
    error, and no row is added -- the "dropped" half of EC-TASK-1's "Malformed
    YAML file dropped or added" (description.md §13).
    """
    # Arrange
    view = _build_view(qtbot, qapp)
    broken = tmp_path / "broken.yaml"
    broken.write_text(_UNPARSEABLE_YAML, encoding="utf-8")
    mime = _mime_for((broken,))
    event = _drop_event(mime)
    error_label = cast(
        "QLabel",
        view.task_files_section.findChild(QLabel, "new_benchmark.task_files.error_label"),
    )
    # Act
    view.task_files_section.dropEvent(event)
    # Assert
    assert view.task_files_section.rows == ()
    assert error_label.isVisibleTo(view)
    assert error_label.text() == view.task_files_section.last_inline_error
