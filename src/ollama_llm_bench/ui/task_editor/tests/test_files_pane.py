"""Colocated table-driven unit tests for the Files pane's per-file badge
rendering (STORY-068-AC-2)."""

from typing import cast

from PySide6.QtWidgets import QListWidget
import pytest
from pytestqt.qtbot import QtBot

from ollama_llm_bench.ui.task_editor._internal.files_pane import FilesPaneWidget
from ollama_llm_bench.ui.task_editor.models import FileRowViewModel, ValidationState


def _row(
    *, is_dirty: bool, validation_state: ValidationState, is_external_changed: bool
) -> FileRowViewModel:
    return FileRowViewModel(
        path="/tasks/sample.yaml",
        display_name="sample.yaml",
        is_dirty=is_dirty,
        is_active=True,
        validation_state=validation_state,
        is_external_changed=is_external_changed,
        is_in_use_by_run=False,
    )


@pytest.mark.parametrize(
    ("row", "expected_badge"),
    [
        pytest.param(
            _row(
                is_dirty=False,
                validation_state=ValidationState.CLEAN,
                is_external_changed=False,
            ),
            "[clean]",
            id="saved_and_valid",
        ),
        pytest.param(
            _row(is_dirty=True, validation_state=ValidationState.CLEAN, is_external_changed=False),
            "[dirty]",
            id="unsaved_edits",
        ),
        pytest.param(
            _row(
                is_dirty=False,
                validation_state=ValidationState.WARNING,
                is_external_changed=False,
            ),
            "[warning]",
            id="soft_warnings",
        ),
        pytest.param(
            _row(is_dirty=False, validation_state=ValidationState.ERROR, is_external_changed=False),
            "[error]",
            id="hard_errors",
        ),
        pytest.param(
            _row(is_dirty=False, validation_state=ValidationState.CLEAN, is_external_changed=True),
            "[reload pending]",
            id="changed_on_disk",
        ),
    ],
)
def test_file_badge_per_state(qtbot: QtBot, row: FileRowViewModel, expected_badge: str) -> None:
    """Proves: STORY-068-AC-2

    For each of the five per-file states, the Files-pane row -- rendered
    through the real ``FilesPaneWidget`` -- shows exactly the badge glyph the
    acceptance criterion's table specifies (precedence: reload-pending >
    error/warning > dirty > clean).
    """
    # Arrange
    widget = FilesPaneWidget()
    qtbot.addWidget(widget)

    # Act
    widget.apply((row,))

    # Assert
    list_widget = cast("QListWidget", widget.findChild(QListWidget, "task_editor.files_pane.list"))
    assert list_widget.item(0).text() == f"{expected_badge} {row.display_name}"


def test_reload_pending_takes_precedence_over_error_and_dirty(qtbot: QtBot) -> None:
    """Proves: STORY-068-AC-2

    A row that is simultaneously dirty, in error, and externally changed
    still renders the reload-pending badge -- the table's stated precedence
    (reload-pending > error/warning > dirty > clean) applied to a row that is
    every non-clean state at once, not just one at a time.
    """
    # Arrange
    widget = FilesPaneWidget()
    qtbot.addWidget(widget)
    row = _row(is_dirty=True, validation_state=ValidationState.ERROR, is_external_changed=True)

    # Act
    widget.apply((row,))

    # Assert
    list_widget = cast("QListWidget", widget.findChild(QListWidget, "task_editor.files_pane.list"))
    assert list_widget.item(0).text() == f"[reload pending] {row.display_name}"


def test_in_use_by_run_renders_marker_alongside_badge(qtbot: QtBot) -> None:
    """Proves: STORY-068-AC-4

    A file row marked ``is_in_use_by_run`` renders the ``[in use]`` marker in
    the Files-pane row text, in addition to (not instead of) its ordinary
    validation/dirty badge -- the in-use marker is an orthogonal indicator, so
    a dirty, in-use row shows both glyphs simultaneously. The row's tooltip
    also carries the in-use explanation.
    """
    # Arrange
    widget = FilesPaneWidget()
    qtbot.addWidget(widget)
    row = FileRowViewModel(
        path="/tasks/sample.yaml",
        display_name="sample.yaml",
        is_dirty=True,
        is_active=True,
        validation_state=ValidationState.CLEAN,
        is_external_changed=False,
        is_in_use_by_run=True,
    )

    # Act
    widget.apply((row,))

    # Assert
    list_widget = cast("QListWidget", widget.findChild(QListWidget, "task_editor.files_pane.list"))
    item = list_widget.item(0)
    assert item.text() == f"[dirty] {row.display_name} [in use]"
    assert "in use" in item.toolTip().lower()
