"""Integration tests for the Task Editor's half of the quit sequence (STORY-114).

These build the *real* application through ``build_app`` and drive the real
``CloseHandler`` prompts, so they prove the whole chain the story wires:
``TaskEditorController`` -> ``TaskEditorWorkspace`` -> ``compose.py`` ->
``make_main_window`` -> ``CloseHandler``.

**The modal hazard.** ``tests/integration/conftest.py`` installs a directory-wide
autouse event filter that *hides* any ``QMessageBox`` 100 ms after it is shown. A
hidden box leaves ``clickedButton()`` as ``None``, which ``CloseHandler`` reads as
"cancel". Every test here therefore installs ``_AnswerQuitPrompts``, which reacts
to the same ``Show`` event but schedules its click at 0 ms -- inside the box's own
nested ``exec()`` loop and comfortably ahead of that 100 ms dismissal.

The answerer is an event filter rather than a pre-armed one-shot timer because the
running-benchmark path shows its two prompts about five seconds apart (the bounded
shutdown wait sits between them), so there is no single moment at which both could
be armed.
"""

from collections.abc import Callable
import functools
from pathlib import Path
from typing import Final, cast

from PySide6.QtCore import QEvent, QObject, Qt, QTimer
from PySide6.QtWidgets import QApplication, QMessageBox, QPushButton, QWidget
from pytest_mock import MockerFixture
from pytestqt.qtbot import QtBot

from ollama_llm_bench.compose import AppHandle

_CLEAN_TASK_YAML: Final[str] = (
    "schema_version: 1\n"
    "tasks:\n"
    '  - task_id: "t1"\n'
    "    difficulty: medium\n"
    '    question: "What is 2+2?"\n'
    '    golden_answer: "4"\n'
    '    pass_criteria: "answer is correct"\n'
    '    fail_criteria: "answer is incorrect"\n'
    "    required_terms:\n"
    "      exact: []\n"
    "      semantic: []\n"
    "      forbidden: []\n"
)
_EDITED_QUESTION: Final[str] = "What is 2+3?"
_BLANK_QUESTION: Final[str] = "   "
_SAVE_BUTTON: Final[str] = "main_window.quit_unsaved.save_button"
_DISCARD_BUTTON: Final[str] = "main_window.quit_unsaved.discard_button"
_HELD_CLOSE_BUTTON: Final[str] = "main_window.quit_unsaved_held.close_button"
_RUNNING_CONFIRM_BUTTON: Final[str] = "main_window.quit_confirm.confirm_button"
_TWO_DIRTY_FILES_PROMPT: Final[str] = "Save changes to 2 file(s)?"
_BOUNDED_SHUTDOWN_WAIT_MS: Final[int] = 9000


class _AnswerQuitPrompts(QObject):
    """Click one named button on each ``CloseHandler`` prompt, in the given order.

    Each ``Show`` of a ``QMessageBox`` schedules a 0 ms callback that looks for the
    next expected button on that box. ``QMessageBox.exec()`` runs its own nested
    event loop, so a 0 ms single-shot armed from the ``Show`` event fires inside
    that loop -- ahead of the directory-wide 100 ms auto-dismissal.

    A box carrying none of the expected buttons (the readiness modal, say) is left
    alone rather than consuming a scripted answer.

    **Why ``button.click()`` and not ``qtbot.mouseClick``.** A synthetic mouse click
    is delivered at the button's centre *coordinate*, and 0 ms after a modal's
    ``show()`` the dialog's layout has not reliably settled -- the click then lands
    outside the button and is silently lost, which made this suite fail roughly
    every other run. ``click()`` goes through the same Qt ``clicked()`` path
    ``QMessageBox`` listens on, without depending on geometry.
    """

    def __init__(self, *, expected_buttons: list[str]) -> None:
        super().__init__()
        self._pending = list(expected_buttons)
        self.captured_texts: list[str] = []

    @property
    def answered_prompts(self) -> int:
        """How many of the expected prompts have been answered so far."""
        return len(self.captured_texts)

    def eventFilter(self, watched: QObject, event: QEvent) -> bool:
        if event.type() == QEvent.Type.Show and isinstance(watched, QMessageBox):
            QTimer.singleShot(0, functools.partial(self._answer, watched))
        return False

    def _answer(self, box: QMessageBox) -> None:
        for name in list(self._pending):
            # findChildren (not findChild) because its list return type lets a
            # "this box carries none of my buttons" check typecheck cleanly.
            matches: list[QPushButton] = list(box.findChildren(QPushButton, name))
            if not matches:
                continue
            self._pending.remove(name)
            self.captured_texts.append(box.text())
            matches[0].click()
            return


