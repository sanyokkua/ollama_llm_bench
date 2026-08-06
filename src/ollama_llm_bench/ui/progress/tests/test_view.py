"""Colocated view tests for ``ui/progress/`` (STORY-058-AC-1, AC-2, AC-7; STORY-060)."""

from typing import TYPE_CHECKING, cast

from PySide6.QtWidgets import (
    QComboBox,
    QFormLayout,
    QLabel,
    QPushButton,
    QTextEdit,
    QToolButton,
    QWidget,
)
import pytest
from pytest_mock import MockerFixture
from pytestqt.qtbot import QtBot
import structlog

if TYPE_CHECKING:
    from collections.abc import Iterable

from ollama_llm_bench.backend.domain import ResultStatus, RunLogVerbosity
from ollama_llm_bench.backend.log_formatting import LogFormatter
from ollama_llm_bench.ui.progress import make_progress_widget
from ollama_llm_bench.ui.progress._internal.select import select_header
from ollama_llm_bench.ui.progress._internal.theme_lookup import resolve_theme_tokens
from ollama_llm_bench.ui.progress._internal.view import ProgressView
from ollama_llm_bench.ui.progress.models import (
    CountersViewModel,
    CurrentTaskViewModel,
    HeaderAffordances,
    LogLineViewModel,
    LogViewModel,
    RunStage,
)
from ollama_llm_bench.ui.progress.testing import FakeProgressGateway
from ollama_llm_bench.ui.progress.tests.conftest import FakeEventBus
from ollama_llm_bench.ui.theme import PlatformKind, ThemeManager, resolve_color


def _counters_vm(stage: RunStage) -> CountersViewModel:
    return CountersViewModel(
        stage=stage,
        tasks_done=0,
        tasks_total=0,
        eta_label="—",
        total_time_label="—",
        counts_by_status=dict.fromkeys(ResultStatus, 0),
        bar_segments=(),
        badge_counts=(),
        judge_phase_active=False,
        provider_label="—",
        model_label="—",
    )


# description.md §3.1's tone table, spelled out as literal theme role names -- NOT
# imported from `_internal/stage_badge.py`'s `_BASE_ROLE_BY_TONE`/`_FILL_ROLE_BY_TONE` (a
# regression in that production dict must fail this test, not be silently mirrored by it).
_STAGE_TONE_TABLE: tuple[tuple[RunStage, str, str], ...] = (
    (RunStage.INITIALIZING, "info.base", "info.fill"),
    (RunStage.INFERENCE, "primary.base", "primary.disabled"),
    (RunStage.KEYWORD_CHECK, "warning.base", "warning.fill"),
    (RunStage.COSINE_CHECK, "warning.base", "warning.fill"),
    (RunStage.JUDGE_CHECK, "warning.base", "warning.fill"),
    (RunStage.COMPLETED, "success.base", "success.fill"),
    (RunStage.FAILED, "error.base", "error.fill"),
    (RunStage.STOPPED, "muted.base", "muted.fill"),
    (RunStage.PAUSED, "muted.base", "muted.fill"),
)


@pytest.mark.parametrize(
    ("stage", "expected_base_role", "expected_fill_role"),
    _STAGE_TONE_TABLE,
    ids=[case[0].value for case in _STAGE_TONE_TABLE],
)
def test_stage_badge_tone_per_stage_table(  # noqa: PLR0913  # one parametrize table (3 columns)
    # plus three independently-overridable fixtures
    stage: RunStage,
    expected_base_role: str,
    expected_fill_role: str,
    qtbot: QtBot,
    theme_manager: ThemeManager,
    platform_kind: PlatformKind,
) -> None:
    """Proves: STORY-058-AC-1

    For each RunStage the AC-1 table names, the header stage badge resolves
    the tone's colour roles -- checked against the literal expected theme
    role names from description.md §3.1's table, independent of the
    production tone-lookup dicts.
    """
    # Arrange
    view = ProgressView(theme_manager=theme_manager, platform_kind=platform_kind)
    qtbot.addWidget(view)
    tokens = resolve_theme_tokens(theme_manager=theme_manager, platform_kind=platform_kind)

    # Act
    view.apply_counters(_counters_vm(stage))

    # Assert
    assert view.stage_badge.current_base_color_hex() == resolve_color(tokens, expected_base_role)
    assert view.stage_badge.current_fill_color_hex() == resolve_color(tokens, expected_fill_role)


