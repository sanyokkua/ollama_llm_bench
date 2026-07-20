"""Colocated ``LogController`` tests for ``ui/progress/`` (STORY-060)."""

from typing import cast

from PySide6.QtCore import Qt
from PySide6.QtWidgets import QLabel, QPushButton, QTextEdit
import pytest
from pytestqt.qtbot import QtBot
import structlog

from ollama_llm_bench.backend.domain import (
    BenchmarkRun,
    ErrorKind,
    ResultStatus,
    RunLogEventKind,
    RunLogVerbosity,
    RunMode,
    RunStatus,
    Verdict,
)
from ollama_llm_bench.backend.events import (
    SIGNAL_INFERENCE_COMPLETED,
    SIGNAL_INFERENCE_STARTED,
    SIGNAL_JUDGE_COMPLETED,
    SIGNAL_JUDGE_STARTED,
    SIGNAL_LOG_CLEARED,
    SIGNAL_MODEL_STABILITY_CHANGED,
    SIGNAL_MODEL_SWITCHED,
    SIGNAL_PROVIDER_REGISTRY_RELOADED,
    SIGNAL_PROVIDER_SWITCHED,
    SIGNAL_RUN_FAILED,
    SIGNAL_RUN_FINISHED,
    SIGNAL_RUN_ID_CHANGED,
    SIGNAL_RUN_STOPPED,
    SIGNAL_STAGE_CHANGED,
    SIGNAL_TASK_COMPLETED,
    SIGNAL_TASK_RETRY,
    InferenceCompletedEvent,
    InferenceStartedEvent,
    JudgeCompletedEvent,
    JudgeStartedEvent,
    LogClearedEvent,
    ModelStabilityChangedEvent,
    ModelSwitchedEvent,
    ProviderRegistryReloadedEvent,
    ProviderSwitchedEvent,
    RunFailedEvent,
    RunFinishedEvent,
    RunIdChangedEvent,
    RunStoppedEvent,
    StageChangedEvent,
    TaskCompletedEvent,
    TaskRetryEvent,
)
from ollama_llm_bench.backend.log_formatting.testing import FakeLogFormatter
from ollama_llm_bench.ui.progress._internal.controller import ProgressController
from ollama_llm_bench.ui.progress._internal.log_controller import LogController
from ollama_llm_bench.ui.progress._internal.select import (
    DEFAULT_RUN_LOG_MAX_LINES,
    RUN_LOG_MAX_LINES_MAX,
    RUN_LOG_MAX_LINES_MIN,
    escape_past_run_line,
    filter_search,
    parse_bool_setting,
    parse_max_lines,
    parse_run_log_verbosity,
)
from ollama_llm_bench.ui.progress._internal.view import ProgressView
from ollama_llm_bench.ui.progress.models import LogLineViewModel, LogViewModel
from ollama_llm_bench.ui.progress.testing import FakeProgressGateway
from ollama_llm_bench.ui.progress.tests.conftest import FakeEventBus

_RUN_ID = 1
_RESULT_ID = 1
_TASK_ID = "task-1"
_PROVIDER_ID = "prov-1"
_MODEL_NAME = "model-1"

_JUDGE_TIMEOUT_ERROR_TEXT = "Judge call exhausted adaptive budget for this task."

# The thirteen of the fifteen log-source signals that each append exactly one
# line, in the order this test fires them (see test docstring for why
# `_inference_completed`/`_log_cleared` are excluded).
_EXPECTED_KIND_ORDER: list[RunLogEventKind] = [
    RunLogEventKind.TASK_START,
    RunLogEventKind.DONE,
    RunLogEventKind.JUDGE,
    RunLogEventKind.JUDGE,
    RunLogEventKind.RETRY,
    RunLogEventKind.STAGE,
    RunLogEventKind.PROVIDER_SWITCH,
    RunLogEventKind.MODEL_SWITCH,
    RunLogEventKind.STOPPED,
    RunLogEventKind.FINISHED,
    RunLogEventKind.FAILED,
    RunLogEventKind.SYSTEM,
    RunLogEventKind.SYSTEM,
]


