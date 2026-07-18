"""Unit tests for ``_internal.task_files.TaskFilesSectionWidget``
(STORY-054-AC-4, AC-6; EC-TASK-1, EC-TASK-3, EC-TASK-8)."""

from PySide6.QtCore import Qt
from pytestqt.qtbot import QtBot
import structlog

from ollama_llm_bench.adapters.native_pickers.testing import FakeNativePickers
from ollama_llm_bench.adapters.workspace_controller.testing import FakeWorkspaceController
from ollama_llm_bench.backend.domain import BenchmarkTask, TaskOrigin
from ollama_llm_bench.backend.errors import TaskFileError
from ollama_llm_bench.backend.task_files.testing import FakeTaskFileLoader
from ollama_llm_bench.ui.new_benchmark._internal.task_files import TaskFilesSectionWidget

_TASK = BenchmarkTask(task_id="t1", task_origin=TaskOrigin.FILE, question="Q?", golden_answer="A")


def _make_widget() -> tuple[TaskFilesSectionWidget, FakeTaskFileLoader]:
    loader = FakeTaskFileLoader()
    widget = TaskFilesSectionWidget(
        task_file_loader=loader,
        native_pickers=FakeNativePickers(),
        workspace=FakeWorkspaceController(),
    )
    return widget, loader


def test_added_file_shows_task_count_badge(qtbot: QtBot) -> None:
    """Proves: STORY-054-AC-4

    Covers: EC-TASK-3

    Given a valid YAML task file is added, a row is appended showing the file
    name and a (N tasks) badge equal to the loader's surviving parsed-task count
    (EC-TASK-3: a malformed individual task is already excluded upstream by the
    loader, so the badge reflects only the surviving tasks).
    """
    # Arrange
    widget, loader = _make_widget()
    qtbot.addWidget(widget)
    loader.set_tasks("/tasks/a.yaml", (_TASK,))
    # Act
    with qtbot.waitSignal(widget.rows_changed, timeout=1000):
        widget.add_files_for_test(("/tasks/a.yaml",))
    # Assert
    assert len(widget.rows) == 1
    assert widget.rows[0].file_name == "a.yaml"
    assert widget.rows[0].task_count == 1


def test_whole_file_parse_error_adds_no_row(qtbot: QtBot) -> None:
    """Proves: STORY-054-AC-4

    Covers: EC-TASK-1

    Given TaskFileLoader.load raises TaskFileError for a file (non-.yaml
    extension, unparseable YAML, or unsupported schema_version), no row is
    added and the widget shows an inline error, not a crash.
    """
    # Arrange
    widget, loader = _make_widget()
    qtbot.addWidget(widget)

    def _raise(source_path: str, /) -> tuple[BenchmarkTask, ...]:
        raise TaskFileError(message="not a YAML file")

    loader.load = _raise  # type: ignore[method-assign]  # test override of the fake's default
    # Act
    with structlog.testing.capture_logs() as logs:
        widget.add_files_for_test(("/tasks/broken.yaml",))
    # Assert
    assert widget.rows == ()
    assert widget.last_inline_error == "not a YAML file"
    assert not any(entry["log_level"] in {"error", "critical"} for entry in logs)


def test_removing_the_only_file_returns_to_empty_drop_zone(qtbot: QtBot) -> None:
    """Proves: STORY-054 Definition of done

    Covers: state_machine.md §4 (Task Files sub-machine) Populated -> EmptyDropZone

    Given the sole row is selected in the list and Remove is clicked, the widget
    drains back to zero rows -- the EmptyDropZone state -- not merely a
    decremented-but-nonzero row count.
    """
    # Arrange
    widget, loader = _make_widget()
    qtbot.addWidget(widget)
    loader.set_tasks("/tasks/a.yaml", (_TASK,))
    widget.add_files_for_test(("/tasks/a.yaml",))
    assert widget.rows[0].file_name == "a.yaml"
    widget._list.item(0).setSelected(True)
    # Act
    with qtbot.waitSignal(widget.rows_changed, timeout=1000):
        qtbot.mouseClick(  # type: ignore[no-untyped-call]  # pytest-qt provides no type stubs
            widget._remove_button, Qt.MouseButton.LeftButton
        )
    # Assert
    assert widget.rows == ()


def test_empty_folder_adds_no_row(qtbot: QtBot) -> None:
    """Proves: STORY-054-AC-6

    Covers: EC-TASK-8

    Given a folder chosen through Add Folder contains no .yaml/.yml file, no row
    is added and the widget surfaces the "no YAML files found" message.
    """
    # Arrange
    widget, _loader = _make_widget()
    qtbot.addWidget(widget)
    # Act
    widget.add_folder_for_test("/tasks/empty_folder", ())
    # Assert
    assert widget.rows == ()
    assert widget.last_toast_message == "No YAML files found in the selected folder."