@pytest.mark.parametrize("stage", list(RunStage))
def test_stage_badge_always_carries_stage_name_text(
    stage: RunStage, qtbot: QtBot, theme_manager: ThemeManager, platform_kind: PlatformKind
) -> None:
    """Proves: STORY-058-AC-1

    For every RunStage (including FINISHING, outside AC-1's tone table), the
    header stage badge's tooltip and accessible name always carry the
    stage's own name text.
    """
    # Arrange
    view = ProgressView(theme_manager=theme_manager, platform_kind=platform_kind)
    qtbot.addWidget(view)

    # Act
    view.apply_counters(_counters_vm(stage))

    # Assert
    assert stage.value in view.stage_badge.toolTip()
    assert stage.value in view.stage_badge.accessibleName()


# state_machine.md §4's full per-state affordance matrix (not just the story's
# looser restated table -- cross-checked directly against the spec): Pause/Stop
# are **hidden** (not merely disabled) in Empty/ViewingPastRun, visible (possibly
# disabled) in every other non-terminal state.
_HEADER_STATE_CASES = [
    # widget_state, pencil_visible, pause_visible, pause_enabled, stop_visible, stop_enabled
    ("Empty", False, False, False, False, False),
    ("Initializing", True, True, False, True, True),
    ("Running", True, True, True, True, True),
    ("Paused", True, True, True, True, True),
    ("Stopping", False, True, False, True, False),
    ("ViewingPastRun", False, False, False, False, False),
]


@pytest.mark.parametrize(
    (
        "widget_state",
        "pencil_visible",
        "pause_visible",
        "pause_enabled",
        "stop_visible",
        "stop_enabled",
    ),
    _HEADER_STATE_CASES,
)
def test_header_controls_visibility_per_run_state(  # noqa: PLR0913  # one parametrize table
    widget_state: str,
    pencil_visible: bool,  # noqa: FBT001  # pytest.mark.parametrize table column
    pause_visible: bool,  # noqa: FBT001  # pytest.mark.parametrize table column
    pause_enabled: bool,  # noqa: FBT001  # pytest.mark.parametrize table column
    stop_visible: bool,  # noqa: FBT001  # pytest.mark.parametrize table column
    stop_enabled: bool,  # noqa: FBT001  # pytest.mark.parametrize table column
    qtbot: QtBot,
) -> None:
    """Proves: STORY-058-AC-2

    Given the displayed run's top-level widget state, the rename pencil is
    visible and Pause/Stop are enabled only while a run is actively executing
    (or paused for Pause/Stop). Pause/Stop are **hidden entirely** (not merely
    disabled) in the Empty and ViewingPastRun states -- `08-L_ui_standardization.md`
    §1's no-placeholder-UI rule -- and remain visible-but-disabled in Initializing
    (Pause) and Stopping (both), a transiently-disabled control about to become
    actionable/inactionable.
    """
    # Arrange
    view = ProgressView()
    qtbot.addWidget(view)
    view.show()
    affordances = select_header(widget_state=widget_state)

    # Act
    view.apply_header(run_name="Run 1", affordances=affordances)

    # Assert
    pencil = cast("QToolButton", view.findChild(QToolButton, "rename_run_button"))
    pause_resume = cast("QPushButton", view.findChild(QPushButton, "progress.header.pause_resume"))
    stop = cast("QPushButton", view.findChild(QPushButton, "progress.header.stop"))
    assert pencil.isVisible() == pencil_visible
    assert pause_resume.isVisible() == pause_visible
    assert pause_resume.isEnabled() == pause_enabled
    assert stop.isVisible() == stop_visible
    assert stop.isEnabled() == stop_enabled