def _install_answerer(*, qapp: QApplication, expected_buttons: list[str]) -> _AnswerQuitPrompts:
    """Install an answerer on ``qapp`` and return it.

    **The caller must keep the returned object alive.** ``installEventFilter``
    takes no ownership, so an unbound answerer is garbage-collected as soon as
    this function returns, taking its C++ side -- and the installed filter -- with
    it. That fails silently: the prompt then falls through to the directory-wide
    100 ms dismissal and ``CloseHandler`` reads the un-clicked box as "cancel".
    Every test here therefore binds it and asserts ``answered_prompts``.
    """
    answerer = _AnswerQuitPrompts(expected_buttons=expected_buttons)
    qapp.installEventFilter(answerer)
    return answerer


def _switch_to_task_editor(handle: AppHandle, qtbot: QtBot) -> QWidget:
    """Click through to the Task Editor workspace and return its root view."""
    button = cast(
        "QPushButton", handle.window.findChild(QPushButton, "workspace_task_editor_button")
    )
    qtbot.mouseClick(  # type: ignore[no-untyped-call]  # pytest-qt provides no type stubs
        button, Qt.MouseButton.LeftButton
    )
    return cast("QWidget", handle.window.findChild(QWidget, "task_editor.view"))


def _drop_files(view: QWidget, paths: tuple[Path, ...]) -> None:
    """Open ``paths`` in the editor through the view's own drag-drop signal.

    Driving ``files_dropped`` is the realistic path that needs no native
    ``QFileDialog``: the real production handler, buffers, validator and YAML
    formatter all run for real behind it.
    """
    view.files_dropped.emit(tuple(str(path) for path in paths))  # type: ignore[attr-defined]  # TaskEditorView signal


def _dirty_open_files(view: QWidget, questions: tuple[str, ...]) -> None:
    """Edit the ``question`` field of each open file, one per ``questions`` entry.

    A blank question is the real validation cascade's ``empty_question`` hard
    error, which is how a test arranges an unsaveable dirty buffer without faking
    the validator away.
    """
    for index, question in enumerate(questions):
        view.file_row_selected.emit(index)  # type: ignore[attr-defined]  # TaskEditorView signal
        view.task_row_selected.emit(0)  # type: ignore[attr-defined]  # TaskEditorView signal
        view.field_focus_lost.emit("question", question)  # type: ignore[attr-defined]  # TaskEditorView signal


def _seed_task_files(tmp_path: Path, names: tuple[str, ...]) -> tuple[Path, ...]:
    paths = tuple(tmp_path / name for name in names)
    for path in paths:
        path.write_text(_CLEAN_TASK_YAML, encoding="utf-8")
    return paths


def test_unsaved_prompt_reports_the_real_dirty_buffer_count(
    build_real_app: Callable[[], AppHandle],
    qapp: QApplication,
    qtbot: QtBot,
    tmp_path: Path,
) -> None:
    """Proves: STORY-114-AC-1

    Given three task files are open and two of them hold unsaved edits, when the
    user requests a quit, then the unsaved-changes prompt appears and reports two
    files -- the real count, not the hard-wired zero that used to suppress it.
    """
    # Arrange
    handle = build_real_app()
    view = _switch_to_task_editor(handle, qtbot)
    paths = _seed_task_files(tmp_path, ("first.yaml", "second.yaml", "untouched.yaml"))
    _drop_files(view, paths)
    _dirty_open_files(view, (_EDITED_QUESTION, _EDITED_QUESTION))
    answerer = _install_answerer(qapp=qapp, expected_buttons=[_DISCARD_BUTTON])

    # Act
    handle.window.close()

    # Assert
    assert answerer.captured_texts == [_TWO_DIRTY_FILES_PROMPT]


def test_save_all_writes_every_clean_dirty_buffer(
    build_real_app: Callable[[], AppHandle],
    qapp: QApplication,
    qtbot: QtBot,
    tmp_path: Path,
    mocker: MockerFixture,
) -> None:
    """Proves: STORY-114-AC-2

    Given two dirty task files and no hard validation error, when the user
    chooses "Save all" at the quit confirmation, then both files are written to
    disk and the quit proceeds.
    """
    # Arrange
    handle = build_real_app()
    force_close = mocker.spy(handle.window, "force_close")
    view = _switch_to_task_editor(handle, qtbot)
    first, second = _seed_task_files(tmp_path, ("first.yaml", "second.yaml"))
    _drop_files(view, (first, second))
    _dirty_open_files(view, (_EDITED_QUESTION, _EDITED_QUESTION))
    answerer = _install_answerer(qapp=qapp, expected_buttons=[_SAVE_BUTTON])

    # Act
    handle.window.close()

    # Assert
    assert (
        answerer.answered_prompts,
        _EDITED_QUESTION in first.read_text(encoding="utf-8"),
        _EDITED_QUESTION in second.read_text(encoding="utf-8"),
        force_close.call_count,
    ) == (1, True, True, 1)


