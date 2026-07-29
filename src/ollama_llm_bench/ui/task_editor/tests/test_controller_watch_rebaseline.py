"""Colocated test for the Task Editor's save-time re-baseline of the on-disk watch
(STORY-112-AC-4).

Uses ``FakeFileChangeWatcher`` rather than the real polling watcher: the behaviour
being proven is the controller's own contract -- cancel the file's existing watch and
start a fresh one once the editor has written the file -- and asserting that contract
directly is both faster and sharper than waiting on real poll ticks. The real
watcher's side of the same story is covered by
``tests/integration/test_task_file_change_watcher.py``.
"""

from pathlib import Path

from pytestqt.qtbot import QtBot

from ollama_llm_bench.adapters.native_pickers.testing import FakeNativePickers
from ollama_llm_bench.backend.task_files.testing import FakeTaskFileLoader
from ollama_llm_bench.backend.yaml_formatter import make_yaml_formatter
from ollama_llm_bench.ui.task_editor.models import TaskEditorCollaborators
from ollama_llm_bench.ui.task_editor.testing import FakeFileChangeWatcher, FakeTaskEditorGateway
from ollama_llm_bench.ui.task_editor.tests.conftest import (
    FakeClipboard,
    FakeFileSystemActions,
    ScratchAwareTaskFileValidator,
    make_bound_task_editor_controller,
    make_clean_validation_result,
)

_WATCHES_REGISTERED_AFTER_SAVE = 2


def test_saving_through_the_editor_does_not_raise_a_conflict(qtbot: QtBot, tmp_path: Path) -> None:
    """Proves: STORY-112-AC-4

    Given a task file open in the editor and edited, when the user saves it,
    then the controller cancels that file's existing on-disk watch and starts a
    fresh one baselined on the bytes it just wrote -- leaving exactly one live
    watch -- so the editor's own write is never reported back as somebody
    else's change and the file's row stays out of the reload-pending state.
    """
    # Arrange
    source_path = tmp_path / "saved.yaml"
    source_path.write_text("tasks:\n  - task_id: t1\n    question: Q?\n", encoding="utf-8")
    validator = ScratchAwareTaskFileValidator()
    validator.set_validation_result(
        str(source_path), make_clean_validation_result(str(source_path))
    )
    native_pickers = FakeNativePickers()
    native_pickers.set_open_file_result((str(source_path),))
    watcher = FakeFileChangeWatcher()
    controller, _bus = make_bound_task_editor_controller(
        qtbot=qtbot,
        collaborators=TaskEditorCollaborators(
            gateway=FakeTaskEditorGateway(),
            task_file_loader=FakeTaskFileLoader(),
            task_file_validator=validator,
            yaml_formatter=make_yaml_formatter(),
            file_change_watcher=watcher,
            native_pickers=native_pickers,
            clipboard=FakeClipboard(),
            file_system_actions=FakeFileSystemActions(),
        ),
    )
    controller.on_open_file_clicked()
    controller.on_add_task_clicked()  # dirties the only open buffer

    # Act
    controller.on_save_clicked()

    # Assert -- the watch was re-registered (two registrations over the file's
    # lifetime) and the first one was cancelled (only one still live), so the
    # buffer is not in the ExternalChanged state after its own save.
    assert watcher.watched_paths == [str(source_path)] * _WATCHES_REGISTERED_AFTER_SAVE
    assert watcher.live_watch_count(str(source_path)) == 1
    assert controller._buffers[0].is_external_changed is False
