"""Pure ``(event payload) -> view-model`` functions for ``ui/progress/`` (STORY-058;
STORY-060 adds the Run Event Log's ``select_*``/``filter_search``/``parse_*`` helpers).

No Qt involvement anywhere in this module -- every function here is directly
unit-testable with no ``QApplication``, per ``implementation_structure.md`` §9's test
boundary.
"""

from datetime import UTC, datetime
import html
import re
from typing import Final

import msgspec

from ollama_llm_bench.backend.domain import (
    InferenceContext,
    ResultStatus,
    RunLogEvent,
    RunLogEventKind,
    RunLogVerbosity,
    RunStatus,
)
from ollama_llm_bench.backend.events import (
    InferenceCompletedEvent,
    InferenceStartedEvent,
    JudgeCompletedEvent,
    JudgeModelExcludedEvent,
    JudgeStartedEvent,
    ModelStabilityChangedEvent,
    ModelSwitchedEvent,
    ProgressUpdatedEvent,
    ProviderRegistryReloadedEvent,
    ProviderSwitchedEvent,
    RunFailedEvent,
    RunFinishedEvent,
    RunStoppedEvent,
    StageChangedEvent,
    TaskCompletedEvent,
    TaskRetryEvent,
)
from ollama_llm_bench.ui.progress.models import (
    CountersViewModel,
    HeaderAffordances,
    LogLineViewModel,
    RunStage,
    StabilityViewModel,
)

__all__: list[str] = [
    "DEFAULT_RUN_LOG_MAX_LINES",
    "INFERENCE_COMPLETE_PLACEHOLDER",
    "RUN_LOG_MAX_LINES_MAX",
    "RUN_LOG_MAX_LINES_MIN",
    "accepts_progress_context",
    "apply_judge_excluded",
    "escape_past_run_line",
    "estimate_eta_label",
    "filter_search",
    "format_duration_ms",
    "format_inference_generating_label",
    "format_inference_waiting_label",
    "format_judge_receiving_label",
    "format_judge_waiting_label",
    "format_retry_label",
    "parse_bool_setting",
    "parse_max_lines",
    "parse_run_log_verbosity",
    "parse_stage",
    "select_counters",
    "select_header",
    "select_judge_completed",
    "select_judge_model_excluded",
    "select_judge_started",
    "select_model_stability_system_note",
    "select_model_switched",
    "select_provider_registry_reloaded",
    "select_provider_switched",
    "select_run_failed",
    "select_run_finished",
    "select_run_stopped",
    "select_stability",
    "select_stage_changed",
    "select_task_completed",
    "select_task_retry",
    "select_task_start",
    "terminal_stage_for_run_status",
]

# The five terminal-failure ResultStatus members that sum into the "Failed" counter
# (description.md §4's "Failed" row; AC-4).
_FAILURE_STATUSES: tuple[ResultStatus, ...] = (
    ResultStatus.FAILED_INFERENCE,
    ResultStatus.FAILED_PROVIDER,
    ResultStatus.FAILED_TIMEOUT,
    ResultStatus.FAILED_JUDGE_TIMEOUT,
    ResultStatus.ERRORED,
)
# "bench" -- inference done, regardless of pending validation phase (description.md §5).
_BENCH_STATUSES: tuple[ResultStatus, ...] = (
    ResultStatus.AWAITING_KEYWORD_CHECK,
    ResultStatus.AWAITING_COSINE_CHECK,
    ResultStatus.AWAITING_JUDGE_CHECK,
    ResultStatus.COMPLETED,
)

# state_machine.md's top-level widget states in which the rename pencil / Pause / Stop
# affordances are available at all (§4, §5).
_RENAME_VISIBLE_STATES = frozenset({"Initializing", "Running", "Paused"})
_STOP_ENABLED_STATES = frozenset({"Initializing", "Running", "Paused"})
_PAUSE_ENABLED_STATES = frozenset({"Running"})
# state_machine.md §4: Pause/Stop are shown (possibly disabled) in every
# non-terminal, non-empty state -- "Stop only" (Initializing), "Pause and Stop"
# (Running), "Resume and Stop" (Paused), "disabled" (Stopping, still visible
# while draining) -- and **hidden** (not merely disabled) in Empty/ViewingPastRun
# per `08-L_ui_standardization.md` §1's no-placeholder-UI rule.
_CONTROLS_VISIBLE_STATES = frozenset({"Initializing", "Running", "Paused", "Stopping"})

