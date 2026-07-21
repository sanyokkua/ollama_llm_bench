"""Colocated unit test for the YAML preview panel's hard-error behaviour
(STORY-069-AC-5; EC-WS-3).
"""

from io import StringIO
from pathlib import Path

from pytestqt.qtbot import QtBot
from ruamel.yaml import YAML

from ollama_llm_bench.adapters.native_pickers.testing import FakeNativePickers
from ollama_llm_bench.backend.task_files import ValidationSeverity, make_task_file_validator
from ollama_llm_bench.backend.task_files.testing import FakeTaskFileLoader
from ollama_llm_bench.backend.yaml_formatter import make_yaml_formatter
from ollama_llm_bench.ui.task_editor.models import TaskEditorCollaborators
from ollama_llm_bench.ui.task_editor.testing import FakeFileChangeWatcher, FakeTaskEditorGateway
from ollama_llm_bench.ui.task_editor.tests.conftest import (
    FakeClipboard,
    FakeFileSystemActions,
    make_bound_task_editor_controller,
)


def test_preview_renders_for_hard_error_file(qtbot: QtBot, tmp_path: Path) -> None:
    """Proves: STORY-069-AC-5

    Covers: EC-WS-3

    Given the user opens the YAML preview for a task that has a hard error,
    when the panel renders, then it still shows the syntactically valid YAML
    the Formatter would produce and notes that Save is disabled while the
    file has errors.
    """
    # Arrange
    source_path = tmp_path / "hard_error.yaml"
    source_path.write_text('tasks:\n  - task_id: t1\n    question: ""\n', encoding="utf-8")
    native_pickers = FakeNativePickers()
    native_pickers.set_open_file_result((str(source_path),))
    collaborators = TaskEditorCollaborators(
        gateway=FakeTaskEditorGateway(),
        task_file_loader=FakeTaskFileLoader(),
        task_file_validator=make_task_file_validator(),
        yaml_formatter=make_yaml_formatter(),
        file_change_watcher=FakeFileChangeWatcher(),
        native_pickers=native_pickers,
        clipboard=FakeClipboard(),
        file_system_actions=FakeFileSystemActions(),
    )
    controller, _bus = make_bound_task_editor_controller(qtbot=qtbot, collaborators=collaborators)
    assert controller._view is not None
    controller._view.show()
    controller.on_open_file_clicked()
    assert controller._buffers[0].validation is not None
    assert controller._buffers[0].validation.severity is ValidationSeverity.ERROR

    # Act
    controller.on_view_yaml_toggled()

    # Assert
    preview_widget = controller._view._yaml_preview
    preview_text = preview_widget.preview_text()
    parsed_document = YAML().load(StringIO(preview_text))
    assert parsed_document["tasks"][0]["task_id"] == "t1"
    assert preview_widget._disabled_note.isVisible() is True