def test_save_all_holds_the_quit_when_a_file_has_a_hard_error(
    build_real_app: Callable[[], AppHandle],
    qapp: QApplication,
    qtbot: QtBot,
    tmp_path: Path,
    mocker: MockerFixture,
) -> None:
    """Proves: STORY-114-AC-3

    Given two dirty task files of which one still holds a hard validation error,
    when the user chooses "Save all" at the quit confirmation, then the error-free
    file is written, the file that could not be saved is named to the user, and
    the quit is held -- the window is never closed.
    """
    # Arrange
    handle = build_real_app()
    force_close = mocker.spy(handle.window, "force_close")
    view = _switch_to_task_editor(handle, qtbot)
    first, broken = _seed_task_files(tmp_path, ("first.yaml", "broken.yaml"))
    _drop_files(view, (first, broken))
    _dirty_open_files(view, (_EDITED_QUESTION, _BLANK_QUESTION))
    answerer = _install_answerer(qapp=qapp, expected_buttons=[_SAVE_BUTTON, _HELD_CLOSE_BUTTON])

    # Act
    handle.window.close()

    # Assert
    assert (
        answerer.answered_prompts,
        _EDITED_QUESTION in first.read_text(encoding="utf-8"),
        "broken.yaml" in answerer.captured_texts[-1],
        force_close.call_count,
    ) == (2, True, True, 0)


def test_discard_all_writes_nothing_and_quits(
    build_real_app: Callable[[], AppHandle],
    qapp: QApplication,
    qtbot: QtBot,
    tmp_path: Path,
    mocker: MockerFixture,
) -> None:
    """Proves: STORY-114-AC-4

    Given two dirty task files, when the user chooses "Discard all" at the quit
    confirmation, then neither file on disk is modified and the quit proceeds.
    """
    # Arrange
    handle = build_real_app()
    force_close = mocker.spy(handle.window, "force_close")
    view = _switch_to_task_editor(handle, qtbot)
    first, second = _seed_task_files(tmp_path, ("first.yaml", "second.yaml"))
    _drop_files(view, (first, second))
    _dirty_open_files(view, (_EDITED_QUESTION, _EDITED_QUESTION))
    answerer = _install_answerer(qapp=qapp, expected_buttons=[_DISCARD_BUTTON])

    # Act
    handle.window.close()

    # Assert
    assert (
        answerer.answered_prompts,
        first.read_text(encoding="utf-8"),
        second.read_text(encoding="utf-8"),
        force_close.call_count,
    ) == (1, _CLEAN_TASK_YAML, _CLEAN_TASK_YAML, 1)


def test_quit_with_dirty_buffers_during_a_run_never_touches_run_control(
    build_real_app_without_enabled_providers: Callable[[], AppHandle],
    qapp: QApplication,
    qtbot: QtBot,
    tmp_path: Path,
    mocker: MockerFixture,
) -> None:
    """Proves: STORY-114-AC-6

    Given a run is in progress and the Task Editor holds dirty buffers, when the
    user quits and answers both confirmations toward quitting, then the Task
    Editor issues no run-control call -- no pause, no stop -- and the quit runs
    the standard bounded-shutdown path exactly once (EC-TE-11).
    """
    # Arrange
    handle = build_real_app_without_enabled_providers()
    mocker.patch.object(handle.flow, "is_running", return_value=True)
    pause = mocker.spy(handle.flow, "pause")
    stop = mocker.spy(handle.flow, "stop")
    shutdown = mocker.spy(handle.flow, "shutdown")
    force_close = mocker.spy(handle.window, "force_close")
    view = _switch_to_task_editor(handle, qtbot)
    first, second = _seed_task_files(tmp_path, ("first.yaml", "second.yaml"))
    _drop_files(view, (first, second))
    _dirty_open_files(view, (_EDITED_QUESTION, _EDITED_QUESTION))
    answerer = _install_answerer(
        qapp=qapp, expected_buttons=[_RUNNING_CONFIRM_BUTTON, _DISCARD_BUTTON]
    )

    # Act -- the unsaved-changes prompt only opens once the bounded shutdown wait
    # settles, which with no genuinely-running pipeline means its full timeout.
    handle.window.close()
    qtbot.waitUntil(lambda: force_close.call_count == 1, timeout=_BOUNDED_SHUTDOWN_WAIT_MS)

    # Assert
    assert (
        answerer.answered_prompts,
        pause.call_count,
        stop.call_count,
        shutdown.call_count,
    ) == (2, 0, 0, 1)