# state_machine.md §10 SPEC-098 reconciliation / description.md §3.1: maps a
# persisted `RunStatus` to the matching terminal/paused stage badge. `INCOMPLETE`
# maps to `PAUSED` because description.md §3.6 defines it as "a paused run that
# is never resumed" -- the only persisted status a genuinely-paused-but-lost-event
# run can settle to.
_TERMINAL_STAGE_BY_RUN_STATUS: dict[RunStatus, RunStage] = {
    RunStatus.COMPLETED: RunStage.COMPLETED,
    RunStatus.FAILED: RunStage.FAILED,
    RunStatus.STOPPED: RunStage.STOPPED,
    RunStatus.INCOMPLETE: RunStage.PAUSED,
}

# description.md §6.2 model band <- ModelStabilityChangedEvent.model_state
# (backend.adaptive_timeout.AdaptiveTimeoutModelState's string values, read as an
# opaque str per D-R-06 -- this module never imports that backend service).
_MODEL_BAND_BY_STATE: dict[str, str] = {"ok": "ok", "warn": "warn", "excluded": "excluded"}
_MODEL_TEXT_BY_BAND: dict[str, str] = {
    "ok": "OK",
    "warn": "Approaching the maximum-timeout exclusion threshold",
    "excluded": "Model excluded — remaining tasks for this model are marked FAILED_TIMEOUT",
}
# description.md §6.3 provider band <- ModelStabilityChangedEvent.provider_state
# (backend.circuit_breaker.CircuitState's string values, read as an opaque str).
_PROVIDER_BAND_BY_STATE: dict[str, str] = {
    "closed": "closed",
    "tripped": "open",
    "probing": "warn",
}
_PROVIDER_TEXT_BY_BAND: dict[str, str] = {
    "closed": "Provider responsive",
    "warn": "Probing provider — next probe pending",
    "open": "Provider unresponsive — circuit breaker open",
}


def parse_stage(value: str) -> RunStage:
    """Parse a ``_stage_changed`` payload's ``stage`` string into ``RunStage``
    (STORY-058 gap resolution: ``StageChangedEvent.stage`` is an untyped ``str`` with
    no canonical casing fixed by the spec/backend yet, so this normalizes case).

    Falls back to ``RunStage.INITIALIZING`` for an unrecognized value -- there is no
    error channel available at this pure-function boundary.
    """
    try:
        return RunStage(value.strip().upper())
    except ValueError:
        return RunStage.INITIALIZING


def format_duration_ms(total_ms: int) -> str:
    """Format a millisecond duration as ``MmSSs``/``Ss`` (description.md §4 Total Time)."""
    total_seconds = max(total_ms, 0) // 1000
    minutes, seconds = divmod(total_seconds, 60)
    if minutes:
        return f"{minutes}m {seconds:02d}s"
    return f"{seconds}s"


def estimate_eta_label(*, elapsed_ms: int, completed: int, remaining: int) -> str:
    """Estimate remaining time from a rolling average of completed-task duration
    (description.md §4 ETA: ``elapsed / completed * remaining``); "—" with no data yet."""
    if remaining <= 0:
        return "0s"
    if completed <= 0:
        return "—"
    average_ms = elapsed_ms / completed
    return format_duration_ms(int(average_ms * remaining))


class _CountersInputs(msgspec.Struct, frozen=True, kw_only=True, gc=False):
    """Private, module-local grouping of ``select_counters``'s inputs beyond the raw
    payload -- keeps every helper signature within the 4-parameter style limit."""

    stage: RunStage
    judge_phase_active: bool
    eta_label: str
    total_time_label: str
    provider_label: str
    model_label: str