def _inference_started(
    *, result_id: int = _RESULT_ID, task_id: str = _TASK_ID
) -> InferenceStartedEvent:
    return InferenceStartedEvent(
        run_id=_RUN_ID,
        result_id=result_id,
        task_id=task_id,
        provider_id=_PROVIDER_ID,
        model_name=_MODEL_NAME,
        stage="inference",
        user_prompt="What is the capital of France?",
    )


def _inference_completed(*, result_id: int = _RESULT_ID) -> InferenceCompletedEvent:
    return InferenceCompletedEvent(
        run_id=_RUN_ID,
        result_id=result_id,
        task_id=_TASK_ID,
        provider_id=_PROVIDER_ID,
        model_name=_MODEL_NAME,
        total_time_ms=1000,
        ttft_ms=200,
        prompt_tokens=10,
        completion_tokens=20,
        tokens_per_second=5.0,
    )


def _task_completed(
    *,
    result_id: int = _RESULT_ID,
    task_id: str = _TASK_ID,
    result_status: ResultStatus = ResultStatus.COMPLETED,
) -> TaskCompletedEvent:
    return TaskCompletedEvent(
        run_id=_RUN_ID,
        result_id=result_id,
        task_id=task_id,
        provider_id=_PROVIDER_ID,
        model_name=_MODEL_NAME,
        result_status=result_status,
    )


def _judge_started() -> JudgeStartedEvent:
    return JudgeStartedEvent(
        run_id=_RUN_ID,
        result_id=_RESULT_ID,
        task_id=_TASK_ID,
        judge_provider_id=_PROVIDER_ID,
        judge_model_name="judge-model",
    )


def _judge_completed() -> JudgeCompletedEvent:
    return JudgeCompletedEvent(
        run_id=_RUN_ID,
        result_id=_RESULT_ID,
        task_id=_TASK_ID,
        judge_verdict=Verdict.PASS,
        judge_reasoning="Correct answer.",
        judge_time_ms=500,
    )


def _task_retry() -> TaskRetryEvent:
    return TaskRetryEvent(
        run_id=_RUN_ID,
        result_id=_RESULT_ID,
        task_id=_TASK_ID,
        provider_id=_PROVIDER_ID,
        model_name=_MODEL_NAME,
        attempt=2,
        total_attempts=3,
        reason="Connection refused",
        error_kind=ErrorKind.PROVIDER,
    )


def _stage_changed() -> StageChangedEvent:
    return StageChangedEvent(run_id=_RUN_ID, stage="inference", stage_index=2, stage_count=5)


def _provider_switched() -> ProviderSwitchedEvent:
    return ProviderSwitchedEvent(run_id=_RUN_ID, to_provider_id="prov-2")


def _model_switched() -> ModelSwitchedEvent:
    return ModelSwitchedEvent(run_id=_RUN_ID, provider_id=_PROVIDER_ID, to_model_name="model-2")


def _run_stopped() -> RunStoppedEvent:
    return RunStoppedEvent(
        run_id=_RUN_ID, stopped_at="2026-01-01T00:00:00Z", completed_tasks=1, total_tasks=10
    )


def _run_finished() -> RunFinishedEvent:
    return RunFinishedEvent(
        run_id=_RUN_ID,
        finished_at="2026-01-01T00:00:00Z",
        run_status=RunStatus.COMPLETED,
        total_tasks=10,
        completed_tasks=10,
        counts_by_result_status={},
        total_elapsed_ms=5000,
    )


def _run_failed() -> RunFailedEvent:
    return RunFailedEvent(
        run_id=_RUN_ID,
        failed_at="2026-01-01T00:00:00Z",
        error_kind=ErrorKind.OTHER,
        error_message="boom",
        completed_tasks=1,
        total_tasks=10,
    )