def test_progress_widget_constructs_and_shows_with_no_error_logs(
    qtbot: QtBot,
    fake_event_bus: FakeEventBus,
    fake_gateway: FakeProgressGateway,
    mocker: MockerFixture,
) -> None:
    """Proves: STORY-058-AC-7

    Constructed via its own factory (`make_progress_widget`) with a fake
    ProgressGateway and fakes for the declared collaborators (EventBus and
    LogFormatter), mounted under qtbot and shown, no exception is raised, the
    widget reports isVisible(), and no error/critical-level structlog record
    is captured.
    """
    # Arrange
    log_formatter = mocker.Mock(spec=LogFormatter)

    # Act
    with structlog.testing.capture_logs() as logs:
        widget = make_progress_widget(
            bus=fake_event_bus, gateway=fake_gateway, log_formatter=log_formatter
        )
        qtbot.addWidget(widget)
        widget.show()
        qtbot.wait(0)

    # Assert
    assert widget.isVisible()
    assert not any(entry["log_level"] in {"error", "critical"} for entry in logs)


def test_run_name_label_renders_via_apply_header(qtbot: QtBot) -> None:
    """Proves: STORY-058-AC-2

    The run-name label reflects `apply_header`'s `run_name` argument.
    """
    # Arrange
    view = ProgressView()
    qtbot.addWidget(view)

    # Act
    view.apply_header(
        run_name="Nightly Run",
        affordances=HeaderAffordances(
            show_rename_pencil=True,
            pause_resume_label="Pause",
            pause_resume_visible=True,
            pause_resume_enabled=True,
            stop_visible=True,
            stop_enabled=True,
        ),
    )

    # Assert
    label = cast("QLabel", view.findChild(QLabel, "progress.header.run_name"))
    assert label.text() == "Nightly Run"


def _current_task_vm(  # noqa: PLR0913  # test fixture builder; six independently-optional toggles
    *,
    retry_active: bool = False,
    retry_label: str | None = None,
    inference_visible: bool = False,
    inference_label: str | None = None,
    judge_visible: bool = False,
    judge_label: str | None = None,
) -> CurrentTaskViewModel:
    return CurrentTaskViewModel(
        task_id="task-1",
        stage_label="inference",
        task_time_label="5s",
        timeouts=0,
        retry_active=retry_active,
        retry_label=retry_label,
        inference_progress_visible=inference_visible,
        inference_progress_label=inference_label,
        judge_progress_visible=judge_visible,
        judge_progress_label=judge_label,
        last_progress_context=None,
    )


def test_current_task_grid_renders_task_id_stage_and_task_time(qtbot: QtBot) -> None:
    """Proves: STORY-059-AC-1

    The Task/Stage/Task Time labels reflect apply_current_task's ViewModel.
    """
    # Arrange
    view = ProgressView()
    qtbot.addWidget(view)

    # Act
    view.apply_current_task(_current_task_vm())

    # Assert
    task_label = cast("QLabel", view.findChild(QLabel, "progress.current_task.task_id"))
    stage_label = cast("QLabel", view.findChild(QLabel, "progress.current_task.stage"))
    time_label = cast("QLabel", view.findChild(QLabel, "progress.current_task.task_time"))
    assert task_label.text() == "task-1"
    assert stage_label.text() == "inference"
    assert time_label.text() == "5s"


def test_inference_progress_row_hidden_when_not_visible(qtbot: QtBot) -> None:
    """Proves: STORY-059-AC-1"""
    # Arrange
    view = ProgressView()
    qtbot.addWidget(view)
    view.show()
    form = cast("QFormLayout", view.findChild(QFormLayout, "progress.current_task.form"))

    # Act
    view.apply_current_task(_current_task_vm(inference_visible=False))

    # Assert
    assert form.isRowVisible(form.rowCount() - 2) is False