class _SegmentCounts(msgspec.Struct, frozen=True, kw_only=True, gc=False):
    """Private, module-local grouping of the per-segment counts ``_bar_segments``/
    ``_badge_counts`` both derive their output from."""

    bench: int
    judge_wait: int
    done: int
    failed: int
    pending: int
    total: int
    is_complete: bool
    judge_phase_active: bool
    judge_timeout_count: int


def select_counters(*, payload: ProgressUpdatedEvent, inputs: _CountersInputs) -> CountersViewModel:
    """Derive ``CountersViewModel`` from one ``_progress_updated`` payload (§4, §5; AC-4)."""
    raw_counts = payload.counts_by_result_status
    counts_by_status = {status: raw_counts.get(status, 0) for status in ResultStatus}
    failed_total = sum(counts_by_status[status] for status in _FAILURE_STATUSES)
    bench = sum(counts_by_status[status] for status in _BENCH_STATUSES)
    judge_wait = (
        counts_by_status[ResultStatus.AWAITING_JUDGE_CHECK] if inputs.judge_phase_active else 0
    )
    done = counts_by_status[ResultStatus.COMPLETED]
    pending = counts_by_status[ResultStatus.PENDING]
    is_complete = payload.total_count > 0 and done == payload.total_count
    segments = _SegmentCounts(
        bench=bench,
        judge_wait=judge_wait,
        done=done,
        failed=failed_total,
        pending=pending,
        total=payload.total_count,
        is_complete=is_complete,
        judge_phase_active=inputs.judge_phase_active,
        judge_timeout_count=counts_by_status[ResultStatus.FAILED_JUDGE_TIMEOUT],
    )
    return CountersViewModel(
        stage=inputs.stage,
        tasks_done=payload.completed_count,
        tasks_total=payload.total_count,
        eta_label=inputs.eta_label,
        total_time_label=inputs.total_time_label,
        counts_by_status=counts_by_status,
        bar_segments=_bar_segments(segments),
        badge_counts=_badge_counts(segments),
        judge_phase_active=inputs.judge_phase_active,
        provider_label=inputs.provider_label,
        model_label=inputs.model_label,
    )


def _bar_segments(counts: _SegmentCounts) -> tuple[tuple[str, int], ...]:
    """The segmented stage-bar weights (description.md §5); a single ``complete``
    segment at 100% completion, otherwise every non-zero segment in pipeline order."""
    if counts.is_complete:
        return (("complete", counts.total),)
    segments = (
        ("bench", counts.bench),
        ("judge_wait", counts.judge_wait),
        ("failed", counts.failed),
        ("pending", counts.pending),
    )
    return tuple((name, weight) for name, weight in segments if weight > 0)


def _badge_counts(counts: _SegmentCounts) -> tuple[tuple[str, int], ...]:
    """The per-stage badge row (description.md §5), plus the ``failed_judge_timeout``
    per-reason breakout badge when any result settled that status."""
    badges: list[tuple[str, int]] = [("bench", counts.bench)]
    if counts.judge_phase_active:
        badges.append(("judge-wait", counts.judge_wait))
    badges.append(("done", counts.done))
    badges.append(("failed", counts.failed))
    if counts.judge_timeout_count > 0:
        badges.append(("failed_judge_timeout", counts.judge_timeout_count))
    return tuple(badges)


def select_header(*, widget_state: str) -> HeaderAffordances:
    """Derive the header's per-state control affordances from the top-level widget
    state (state_machine.md §4, §5; AC-2).

    Pause/Stop are **hidden** (not merely disabled) in ``Empty`` and
    ``ViewingPastRun``; in every other non-terminal state they are shown,
    possibly disabled (``Initializing`` disables Pause -- a
    transiently-disabled control about to become actionable per
    `08-L_ui_standardization.md` §1 -- and ``Stopping`` disables both while
    draining).
    """
    is_paused = widget_state == "Paused"
    controls_visible = widget_state in _CONTROLS_VISIBLE_STATES
    return HeaderAffordances(
        show_rename_pencil=widget_state in _RENAME_VISIBLE_STATES,
        pause_resume_label="Resume" if is_paused else "Pause",
        pause_resume_visible=controls_visible,
        pause_resume_enabled=is_paused or widget_state in _PAUSE_ENABLED_STATES,
        stop_visible=controls_visible,
        stop_enabled=widget_state in _STOP_ENABLED_STATES,
    )