def _model_stability_changed() -> ModelStabilityChangedEvent:
    return ModelStabilityChangedEvent(
        run_id=_RUN_ID,
        provider_id=_PROVIDER_ID,
        model_name=_MODEL_NAME,
        model_state="ok",
        model_consecutive_successes=3,
        model_promotion_threshold=5,
        provider_state="closed",
        provider_consecutive_failures=0,
        provider_cooldown_remaining_ms=0,
    )


def _provider_registry_reloaded() -> ProviderRegistryReloadedEvent:
    return ProviderRegistryReloadedEvent(
        provider_count=3, enabled_provider_ids=("prov-1", "prov-2"), reload_cause="settings_saved"
    )


def _log_cleared() -> LogClearedEvent:
    return LogClearedEvent(run_id=_RUN_ID)


def _make_run(*, run_id: int) -> BenchmarkRun:
    return BenchmarkRun(
        run_id=run_id,
        run_name="Run 1",
        timestamp="2026-01-01T00:00:00Z",
        run_mode=RunMode.TASKS,
        status=RunStatus.COMPLETED,
        total_tasks=10,
        completed_tasks=10,
        total_elapsed_ms=1000,
        schema_version=1,
        created_at="2026-01-01T00:00:00Z",
    )


def _bind(
    *,
    gateway: FakeProgressGateway,
    event_bus: FakeEventBus,
    log_formatter: FakeLogFormatter,
    qtbot: QtBot,
) -> tuple[LogController, ProgressView]:
    view = ProgressView()
    qtbot.addWidget(view)
    controller = LogController(gateway=gateway, event_bus=event_bus, log_formatter=log_formatter)
    controller.bind(view)
    return controller, view


def test_one_line_per_event_via_formatter(
    qtbot: QtBot, fake_gateway: FakeProgressGateway, fake_event_bus: FakeEventBus
) -> None:
    """Proves: STORY-060-AC-1

    Firing each of the fifteen log-source signals once drives exactly one
    `LogFormatter.format_event` call, in pipeline order, for every signal that
    produces its own line. `_inference_completed` contributes no line of its
    own -- its timing/token metrics merge into the *following*
    `_task_completed` line per `select_task_completed`'s design -- and
    `_log_cleared` clears rather than appends; so thirteen of the fifteen
    signals each produce one line (verified against `_EXPECTED_KIND_ORDER`).
    Also covers EC-PROV-4a: firing a second `_task_completed` with
    `result_status=FAILED_JUDGE_TIMEOUT` produces a
    `RunLogEvent(kind=RunLogEventKind.TASK_JUDGE_TIMEOUT, ...)` line.
    """
    # Arrange
    log_formatter = FakeLogFormatter()
    with structlog.testing.capture_logs() as logs:
        _controller, view = _bind(
            gateway=fake_gateway, event_bus=fake_event_bus, log_formatter=log_formatter, qtbot=qtbot
        )
        captured: list[LogViewModel] = []
        view.apply_log = captured.append  # type: ignore[method-assign, assignment]

        # Act -- fire all fifteen log-source signals once, in pipeline order (the
        # thirteen appending signals coalesce into one debounced view repaint)
        fake_event_bus.emit(SIGNAL_INFERENCE_STARTED, _inference_started())
        fake_event_bus.emit(SIGNAL_INFERENCE_COMPLETED, _inference_completed())
        fake_event_bus.emit(SIGNAL_TASK_COMPLETED, _task_completed())
        fake_event_bus.emit(SIGNAL_JUDGE_STARTED, _judge_started())
        fake_event_bus.emit(SIGNAL_JUDGE_COMPLETED, _judge_completed())
        fake_event_bus.emit(SIGNAL_TASK_RETRY, _task_retry())
        fake_event_bus.emit(SIGNAL_STAGE_CHANGED, _stage_changed())
        fake_event_bus.emit(SIGNAL_PROVIDER_SWITCHED, _provider_switched())
        fake_event_bus.emit(SIGNAL_MODEL_SWITCHED, _model_switched())
        fake_event_bus.emit(SIGNAL_RUN_STOPPED, _run_stopped())
        fake_event_bus.emit(SIGNAL_RUN_FINISHED, _run_finished())
        fake_event_bus.emit(SIGNAL_RUN_FAILED, _run_failed())
        fake_event_bus.emit(SIGNAL_MODEL_STABILITY_CHANGED, _model_stability_changed())
        fake_event_bus.emit(SIGNAL_PROVIDER_REGISTRY_RELOADED, _provider_registry_reloaded())
        qtbot.wait(100)

        # Act -- the view-source `_log_cleared` clear+push is never coalesced
        fake_event_bus.emit(SIGNAL_LOG_CLEARED, _log_cleared())

        # Act -- EC-PROV-4a: a judge-timeout task-completion for a second task
        fake_event_bus.emit(
            SIGNAL_TASK_COMPLETED,
            _task_completed(
                result_id=2, task_id="task-2", result_status=ResultStatus.FAILED_JUDGE_TIMEOUT
            ),
        )
        qtbot.wait(100)

    # Assert -- thirteen ordinary lines plus the judge-timeout line = 14 calls, in order
    assert [event.kind for event, _verbosity in log_formatter.calls] == [
        *_EXPECTED_KIND_ORDER,
        RunLogEventKind.TASK_JUDGE_TIMEOUT,
    ]
    assert all(verbosity == RunLogVerbosity.NORMAL for _event, verbosity in log_formatter.calls)

    # Assert -- the coalesced burst of thirteen appends produced one repaint
    # (all thirteen lines), `_log_cleared` pushed immediately with zero lines,
    # and the judge-timeout append (its own coalesced burst of one) produced a
    # final repaint with a single fresh line
    assert [len(vm.lines) for vm in captured] == [13, 0, 1]
    assert captured[-1].lines[0].kind == RunLogEventKind.TASK_JUDGE_TIMEOUT.value
    assert captured[-1].lines[0].html == log_formatter.next_fragment
    assert log_formatter.calls[-1][0].error_text == _JUDGE_TIMEOUT_ERROR_TEXT
    assert not any(entry["log_level"] in {"error", "critical"} for entry in logs)