def test_inference_progress_row_shown_with_label_when_visible(qtbot: QtBot) -> None:
    """Proves: STORY-059-AC-2"""
    # Arrange
    view = ProgressView()
    qtbot.addWidget(view)
    view.show()

    # Act
    view.apply_current_task(
        _current_task_vm(
            inference_visible=True,
            inference_label="Generating — 184 tokens · 5.6 s elapsed",
        )
    )

    # Assert
    label = cast("QLabel", view.findChild(QLabel, "progress.current_task.inference_progress"))
    assert label.text() == "Generating — 184 tokens · 5.6 s elapsed"
    assert label.isVisible()


def test_judge_progress_row_shown_with_label_when_visible(qtbot: QtBot) -> None:
    """Proves: STORY-059-AC-4"""
    # Arrange
    view = ProgressView()
    qtbot.addWidget(view)
    view.show()

    # Act
    view.apply_current_task(
        _current_task_vm(judge_visible=True, judge_label="Judge: waiting for response — 0.0 s")
    )

    # Assert
    label = cast("QLabel", view.findChild(QLabel, "progress.current_task.judge_progress"))
    assert label.text() == "Judge: waiting for response — 0.0 s"
    assert label.isVisible()


def test_retry_line_renders_in_error_tone_when_active(qtbot: QtBot) -> None:
    """Proves: STORY-059-AC-5

    The retry line reuses the same error-toned badge helper.
    """
    # Arrange
    view = ProgressView()
    qtbot.addWidget(view)
    view.show()

    # Act
    view.apply_current_task(
        _current_task_vm(retry_active=True, retry_label="2/3 - Connection refused")
    )

    # Assert
    container = cast("QWidget | None", view.findChild(QWidget, "progress.current_task.retry"))
    assert container is not None
    labels = cast("Iterable[QLabel]", container.findChildren(QLabel))
    assert any(
        isinstance(child, QLabel) and child.text() == "2/3 - Connection refused" for child in labels
    )


def test_retry_line_clears_when_not_active(qtbot: QtBot) -> None:
    """Proves: STORY-059-AC-5"""
    # Arrange
    view = ProgressView()
    qtbot.addWidget(view)
    view.show()
    view.apply_current_task(
        _current_task_vm(retry_active=True, retry_label="2/3 - Connection refused")
    )

    # Act
    view.apply_current_task(_current_task_vm(retry_active=False, retry_label=None))

    # Assert
    container = cast("QWidget | None", view.findChild(QWidget, "progress.current_task.retry"))
    assert container is not None
    assert list(cast("Iterable[QLabel]", container.findChildren(QLabel))) == []


# -- Run Event Log panel (STORY-060; `implementation_structure.md` §9's View row) --


def _log_vm(
    *,
    verbosity: RunLogVerbosity = RunLogVerbosity.NORMAL,
    lines: tuple[LogLineViewModel, ...] = (),
    file_write_warning: bool = False,
    auto_scroll: bool = True,
) -> LogViewModel:
    return LogViewModel(
        verbosity=verbosity,
        lines=lines,
        search_term="",
        auto_scroll=auto_scroll,
        file_write_warning=file_write_warning,
    )


def test_apply_log_sets_verbosity_combo_without_reemitting_signal(qtbot: QtBot) -> None:
    """Proves: STORY-060-AC-2

    `apply_log` sets the verbosity combo's displayed text from
    `LogViewModel.verbosity` without re-emitting `log_verbosity_changed` -- the
    view blocks its own signal while applying the ViewModel, so a
    controller-driven re-render never bounces back into another controller
    call (`implementation_structure.md` §9's render-only View contract).
    """
    # Arrange
    view = ProgressView()
    qtbot.addWidget(view)
    received: list[str] = []
    view.log_verbosity_changed.connect(received.append)

    # Act
    view.apply_log(_log_vm(verbosity=RunLogVerbosity.VERBOSE))

    # Assert
    combo = cast("QComboBox", view.findChild(QComboBox, "progress.log.verbosity"))
    assert combo.currentText() == "Verbose"
    assert received == []


