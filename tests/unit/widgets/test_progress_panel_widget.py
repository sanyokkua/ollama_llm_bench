"""Unit tests for ProgressPanelWidget — progress label, ETA label,
task label truncation, stage badge, and lifecycle event handling."""

import pytest
from PySide6.QtWidgets import QApplication
from pytest_mock import MockerFixture

from ollama_llm_bench.backend.core.interfaces import AppSettingsServiceApi, BenchmarkFlowApi, EventBus
from ollama_llm_bench.backend.core.models import (
    BenchmarkFinishedEvent,
    BenchmarkPausedEvent,
    BenchmarkResumedEvent,
    BenchmarkStartedEvent,
    BenchmarkStoppedEvent,
    ModelDescriptor,
    PauseReason,
    PipelineStage,
    RunMode,
    StopReason,
)
from ollama_llm_bench.ui.widgets.panels.progress_panel_widget import ProgressPanelWidget

# ---------------------------------------------------------------------------
# QApplication fixture — module scope so Qt is initialised exactly once
# ---------------------------------------------------------------------------


@pytest.fixture(scope="module")
def qapp() -> QApplication:
    """Return (or create) a QApplication instance for the module."""
    instance = QApplication.instance()
    if isinstance(instance, QApplication):
        return instance
    return QApplication([])


# ---------------------------------------------------------------------------
# Widget fixture — function scope; fresh widget per test
# ---------------------------------------------------------------------------


@pytest.fixture
def widget(qapp: QApplication, mocker: MockerFixture) -> ProgressPanelWidget:
    """Construct a ProgressPanelWidget with mock dependencies."""
    mock_bus = mocker.Mock(spec=EventBus)
    mock_flow = mocker.Mock(spec=BenchmarkFlowApi)
    mock_settings = mocker.Mock(spec=AppSettingsServiceApi)
    return ProgressPanelWidget(event_bus=mock_bus, benchmark_flow_api=mock_flow, app_settings=mock_settings)


# ---------------------------------------------------------------------------
# Group A — progress label
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    ("completed", "total", "expected"),
    [
        (0, 0, "0 / 0 (0%)"),
        (0, 10, "0 / 10 (0%)"),
        (5, 10, "5 / 10 (50%)"),
        (10, 10, "10 / 10 (100%)"),
    ],
    ids=[
        "zero_total",
        "zero_completed",
        "half_complete",
        "fully_complete",
    ],
)
def test_update_progress_label_shows_correct_text(
    widget: ProgressPanelWidget,
    completed: int,
    total: int,
    expected: str,
) -> None:
    # Act
    widget._update_progress_label(completed, total)

    # Assert
    assert widget._progress_label.text() == expected


# ---------------------------------------------------------------------------
# Group B — ETA label
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    ("estimated_remaining_ms", "expected"),
    [
        (None, "Calculating…"),
        (0.0, "< 1s"),
        (59999.0, "~59s"),
        (60000.0, "~1m 0s"),
        (840000.0, "~14m 0s"),
    ],
    ids=[
        "none_shows_calculating",
        "zero_shows_less_than_one_second",
        "sub_minute_shows_compact_seconds",
        "exactly_one_minute",
        "fourteen_minutes",
    ],
)
def test_update_eta_label_shows_correct_text(
    widget: ProgressPanelWidget,
    estimated_remaining_ms: float | None,
    expected: str,
) -> None:
    # Act
    widget._update_eta_label(estimated_remaining_ms)

    # Assert
    assert widget._eta_label.text() == expected


# ---------------------------------------------------------------------------
# Group C — task label truncation
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    ("task", "expected_display", "expected_tooltip"),
    [
        ("a" * 30, "a" * 30, "a" * 30),
        ("a" * 60, "a" * 60, "a" * 60),
        ("", "\u2013", ""),
    ],
    ids=[
        "short_task_id_shown_as_is",
        "long_task_id_shown_in_full_no_truncation",
        "empty_string_shows_dash",
    ],
)
def test_update_context_labels_task_id(
    widget: ProgressPanelWidget,
    task: str,
    expected_display: str,
    expected_tooltip: str,
) -> None:
    # Act
    widget._update_context_labels("prov", "model", task)

    # Assert
    assert widget._task_label.text() == expected_display
    assert widget._task_label.toolTip() == expected_tooltip