def terminal_stage_for_run_status(status: RunStatus) -> RunStage:
    """Map a persisted ``RunStatus`` to the matching terminal/paused stage badge
    (description.md §3.1; state_machine.md §10 SPEC-098 reconciliation).

    Used by ``ProgressController`` to force the badge to the correct
    terminal/paused ``RunStage`` on ``_run_finished`` (whose payload carries
    the persisted status directly) and on the bounded reconciliation timeout
    (which reads ``ProgressGateway.run_header(run_id).status``).
    """
    return _TERMINAL_STAGE_BY_RUN_STATUS[status]


def select_stability(event: ModelStabilityChangedEvent) -> StabilityViewModel:
    """Derive the model/provider stability bands from one ``_model_stability_changed``
    payload (description.md §6.2/§6.3; AC-6; EC-PROV-3, EC-PROV-4)."""
    model_band = _MODEL_BAND_BY_STATE.get(event.model_state, "ok")
    provider_band = _PROVIDER_BAND_BY_STATE.get(event.provider_state, "closed")
    return StabilityViewModel(
        model_band=model_band,
        model_text=_MODEL_TEXT_BY_BAND[model_band],
        provider_band=provider_band,
        provider_text=_PROVIDER_TEXT_BY_BAND[provider_band],
        show_retry_probe=provider_band == "open",
        show_open_settings=provider_band == "open",
        judge_excluded_text=None,
    )


def apply_judge_excluded(
    vm: StabilityViewModel, event: JudgeModelExcludedEvent
) -> StabilityViewModel:
    """Set the persistent red judge-exclusion callout (description.md §6.2; AC-6;
    EC-PROV-4b).

    Additive and sticky by construction: the caller (``StabilityController``) is
    responsible for re-applying the last-known ``judge_excluded_text`` onto every
    later ``select_stability`` result so a subsequent ``_model_stability_changed``
    never clears it.
    """
    text = (
        f"Judge model excluded — {event.consecutive_timeouts} consecutive "
        "max-budget timeouts · remaining tasks' judge phase will be skipped"
    )
    return StabilityViewModel(
        model_band=vm.model_band,
        model_text=vm.model_text,
        provider_band=vm.provider_band,
        provider_text=vm.provider_text,
        show_retry_probe=vm.show_retry_probe,
        show_open_settings=vm.show_open_settings,
        judge_excluded_text=text,
    )


# description.md §7.1.3's exact italic placeholder shown in the Inference progress
# sub-row while the judge phase is in flight for the same result (AC-4).
INFERENCE_COMPLETE_PLACEHOLDER = "(complete — main inference finished)"

# description.md §7.1: the Current-task controller accepts only these two
# contexts; RUN_ANALYSIS/PROVIDER_TEST are routed to other subscribers (AC-3).
_ACCEPTED_PROGRESS_CONTEXTS = frozenset(
    {InferenceContext.BENCHMARK_TASK, InferenceContext.BENCHMARK_JUDGE}
)


def accepts_progress_context(context: InferenceContext) -> bool:
    """Whether the Current-task controller accepts this ``_inference_progress``
    context (description.md §7.1; AC-3; EC-RUN-23's premise)."""
    return context in _ACCEPTED_PROGRESS_CONTEXTS


def _estimate_marker(*, is_estimate: bool) -> str:
    return "~" if is_estimate else ""


def format_inference_waiting_label(elapsed_ms: int) -> str:
    """Sub-state A label for the Inference progress sub-row (description.md §7.1.1; AC-1)."""
    return f"Waiting for first token — {elapsed_ms / 1000:.1f} s"


def format_inference_generating_label(*, tokens: int, elapsed_ms: int, is_estimate: bool) -> str:
    """Sub-state B label for the Inference progress sub-row (description.md §7.1.1;
    AC-2, AC-6; EC-RUN-17)."""
    marker = _estimate_marker(is_estimate=is_estimate)
    return f"Generating — {marker}{tokens} tokens · {elapsed_ms / 1000:.1f} s elapsed"