def test_verbosity_change_rerenders_from_cache(
    qtbot: QtBot, fake_gateway: FakeProgressGateway, fake_event_bus: FakeEventBus
) -> None:
    """Proves: STORY-060-AC-2

    Covers EC-LOG-3. Given three cached raw events, changing the verbosity
    dropdown re-renders every cached event exactly once at the new verbosity
    -- no event lost -- and persists the new value to `ui.run_log_verbosity`.
    """
    # Arrange
    log_formatter = FakeLogFormatter()
    _controller, view = _bind(
        gateway=fake_gateway, event_bus=fake_event_bus, log_formatter=log_formatter, qtbot=qtbot
    )
    fake_event_bus.emit(SIGNAL_INFERENCE_STARTED, _inference_started())
    fake_event_bus.emit(SIGNAL_STAGE_CHANGED, _stage_changed())
    fake_event_bus.emit(SIGNAL_RUN_STOPPED, _run_stopped())
    qtbot.wait(100)  # flush the coalesced append burst before observing verbosity's push
    calls_before = len(log_formatter.calls)
    captured: list[LogViewModel] = []
    view.apply_log = captured.append  # type: ignore[method-assign, assignment]

    # Act
    view.log_verbosity_changed.emit("Verbose")

    # Assert -- one re-render call per cached event, all three lines survive
    assert len(log_formatter.calls) == calls_before + 3
    assert all(
        verbosity == RunLogVerbosity.VERBOSE for _event, verbosity in log_formatter.calls[-3:]
    )
    assert len(captured[-1].lines) == 3  # noqa: PLR2004  # the three cached events, not a magic threshold
    assert captured[-1].verbosity == RunLogVerbosity.VERBOSE
    assert fake_gateway.get_setting("ui.run_log_verbosity") == "verbose"


