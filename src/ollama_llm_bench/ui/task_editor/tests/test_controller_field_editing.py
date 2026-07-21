"""Colocated unit tests for ``TaskEditorController``'s field-edit/validation-debounce/
preview-refresh pipeline (STORY-069) -- not tied to one single named acceptance
criterion, but required by the story's Definition of done branch-coverage gate
(>=85% on controllers): ``on_field_text_changed``/``on_field_focus_lost``/
``on_field_boolean_changed``/``on_field_enum_changed``/``on_field_chip_values_changed``,
the validation-debounce timer, the preview-refresh timer, and Copy YAML.

The debounce/preview ``QTimer``s are fired directly by calling their private
``_on_*_fired`` handlers rather than waiting on real Qt timeout signals -- this
proves the same commit/revalidate/render logic deterministically, without a
flaky wall-clock wait (mirrors this package's existing white-box style of
reaching into ``controller._buffers`` directly).
"""

from pathlib import Path

from pytestqt.qtbot import QtBot

from ollama_llm_bench.adapters.native_pickers.testing import FakeNativePickers
from ollama_llm_bench.backend.task_files.testing import FakeTaskFileLoader
from ollama_llm_bench.backend.yaml_formatter import make_yaml_formatter
from ollama_llm_bench.ui.task_editor._internal.controller import TaskEditorController
from ollama_llm_bench.ui.task_editor.models import TaskEditorCollaborators
from ollama_llm_bench.ui.task_editor.testing import FakeFileChangeWatcher, FakeTaskEditorGateway
from ollama_llm_bench.ui.task_editor.tests.conftest import (
    FakeClipboard,
    FakeFileSystemActions,
    ScratchAwareTaskFileValidator,
    make_bound_task_editor_controller,
    make_clean_validation_result,
)


def _open_single_task_buffer(
    qtbot: QtBot, tmp_path: Path
) -> tuple[TaskEditorController, FakeClipboard]:
    """Open one clean, real-backed buffer and return the bound controller plus
    its ``FakeClipboard``."""
    source_path = tmp_path / "editable.yaml"
    source_path.write_text(
        "tasks:\n  - task_id: t1\n    question: Old?\n    difficulty: easy\n",
        encoding="utf-8",
    )
    validator = ScratchAwareTaskFileValidator()
    validator.set_validation_result(
        str(source_path), make_clean_validation_result(str(source_path))
    )
    native_pickers = FakeNativePickers()
    native_pickers.set_open_file_result((str(source_path),))
    clipboard = FakeClipboard()
    collaborators = TaskEditorCollaborators(
        gateway=FakeTaskEditorGateway(),
        task_file_loader=FakeTaskFileLoader(),
        task_file_validator=validator,
        yaml_formatter=make_yaml_formatter(),
        file_change_watcher=FakeFileChangeWatcher(),
        native_pickers=native_pickers,
        clipboard=clipboard,
        file_system_actions=FakeFileSystemActions(),
    )
    controller, _bus = make_bound_task_editor_controller(qtbot=qtbot, collaborators=collaborators)
    controller.on_open_file_clicked()
    return controller, clipboard


def test_field_text_changed_stages_a_pending_edit_and_starts_the_debounce_timer(
    qtbot: QtBot, tmp_path: Path
) -> None:
    """A text-field keystroke stages the draft and starts (but does not yet
    commit) the validation-debounce timer."""
    # Arrange
    controller, _clipboard = _open_single_task_buffer(qtbot, tmp_path)

    # Act
    controller.on_field_text_changed("question", "Draft in progress")

    # Assert
    assert controller._pending_field_edit is not None
    assert controller._pending_field_edit.draft_text == "Draft in progress"
    assert controller._buffers[0].document["tasks"][0]["question"] == "Old?"
    assert controller._validation_timer is not None
    assert controller._validation_timer.isActive()


