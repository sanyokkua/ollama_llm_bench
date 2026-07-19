"""Pure ``(event payload) -> view-model`` functions for ``ui/progress/`` (STORY-058).

No Qt involvement anywhere in this module -- every function here is directly
unit-testable with no ``QApplication``, per ``implementation_structure.md`` §9's test
boundary.
"""

import msgspec

from ollama_llm_bench.backend.domain import ResultStatus, RunStatus
from ollama_llm_bench.backend.events import (
    JudgeModelExcludedEvent,
    ModelStabilityChangedEvent,
    ProgressUpdatedEvent,
)
from ollama_llm_bench.ui.progress.models import (
    CountersViewModel,
    HeaderAffordances,
    RunStage,
    StabilityViewModel,
)

__all__: list[str] = [
    "apply_judge_excluded",
    "estimate_eta_label",
    "format_duration_ms",
    "parse_stage",
    "select_counters",
    "select_header",
    "select_stability",
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