def test_buffer_cap_evicts_oldest(
    qtbot: QtBot, fake_gateway: FakeProgressGateway, fake_event_bus: FakeEventBus
) -> None:
    """Proves: STORY-060-AC-3

    Covers EC-PERF-3. With `ui.run_log_max_lines` at its hard floor
    (`RUN_LOG_MAX_LINES_MIN`, read once at construction), one event beyond
    the cap evicts the oldest line from the visible buffer; a subsequent
    verbosity change re-renders only the events that survived the eviction,
    proving the oldest event is gone from the raw-event cache too, not
    merely hidden from view.
    """
    # Arrange
    fake_gateway.set_setting("ui.run_log_max_lines", str(RUN_LOG_MAX_LINES_MIN))
    log_formatter = FakeLogFormatter()
    _controller, view = _bind(
        gateway=fake_gateway, event_bus=fake_event_bus, log_formatter=log_formatter, qtbot=qtbot
    )
    captured: list[LogViewModel] = []
    view.apply_log = captured.append  # type: ignore[method-assign, assignment]

    # Act -- one event beyond the cap
    for index in range(RUN_LOG_MAX_LINES_MIN + 1):
        fake_event_bus.emit(SIGNAL_INFERENCE_STARTED, _inference_started(task_id=f"task-{index}"))
    qtbot.wait(100)

    # Assert -- capped at RUN_LOG_MAX_LINES_MIN visible lines
    assert len(captured[-1].lines) == RUN_LOG_MAX_LINES_MIN

    # Act -- a verbosity change re-renders only from the still-capped cache
    view.log_verbosity_changed.emit("Verbose")

    # Assert -- the oldest event (task-0) did not survive the eviction, and the
    # newest event (task-<cap>) did
    rerendered_task_ids = [
        event.task_id for event, _verbosity in log_formatter.calls[-RUN_LOG_MAX_LINES_MIN:]
    ]
    assert "task-0" not in rerendered_task_ids
    assert rerendered_task_ids[-1] == f"task-{RUN_LOG_MAX_LINES_MIN}"


def test_clear_empties_view_not_cache(
    qtbot: QtBot, fake_gateway: FakeProgressGateway, fake_event_bus: FakeEventBus
) -> None:
    """Proves: STORY-060-AC-4

    Clicking Clear empties the visible log body, but the cached raw events
    are retained; a subsequent verbosity change re-renders the full buffer.
    """
    # Arrange
    log_formatter = FakeLogFormatter()
    _controller, view = _bind(
        gateway=fake_gateway, event_bus=fake_event_bus, log_formatter=log_formatter, qtbot=qtbot
    )
    view.show()
    fake_event_bus.emit(SIGNAL_INFERENCE_STARTED, _inference_started())
    fake_event_bus.emit(SIGNAL_STAGE_CHANGED, _stage_changed())
    qtbot.wait(100)
    log_body = cast("QTextEdit", view.findChild(QTextEdit, "progress.log.body"))
    assert log_body.toPlainText() != ""
    clear_button = cast("QPushButton", view.findChild(QPushButton, "progress.log.clear"))

    # Act
    qtbot.mouseClick(  # type: ignore[no-untyped-call]  # pytest-qt provides no type stubs
        clear_button, Qt.MouseButton.LeftButton
    )

    # Assert -- view cleared
    assert log_body.toPlainText() == ""

    # Act -- a verbosity change re-renders the full retained buffer
    view.log_verbosity_changed.emit("Verbose")

    # Assert -- both original lines reappear
    assert log_body.toPlainText().count("EVENT") == 2  # noqa: PLR2004  # the two retained lines


