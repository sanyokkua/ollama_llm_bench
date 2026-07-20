"""Colocated view tests for ``ui/progress/`` (STORY-058-AC-1, AC-2, AC-7)."""

from typing import cast

from PySide6.QtWidgets import QFormLayout, QLabel, QPushButton, QToolButton, QWidget
import pytest
from pytest_mock import MockerFixture
from pytestqt.qtbot import QtBot
import structlog

from ollama_llm_bench.backend.domain import ResultStatus
from ollama_llm_bench.backend.log_formatting import LogFormatter
from ollama_llm_bench.ui.progress import make_progress_widget
from ollama_llm_bench.ui.progress._internal.select import select_header
from ollama_llm_bench.ui.progress._internal.theme_lookup import resolve_theme_tokens
from ollama_llm_bench.ui.progress._internal.view import ProgressView
from ollama_llm_bench.ui.progress.models import CountersViewModel, CurrentTaskViewModel, HeaderAffordances, RunStage
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
    pencil = cast("QToolButton", view.findChild(QToolButton, "progress.header.rename_pencil"))
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


def _current_task_vm(
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
    label = cast(
        "QLabel", view.findChild(QLabel, "progress.current_task.inference_progress")
    )
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
    container = view.findChild(QWidget, "progress.current_task.retry")
    assert container is not None
    assert any(
        isinstance(child, QLabel) and child.text() == "2/3 - Connection refused"
        for child in container.findChildren(QLabel)
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
    container = view.findChild(QWidget, "progress.current_task.retry")
    assert container is not None
    assert container.findChildren(QLabel) == []