# ---------------------------------------------------------------------------
# Group D — stage badge text and colour
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    ("stage", "expected_label"),
    [
        (PipelineStage.INITIALIZING, "Initializing"),
        (PipelineStage.BENCHMARKING, "Benchmarking"),
        (PipelineStage.FAILED, "Failed"),
    ],
    ids=[
        "initializing_stage",
        "benchmarking_stage",
        "failed_stage",
    ],
)
def test_update_stage_badge_sets_correct_text_and_property(
    widget: ProgressPanelWidget,
    stage: PipelineStage,
    expected_label: str,
) -> None:
    # Act
    widget._update_stage_badge(stage)

    # Assert — styling is QSS-driven via pipeline_stage property
    assert widget._stage_badge.text() == expected_label
    assert widget._stage_badge.property("pipeline_stage") == stage.name


# ---------------------------------------------------------------------------
# Group E — stopped event
# ---------------------------------------------------------------------------


def test_on_benchmark_stopped_sets_stopped_badge(
    widget: ProgressPanelWidget,
) -> None:
    # Arrange
    event = BenchmarkStoppedEvent(run_id=1, stop_reason=StopReason.USER)

    # Act
    widget._on_benchmark_stopped(event)

    # Assert
    assert widget._stage_badge.text() == "Stopped"
    assert widget._stage_badge.property("pipeline_stage") is None


# ---------------------------------------------------------------------------
# Group F — finished event
# ---------------------------------------------------------------------------


def test_on_benchmark_finished_updates_eta_and_badge(
    widget: ProgressPanelWidget,
) -> None:
    # Arrange
    event = BenchmarkFinishedEvent(
        run_id=1,
        total_time_ms=1000.0,
        completed_count=5,
        failed_count=0,
    )

    # Act
    widget._on_benchmark_finished(event)

    # Assert
    assert widget._eta_label.text() == "Finished"
    assert widget._stage_badge.text() == "Finished"


# ---------------------------------------------------------------------------
# Group G — live timer lifecycle
# ---------------------------------------------------------------------------


def _make_started_event() -> BenchmarkStartedEvent:
    return BenchmarkStartedEvent(
        run_id=1,
        total_tasks=10,
        models=(
            ModelDescriptor(
                provider_id="ollama",
                provider_type="openai_compatible",
                model_name="llama3",
                display_label="llama3",
            ),
        ),
        run_mode=RunMode.FULL_GRADING,
    )


def test_live_timer_starts_on_benchmark_started(widget: ProgressPanelWidget) -> None:
    # Act
    widget._on_benchmark_started(_make_started_event())

    # Assert
    assert widget._live_timer.isActive()


def test_live_timer_stops_on_benchmark_finished(widget: ProgressPanelWidget) -> None:
    # Arrange
    widget._on_benchmark_started(_make_started_event())

    # Act
    widget._on_benchmark_finished(
        BenchmarkFinishedEvent(run_id=1, total_time_ms=1000.0, completed_count=5, failed_count=0)
    )

    # Assert
    assert not widget._live_timer.isActive()


def test_live_timer_stops_on_benchmark_stopped(widget: ProgressPanelWidget) -> None:
    # Arrange
    widget._on_benchmark_started(_make_started_event())

    # Act
    widget._on_benchmark_stopped(BenchmarkStoppedEvent(run_id=1, stop_reason=StopReason.USER))

    # Assert
    assert not widget._live_timer.isActive()


def test_live_timer_stops_on_benchmark_paused(widget: ProgressPanelWidget) -> None:
    # Arrange
    widget._on_benchmark_started(_make_started_event())

    # Act
    widget._on_benchmark_paused(
        BenchmarkPausedEvent(run_id=1, pause_reason=PauseReason.USER, paused_at_stage=PipelineStage.BENCHMARKING)
    )

    # Assert
    assert not widget._live_timer.isActive()


def test_live_timer_resumes_on_benchmark_resumed(widget: ProgressPanelWidget) -> None:
    # Arrange — start then pause
    widget._on_benchmark_started(_make_started_event())
    widget._on_benchmark_paused(
        BenchmarkPausedEvent(run_id=1, pause_reason=PauseReason.USER, paused_at_stage=PipelineStage.BENCHMARKING)
    )

    # Act
    widget._on_benchmark_resumed(BenchmarkResumedEvent(run_id=1))

    # Assert
    assert widget._live_timer.isActive()


def test_bench_start_ms_stored_on_benchmark_started(widget: ProgressPanelWidget) -> None:
    # Act
    widget._on_benchmark_started(_make_started_event())

    # Assert — _bench_start_ms must be a positive monotonic timestamp
    assert widget._bench_start_ms > 0