def test_file_write_warning_indicator(
    qtbot: QtBot, fake_gateway: FakeProgressGateway, fake_event_bus: FakeEventBus
) -> None:
    """Proves: STORY-060-AC-5

    Covers EC-LOG-1. When the run-log file writer reports a write failure,
    the write-failure warning indicator is shown and the panel keeps
    appending lines from the in-memory buffer. `run_log_write_failed()` is
    polled fresh on every push, so the write failure is introduced *after*
    binding (still healthy at bind time) to prove the indicator reacts to a
    failure discovered mid-run, not only one present at construction.
    """
    # Arrange
    log_formatter = FakeLogFormatter()
    _controller, view = _bind(
        gateway=fake_gateway, event_bus=fake_event_bus, log_formatter=log_formatter, qtbot=qtbot
    )
    view.show()
    warning_label = cast("QLabel", view.findChild(QLabel, "progress.log.write_warning"))
    log_body = cast("QTextEdit", view.findChild(QTextEdit, "progress.log.body"))
    assert not warning_label.isVisible()

    # Act
    fake_gateway.set_run_log_write_failed(failed=True)
    fake_event_bus.emit(SIGNAL_INFERENCE_STARTED, _inference_started())
    qtbot.wait(100)

    # Assert
    assert warning_label.isVisible()
    assert log_body.toPlainText() != ""


def test_past_run_replay_loads_saved_log(
    qtbot: QtBot, fake_gateway: FakeProgressGateway, fake_event_bus: FakeEventBus
) -> None:
    """Proves: STORY-060-AC-6

    Given no run is active, a `_run_id_changed` selecting a past run makes the
    parent `ProgressController` delegate to `LogController.load_past_run`,
    which loads and replays that run's saved log via
    `ProgressGateway.load_past_log(run_id)` -- driven through the parent
    controller (not `LogController` directly) to prove the delegation wiring.
    """
    # Arrange
    run_id = 7
    fake_gateway.set_run_header(_make_run(run_id=run_id))
    fake_gateway.set_past_log(run_id, "line one\nline two")
    log_formatter = FakeLogFormatter()
    view = ProgressView()
    qtbot.addWidget(view)
    controller = ProgressController(
        gateway=fake_gateway, event_bus=fake_event_bus, log_formatter=log_formatter
    )
    controller.bind(view)
    captured: list[LogViewModel] = []
    view.apply_log = captured.append  # type: ignore[method-assign, assignment]

    # Act
    fake_event_bus.emit(SIGNAL_RUN_ID_CHANGED, RunIdChangedEvent(run_id=run_id))

    # Assert
    assert [line.html for line in captured[-1].lines] == [
        escape_past_run_line("line one"),
        escape_past_run_line("line two"),
    ]


def test_verbosity_change_while_viewing_past_run_preserves_replayed_lines(
    qtbot: QtBot, fake_gateway: FakeProgressGateway, fake_event_bus: FakeEventBus
) -> None:
    """Proves: STORY-060-AC-6

    Given a past run's log is loaded and replayed, changing the verbosity
    dropdown must not erase the replayed lines. A past run carries no
    structured `RunLogEvent`s to re-render at the new verbosity, so the
    still-populated replay cache is re-pushed unchanged rather than rebuilt
    from the (empty) live-run raw-event cache.
    """
    # Arrange
    run_id = 9
    fake_gateway.set_past_log(run_id, "line one\nline two")
    log_formatter = FakeLogFormatter()
    controller, view = _bind(
        gateway=fake_gateway, event_bus=fake_event_bus, log_formatter=log_formatter, qtbot=qtbot
    )
    controller.load_past_run(run_id)
    captured: list[LogViewModel] = []
    view.apply_log = captured.append  # type: ignore[method-assign, assignment]

    # Act
    view.log_verbosity_changed.emit("Verbose")

    # Assert -- the two replayed lines survive the verbosity change unchanged
    assert [line.html for line in captured[-1].lines] == [
        escape_past_run_line("line one"),
        escape_past_run_line("line two"),
    ]