def format_judge_waiting_label(elapsed_ms: int) -> str:
    """Sub-state A label for the Judge progress sub-row (description.md §7.1.2)."""
    return f"Judge: waiting for response — {elapsed_ms / 1000:.1f} s"


def format_judge_receiving_label(*, tokens: int, elapsed_ms: int, is_estimate: bool) -> str:
    """Sub-state B label for the Judge progress sub-row (description.md §7.1.2; AC-6)."""
    marker = _estimate_marker(is_estimate=is_estimate)
    return f"Judge: receiving — {marker}{tokens} tokens · {elapsed_ms / 1000:.1f} s elapsed"


def format_retry_label(*, attempt: int, total_attempts: int, reason: str) -> str:
    """The Retry line's ``attempt/total - reason`` text (description.md §7; AC-5)."""
    return f"{attempt}/{total_attempts} - {reason}"


# ---------------------------------------------------------------------------------
# Run Event Log -- pure event -> RunLogEvent mapping and settings-parsing helpers
# (STORY-060; description.md §8; implementation_structure.md §4.3/§9).
# ---------------------------------------------------------------------------------

DEFAULT_RUN_LOG_MAX_LINES: Final[int] = 100_000
"""The registry default for ``ui.run_log_max_lines`` (description.md §8.4)."""

RUN_LOG_MAX_LINES_MIN: Final[int] = 1_000
"""The hard lower bound ``ui.run_log_max_lines`` is clamped to (description.md §8.4)."""

RUN_LOG_MAX_LINES_MAX: Final[int] = 500_000
"""The hard upper bound ``ui.run_log_max_lines`` is clamped to (description.md §8.4)."""

_JUDGE_TIMEOUT_ERROR_TEXT: Final[str] = "Judge call exhausted adaptive budget for this task."
"""EC-PROV-4a's canonical ``error_message`` text, reused verbatim as the Run Event Log
line's ``error_text`` for a ``task_judge_timeout`` line."""

_HTML_TAG_RE: Final[re.Pattern[str]] = re.compile(r"<[^>]+>")


def _log_timestamp() -> str:
    """The current UTC instant, stamped on every Run Event Log line built here.

    ``ui/*`` cannot import ``backend.infra.Clock`` (project-structure.md's import
    table), and ``ProgressGateway`` carries no clock method, so there is no
    injectable alternative at this layer -- the same
    ``datetime.now(UTC).isoformat()`` idiom ``ui/resume_benchmark/_internal/
    actions.py`` uses for the identical reason.
    """
    return datetime.now(UTC).isoformat()


def parse_run_log_verbosity(value: str) -> RunLogVerbosity:
    """Parse a verbosity combo-box/settings string; falls back to ``NORMAL`` for an
    unrecognized value (description.md §8.1) -- user input, never a contract."""
    try:
        return RunLogVerbosity(value.strip().lower())
    except ValueError:
        return RunLogVerbosity.NORMAL


def parse_max_lines(value: str | None) -> int:
    """Parse ``ui.run_log_max_lines``; falls back to ``DEFAULT_RUN_LOG_MAX_LINES`` on
    a missing or malformed setting, and clamps any parsed value to the hard range
    ``[RUN_LOG_MAX_LINES_MIN, RUN_LOG_MAX_LINES_MAX]`` (description.md §8.4) --
    never raises, and never returns a value a ``deque(maxlen=...)`` would reject."""
    if value is None:
        return DEFAULT_RUN_LOG_MAX_LINES
    try:
        parsed = int(value)
    except ValueError:
        return DEFAULT_RUN_LOG_MAX_LINES
    return max(RUN_LOG_MAX_LINES_MIN, min(RUN_LOG_MAX_LINES_MAX, parsed))


def parse_bool_setting(value: str | None, *, default: bool) -> bool:
    """Parse a ``"true"``/``"false"`` settings string; falls back to ``default`` for
    ``None`` or any other value."""
    if value is None:
        return default
    return value.strip().lower() == "true"


def escape_past_run_line(line: str) -> str:
    """HTML-escape one raw line from a past run's saved log file for safe display
    (AC-6) -- no structured ``RunLogEvent`` survives to re-run through
    ``LogFormatter``, so this bypasses the log-formatting service entirely."""
    return html.escape(line)


