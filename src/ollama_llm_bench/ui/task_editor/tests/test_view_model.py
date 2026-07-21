"""Colocated unit tests for the pure view-model selection function (STORY-068-AC-1)
and the factory-level construction/interaction smoke test (STORY-068-AC-7)."""

from collections.abc import Iterator
from contextlib import contextmanager

from PySide6.QtWidgets import QWidget
from pytestqt.qtbot import QtBot
from ruamel.yaml.comments import CommentedMap, CommentedSeq
import structlog

from ollama_llm_bench.backend.task_files import FileValidationResult, ValidationSeverity
from ollama_llm_bench.ui.task_editor import TaskEditorCollaborators, make_task_editor_workspace
from ollama_llm_bench.ui.task_editor._internal.buffer import TaskBuffer
from ollama_llm_bench.ui.task_editor._internal.view_model_select import (
    select_task_editor_view_model,
)
from ollama_llm_bench.ui.task_editor.tests.conftest import FakeEventBus


@contextmanager
def _isolated_structlog_defaults() -> Iterator[None]:
    """Snapshot and restore ``structlog``'s process-global configuration.

    Mirrors ``ui/results/tests/test_summary_tab.py``'s helper of the same name:
    ``structlog.testing.capture_logs()`` only swaps the processor chain, never
    ``wrapper_class``. If an earlier test already called ``configure_logging(...)``
    (installing a process-global ``INFO``-filtering ``wrapper_class`` with no
    teardown), every ``DEBUG``-level call becomes a silent no-op regardless of
    ``capture_logs()`` -- making this test's DEBUG-event assertion depend on
    execution order across module boundaries.
    """
    original_config = structlog.get_config()
    structlog.reset_defaults()
    try:
        yield
    finally:
        structlog.configure(**original_config)


def _make_empty_buffer(path: str) -> TaskBuffer:
    document = CommentedMap()
    document["tasks"] = CommentedSeq()
    return TaskBuffer(source_path=path, document=document)


def test_empty_to_with_files_transition() -> None:
    """Proves: STORY-068-AC-1

    With no open buffers the derived view-model is the Empty state
    (``is_empty`` True, no active file); once one buffer is open and active,
    the view-model moves to the With-files state with that file marked active.
    """
    # Arrange / Act
    empty_view_model = select_task_editor_view_model(
        buffers=(),
        active_buffer_index=None,
        active_task_index=None,
        preview_shown=False,
        preview_text="",
    )
    buffer = _make_empty_buffer("/tasks/first.yaml")
    with_files_view_model = select_task_editor_view_model(
        buffers=(buffer,),
        active_buffer_index=0,
        active_task_index=None,
        preview_shown=False,
        preview_text="",
    )

    # Assert
    assert empty_view_model.is_empty
    assert empty_view_model.active_file_index is None
    assert empty_view_model.files == ()
    assert not with_files_view_model.is_empty
    assert with_files_view_model.active_file_index == 0
    assert with_files_view_model.files[0].is_active
    assert with_files_view_model.files[0].path == "/tasks/first.yaml"


def _make_dirty_buffer(path: str, *, severity: ValidationSeverity) -> TaskBuffer:
    buffer = _make_empty_buffer(path)
    buffer.is_dirty = True
    buffer.validation = FileValidationResult(
        source_path=path, severity=severity, save_enabled=severity is not ValidationSeverity.ERROR
    )
    return buffer


def test_save_all_count_counts_dirty_error_file_but_disables_save_all() -> None:
    """Proves: STORY-068-AC-2

    Per ``description.md`` §3.2, ``Save All (N)``'s ``N`` is the count of dirty
    files regardless of validation state; a dirty file with a hard error still
    counts toward ``N`` even though it keeps Save All disabled on its own.
    """
    # Arrange
    buffer = _make_dirty_buffer("/tasks/broken.yaml", severity=ValidationSeverity.ERROR)

    # Act
    view_model = select_task_editor_view_model(
        buffers=(buffer,),
        active_buffer_index=0,
        active_task_index=None,
        preview_shown=False,
        preview_text="",
    )

    # Assert
    assert view_model.toolbar_state.save_all_count == 1
    assert view_model.toolbar_state.save_all_enabled is False


def test_save_all_count_and_enabled_with_mixed_dirty_files() -> None:
    """Proves: STORY-068-AC-2

    A dirty-clean file and a dirty-error file together give ``save_all_count
    == 2`` (both dirty files) while ``save_all_enabled`` stays ``True`` because
    at least one dirty file (the clean one) has no hard error.
    """
    # Arrange
    dirty_buffers = (
        _make_dirty_buffer("/tasks/clean.yaml", severity=ValidationSeverity.CLEAN),
        _make_dirty_buffer("/tasks/broken.yaml", severity=ValidationSeverity.ERROR),
    )
    expected_dirty_count = len(dirty_buffers)

    # Act
    view_model = select_task_editor_view_model(
        buffers=dirty_buffers,
        active_buffer_index=0,
        active_task_index=None,
        preview_shown=False,
        preview_text="",
    )

    # Assert
    assert view_model.toolbar_state.save_all_count == expected_dirty_count
    assert view_model.toolbar_state.save_all_enabled is True


def test_task_editor_workspace_constructs_and_shows_with_no_error_logs(
    qtbot: QtBot, task_editor_collaborators: TaskEditorCollaborators
) -> None:
    """Proves: STORY-068-AC-7

    Constructed via its own factory with a fake ``TaskEditorGateway`` (and
    fakes for every declared non-store helper), mounted under ``qtbot`` and
    shown, no exception is raised, the widget reports ``isVisible()``, no
    error/critical-level ``structlog`` record is captured, and the
    controller's construction emits a DEBUG-level lifecycle event (the
    design constraint requiring DEBUG-level events at construction).
    """
    # Arrange
    bus = FakeEventBus()

    # Act
    with (
        _isolated_structlog_defaults(),
        structlog.testing.capture_logs() as logs,
    ):
        widget = make_task_editor_workspace(bus=bus, collaborators=task_editor_collaborators)
        qtbot.addWidget(widget)
        widget.show()
        qtbot.wait(0)

    # Assert
    assert isinstance(widget, QWidget)
    assert widget.isVisible()
    assert not any(entry["log_level"] in {"error", "critical"} for entry in logs)
    assert any(entry["event"] == "task_editor_controller_constructed" for entry in logs)