def test_apply_log_body_renders_each_line_html(qtbot: QtBot) -> None:
    """Proves: STORY-060-AC-1

    The log body's rendered text reflects every line in `LogViewModel.lines`,
    in order; the view performs no HTML construction of its own -- it only
    appends each pre-built fragment.
    """
    # Arrange
    view = ProgressView()
    qtbot.addWidget(view)
    lines = (
        LogLineViewModel(kind="task_start", html="<b>first</b>"),
        LogLineViewModel(kind="done", html="<b>second</b>"),
    )

    # Act
    view.apply_log(_log_vm(lines=lines))

    # Assert
    body = cast("QTextEdit", view.findChild(QTextEdit, "progress.log.body"))
    text = body.toPlainText()
    assert text.index("first") < text.index("second")


@pytest.mark.parametrize("file_write_warning", [True, False])
def test_apply_log_warning_label_visibility_reflects_file_write_warning(
    file_write_warning: bool,  # noqa: FBT001  # pytest.mark.parametrize table column
    qtbot: QtBot,
) -> None:
    """Proves: STORY-060-AC-5

    Covers EC-LOG-1. The write-failure warning label's visibility mirrors
    `LogViewModel.file_write_warning` -- shown only while the run-log file
    writer's last write attempt failed.
    """
    # Arrange
    view = ProgressView()
    qtbot.addWidget(view)
    view.show()

    # Act
    view.apply_log(_log_vm(file_write_warning=file_write_warning))

    # Assert
    label = cast("QLabel", view.findChild(QLabel, "progress.log.write_warning"))
    assert label.isVisible() is file_write_warning


def _many_log_lines() -> tuple[LogLineViewModel, ...]:
    return tuple(
        LogLineViewModel(kind="task_start", html=f"<span>line {i}</span>") for i in range(200)
    )


def test_apply_log_scrolls_to_bottom_when_auto_scroll_true(qtbot: QtBot) -> None:
    """Proves: STORY-060 (`description.md` §8.5's auto-scroll rule)

    `apply_log` moves the log body's scrollbar to the maximum when
    `LogViewModel.auto_scroll` is `True`, even if the user had previously
    scrolled away from the bottom.
    """
    # Arrange
    view = ProgressView()
    qtbot.addWidget(view)
    view.resize(200, 100)
    view.show()
    many_lines = _many_log_lines()
    view.apply_log(_log_vm(lines=many_lines, auto_scroll=True))
    body = cast("QTextEdit", view.findChild(QTextEdit, "progress.log.body"))
    scrollbar = body.verticalScrollBar()
    scrollbar.setValue(0)  # the user scrolled back up to read earlier lines

    # Act -- a further re-render arrives (e.g. the next pipeline event)
    view.apply_log(_log_vm(lines=many_lines, auto_scroll=True))

    # Assert
    assert scrollbar.value() == scrollbar.maximum()


def test_apply_log_preserves_scroll_position_when_auto_scroll_false(qtbot: QtBot) -> None:
    """Proves: STORY-060 (`description.md` §8.5's auto-scroll rule)

    `apply_log` must preserve the user's scroll position -- not snap back to
    the newest line -- when `LogViewModel.auto_scroll` is `False` (the
    "suspend on scroll-up" rule). See the `xfail` reason for the concrete
    defect this test caught.
    """
    # Arrange
    view = ProgressView()
    qtbot.addWidget(view)
    view.resize(200, 100)
    view.show()
    many_lines = _many_log_lines()
    view.apply_log(_log_vm(lines=many_lines, auto_scroll=True))
    body = cast("QTextEdit", view.findChild(QTextEdit, "progress.log.body"))
    scrollbar = body.verticalScrollBar()
    scrollbar.setValue(0)  # the user scrolled back up to read earlier lines

    # Act -- a further re-render arrives (e.g. the next pipeline event)
    view.apply_log(_log_vm(lines=many_lines, auto_scroll=False))

    # Assert
    assert scrollbar.value() == 0