def filter_search(lines: tuple[LogLineViewModel, ...], term: str) -> tuple[LogLineViewModel, ...]:
    """Case-insensitive substring filter over each line's plain rendered text
    (description.md §8.1) -- HTML tags are stripped before matching so a search
    term never matches CSS-class markup incidentally."""
    needle = term.strip().lower()
    if not needle:
        return lines
    return tuple(line for line in lines if needle in _HTML_TAG_RE.sub("", line.html).lower())


def select_task_start(event: InferenceStartedEvent) -> RunLogEvent:
    """Map ``_inference_started`` into a ``task_start`` line (description.md §8.3)."""
    return RunLogEvent(
        kind=RunLogEventKind.TASK_START,
        timestamp=_log_timestamp(),
        provider_id=event.provider_id,
        model_name=event.model_name,
        task_id=event.task_id,
        stage=event.stage,
        prompt_excerpt=event.user_prompt,
    )


def select_judge_started(event: JudgeStartedEvent) -> RunLogEvent:
    """Map ``_judge_started`` into a ``judge`` line, no verdict fields yet
    (description.md §8.3; STORY-060 gap resolution -- ``RunLogEventKind`` has no
    dedicated ``judge_started`` member, so this reuses ``JUDGE``, distinguished
    from ``select_judge_completed`` only by which fields are populated)."""
    return RunLogEvent(
        kind=RunLogEventKind.JUDGE,
        timestamp=_log_timestamp(),
        provider_id=event.judge_provider_id,
        model_name=event.judge_model_name,
        task_id=event.task_id,
    )


def select_judge_completed(event: JudgeCompletedEvent) -> RunLogEvent:
    """Map ``_judge_completed`` into a ``judge`` line carrying the binary verdict
    and reasoning (description.md §8.3)."""
    return RunLogEvent(
        kind=RunLogEventKind.JUDGE,
        timestamp=_log_timestamp(),
        task_id=event.task_id,
        total_time_ms=event.judge_time_ms,
        completion_tokens=event.judge_completion_tokens,
        judge_verdict=event.judge_verdict,
        judge_reasoning=event.judge_reasoning,
    )


def select_task_completed(
    event: TaskCompletedEvent, *, completion: InferenceCompletedEvent | None
) -> RunLogEvent:
    """Map ``_task_completed`` into a ``done``/``task_judge_timeout`` line
    (description.md §8.3; EC-PROV-4a), merging the matching cached
    ``_inference_completed`` timing/token metrics when one exists."""
    is_judge_timeout = event.result_status == ResultStatus.FAILED_JUDGE_TIMEOUT
    kind = RunLogEventKind.TASK_JUDGE_TIMEOUT if is_judge_timeout else RunLogEventKind.DONE
    error_text = _JUDGE_TIMEOUT_ERROR_TEXT if is_judge_timeout else _task_error_text(event)
    return RunLogEvent(
        kind=kind,
        timestamp=_log_timestamp(),
        provider_id=event.provider_id,
        model_name=event.model_name,
        task_id=event.task_id,
        total_time_ms=(completion.total_time_ms if completion is not None else event.total_time_ms),
        ttft_ms=completion.ttft_ms if completion is not None else None,
        tokens_per_second=completion.tokens_per_second if completion is not None else None,
        prompt_tokens=completion.prompt_tokens if completion is not None else None,
        completion_tokens=completion.completion_tokens if completion is not None else None,
        error_text=error_text,
        judge_verdict=event.verdict,
    )


def _task_error_text(event: TaskCompletedEvent) -> str | None:
    return event.error_kind.value if event.error_kind is not None else None


def select_task_retry(event: TaskRetryEvent) -> RunLogEvent:
    """Map ``_task_retry`` into a ``retry`` line (description.md §8.3)."""
    return RunLogEvent(
        kind=RunLogEventKind.RETRY,
        timestamp=_log_timestamp(),
        provider_id=event.provider_id,
        model_name=event.model_name,
        task_id=event.task_id,
        retry_attempt=event.attempt,
        retry_reason=event.reason,
    )