def test_validation_debounce_firing_commits_the_pending_edit_and_revalidates(
    qtbot: QtBot, tmp_path: Path
) -> None:
    """When the validation-debounce timer fires, the staged draft is committed
    into the buffer and the buffer is revalidated."""
    # Arrange
    controller, _clipboard = _open_single_task_buffer(qtbot, tmp_path)
    controller.on_field_text_changed("question", "Committed via debounce")

    # Act
    controller._on_validation_debounce_fired()

    # Assert
    assert controller._buffers[0].document["tasks"][0]["question"] == "Committed via debounce"
    assert controller._buffers[0].is_dirty
    assert controller._pending_field_edit is None


def test_field_text_changed_while_preview_shown_schedules_preview_refresh(
    qtbot: QtBot, tmp_path: Path
) -> None:
    """A text-field keystroke while the YAML preview is open also starts the
    (separate) preview-refresh timer; firing it renders the committed draft."""
    # Arrange
    controller, _clipboard = _open_single_task_buffer(qtbot, tmp_path)
    controller.on_view_yaml_toggled()
    assert controller._preview_shown is True

    # Act
    controller.on_field_text_changed("question", "Shown in preview")
    assert controller._preview_timer is not None
    assert controller._preview_timer.isActive()
    controller._on_preview_timer_fired()

    # Assert
    assert controller._buffers[0].document["tasks"][0]["question"] == "Shown in preview"
    assert controller._view is not None
    assert "Shown in preview" in controller._view._yaml_preview.preview_text()


def test_field_focus_lost_commits_immediately_with_no_debounce(
    qtbot: QtBot, tmp_path: Path
) -> None:
    """Losing focus on a field commits its text immediately (no timer wait)
    and revalidates the buffer."""
    # Arrange
    controller, _clipboard = _open_single_task_buffer(qtbot, tmp_path)

    # Act
    controller.on_field_focus_lost("question", "Committed on blur")

    # Assert
    assert controller._buffers[0].document["tasks"][0]["question"] == "Committed on blur"
    assert controller._buffers[0].is_dirty
    assert controller._pending_field_edit is None


def test_field_boolean_changed_commits_a_real_bool_not_a_string(
    qtbot: QtBot, tmp_path: Path
) -> None:
    """Toggling the ``cosine_enabled`` checkbox writes a real Python ``bool``
    into the task mapping (STORY-069-AC-1)."""
    # Arrange
    controller, _clipboard = _open_single_task_buffer(qtbot, tmp_path)

    # Act
    controller.on_field_boolean_changed("cosine_enabled", value=False)

    # Assert
    stored_value = controller._buffers[0].document["tasks"][0]["cosine_enabled"]
    assert stored_value is False
    assert controller._buffers[0].is_dirty


def test_field_enum_changed_commits_the_selected_difficulty(qtbot: QtBot, tmp_path: Path) -> None:
    """Selecting a ``difficulty`` dropdown entry commits its string value."""
    # Arrange
    controller, _clipboard = _open_single_task_buffer(qtbot, tmp_path)

    # Act
    controller.on_field_enum_changed("difficulty", "hard")

    # Assert
    assert controller._buffers[0].document["tasks"][0]["difficulty"] == "hard"
    assert controller._buffers[0].is_dirty


def test_field_chip_values_changed_replaces_the_nested_term_list(
    qtbot: QtBot, tmp_path: Path
) -> None:
    """Editing a ``required_terms.*`` chip input replaces the whole nested
    list under ``required_terms``, keyed by its leaf name."""
    # Arrange
    controller, _clipboard = _open_single_task_buffer(qtbot, tmp_path)

    # Act
    controller.on_field_chip_values_changed("required_terms.exact", ("alpha", "beta"))

    # Assert
    required_terms = controller._buffers[0].document["tasks"][0]["required_terms"]
    assert list(required_terms["exact"]) == ["alpha", "beta"]
    assert controller._buffers[0].is_dirty


def test_copy_yaml_clicked_copies_the_rendered_preview_text(qtbot: QtBot, tmp_path: Path) -> None:
    """Copy YAML copies the currently-rendered preview text (the same text the
    preview panel shows) to the clipboard."""
    # Arrange
    controller, clipboard = _open_single_task_buffer(qtbot, tmp_path)
    controller.on_view_yaml_toggled()

    # Act
    controller.on_copy_yaml_clicked()

    # Assert
    assert clipboard.copied
    assert "task_id" in clipboard.copied[-1]