def test_log_updates_coalesce_under_rapid_event_bursts(
    qtbot: QtBot, fake_gateway: FakeProgressGateway, fake_event_bus: FakeEventBus
) -> None:
    """Proves: STORY-060-AC-1

    Covers EC-PERF-3. A burst of log-source events fired in a tight loop with
    no real inter-event delay coalesces into fewer `apply_log` view repaints
    than events fired -- per-event pushes are debounced, not one full
    re-render per single event.
    """
    # Arrange
    log_formatter = FakeLogFormatter()
    _controller, view = _bind(
        gateway=fake_gateway, event_bus=fake_event_bus, log_formatter=log_formatter, qtbot=qtbot
    )
    captured: list[LogViewModel] = []
    view.apply_log = captured.append  # type: ignore[method-assign, assignment]
    event_count = 20

    # Act -- a tight loop, no real inter-event delay
    for index in range(event_count):
        fake_event_bus.emit(SIGNAL_INFERENCE_STARTED, _inference_started(task_id=f"task-{index}"))
    qtbot.wait(100)

    # Assert -- far fewer repaints than events fired, reflecting the full burst
    assert len(captured) < event_count
    assert len(captured[-1].lines) == event_count


# -- Pure-function tests for select.py's new Run Event Log helpers ----------------


@pytest.mark.parametrize(
    ("raw", "expected"),
    [
        ("short", RunLogVerbosity.SHORT),
        ("NORMAL", RunLogVerbosity.NORMAL),
        (" verbose ", RunLogVerbosity.VERBOSE),
        ("bogus", RunLogVerbosity.NORMAL),
    ],
    ids=["short", "normal-uppercase", "verbose-whitespace", "unrecognized-falls-back"],
)
def test_parse_run_log_verbosity_table(raw: str, expected: RunLogVerbosity) -> None:
    assert parse_run_log_verbosity(raw) == expected


@pytest.mark.parametrize(
    ("raw", "expected"),
    [
        ("50000", 50000),
        (None, DEFAULT_RUN_LOG_MAX_LINES),
        ("not-a-number", DEFAULT_RUN_LOG_MAX_LINES),
        ("0", RUN_LOG_MAX_LINES_MIN),
        ("500", RUN_LOG_MAX_LINES_MIN),
        ("-1", RUN_LOG_MAX_LINES_MIN),
        ("1000000", RUN_LOG_MAX_LINES_MAX),
    ],
    ids=[
        "valid-int-in-range",
        "missing-falls-back",
        "malformed-falls-back",
        "zero-clamped-to-min",
        "below-min-clamped-to-min",
        "negative-clamped-to-min",
        "above-max-clamped-to-max",
    ],
)
def test_parse_max_lines_table(raw: str | None, expected: int) -> None:
    assert parse_max_lines(raw) == expected


@pytest.mark.parametrize(
    ("raw", "default", "expected"),
    [
        ("true", False, True),
        ("false", True, False),
        (None, True, True),
        ("bogus", False, False),
    ],
    ids=["true-string", "false-string", "missing-uses-default", "unrecognized-uses-default"],
)
def test_parse_bool_setting_table(
    raw: str | None,
    default: bool,  # noqa: FBT001  # pytest.mark.parametrize table column
    expected: bool,  # noqa: FBT001  # pytest.mark.parametrize table column
) -> None:
    assert parse_bool_setting(raw, default=default) is expected


def test_escape_past_run_line_escapes_html_special_characters() -> None:
    assert escape_past_run_line("<script>alert(1)</script>") == (
        "&lt;script&gt;alert(1)&lt;/script&gt;"
    )


def test_filter_search_is_case_insensitive_substring_match() -> None:
    lines = (
        LogLineViewModel(kind="task_start", html="<b>Hello World</b>"),
        LogLineViewModel(kind="done", html="<b>Goodbye</b>"),
    )
    assert filter_search(lines, "hello") == (lines[0],)


def test_filter_search_strips_html_tags_before_matching() -> None:
    lines = (LogLineViewModel(kind="task_start", html='<span class="tone-info">EVENT</span>'),)
    assert filter_search(lines, "tone-info") == ()


def test_filter_search_empty_term_returns_all_lines() -> None:
    lines = (LogLineViewModel(kind="task_start", html="<b>x</b>"),)
    assert filter_search(lines, "   ") == lines