def select_stage_changed(event: StageChangedEvent) -> RunLogEvent:
    """Map ``_stage_changed`` into a ``stage`` line (description.md §8.3)."""
    return RunLogEvent(kind=RunLogEventKind.STAGE, timestamp=_log_timestamp(), stage=event.stage)


def select_provider_switched(event: ProviderSwitchedEvent) -> RunLogEvent:
    """Map ``_provider_switched`` into a ``provider_switch`` line (description.md
    §8.3)."""
    return RunLogEvent(
        kind=RunLogEventKind.PROVIDER_SWITCH,
        timestamp=_log_timestamp(),
        provider_id=event.to_provider_id,
    )


def select_model_switched(event: ModelSwitchedEvent) -> RunLogEvent:
    """Map ``_model_switched`` into a ``model_switch`` line (description.md §8.3)."""
    return RunLogEvent(
        kind=RunLogEventKind.MODEL_SWITCH,
        timestamp=_log_timestamp(),
        provider_id=event.provider_id,
        model_name=event.to_model_name,
    )


def select_run_stopped(event: RunStoppedEvent) -> RunLogEvent:
    """Map ``_run_stopped`` into a ``stopped`` line (description.md §8.3)."""
    return RunLogEvent(
        kind=RunLogEventKind.STOPPED, timestamp=_log_timestamp(), error_text=event.reason
    )


def select_run_finished(event: RunFinishedEvent) -> RunLogEvent:
    """Map ``_run_finished`` into a ``finished`` line (description.md §8.3)."""
    return RunLogEvent(
        kind=RunLogEventKind.FINISHED,
        timestamp=_log_timestamp(),
        total_time_ms=event.total_elapsed_ms,
    )


def select_run_failed(event: RunFailedEvent) -> RunLogEvent:
    """Map ``_run_failed`` into a ``failed`` line (description.md §8.3); ``error_text``
    is already redacted by the emitter (``RunFailedEvent.error_message``'s own
    docstring)."""
    return RunLogEvent(
        kind=RunLogEventKind.FAILED, timestamp=_log_timestamp(), error_text=event.error_message
    )


def select_model_stability_system_note(event: ModelStabilityChangedEvent) -> RunLogEvent:
    """Map ``_model_stability_changed`` into a ``system`` note (description.md §8.3).

    No canonical text is spec-mandated for this particular system note (unlike the
    judge-exclusion line built by ``select_judge_model_excluded``, whose fixed §8.3
    sentence is rendered by the log-formatting service, and the pause/resume lines,
    which remain out of scope per this module's own log-source subscription list)
    -- the descriptive text is carried on the generic ``stage`` field, the only
    freeform display slot ``RunLogEvent`` offers beyond the error/retry/judge-specific
    fields.
    """
    return RunLogEvent(
        kind=RunLogEventKind.SYSTEM,
        timestamp=_log_timestamp(),
        provider_id=event.provider_id,
        model_name=event.model_name,
        stage=f"model={event.model_state}, provider={event.provider_state}",
    )


def select_provider_registry_reloaded(event: ProviderRegistryReloadedEvent) -> RunLogEvent:
    """Map ``_provider_registry_reloaded`` into a ``system`` note (description.md
    §8.3); the reload cause is carried on the generic ``stage`` field (see
    ``select_model_stability_system_note``'s docstring for why)."""
    return RunLogEvent(
        kind=RunLogEventKind.SYSTEM, timestamp=_log_timestamp(), stage=event.reload_cause
    )


def select_judge_model_excluded(
    event: JudgeModelExcludedEvent, *, provider_name: str
) -> RunLogEvent:
    """Map ``_judge_model_excluded`` into the one-time ``judge_excluded`` line
    (description.md §8.3, §12; EC-PROV-4b). ``provider_name`` is the judge
    provider's display name resolved by the controller (DD-33)."""
    return RunLogEvent(
        kind=RunLogEventKind.JUDGE_EXCLUDED,
        timestamp=_log_timestamp(),
        provider_id=event.provider_id,
        model_name=event.model_name,
        provider_name=provider_name,
        consecutive_timeouts=event.consecutive_timeouts,
    )
