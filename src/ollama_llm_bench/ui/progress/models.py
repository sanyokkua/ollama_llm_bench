"""Frozen ViewModel structs (+ the locally-declared ``RunStage`` enum) for
``ui/progress/`` (STORY-058).

Source of truth: ``docs/v3_specification/04_Progress_Widget/implementation_structure.md``
§5. ``RunStage`` is declared **locally** rather than imported from
``backend.domain`` -- a grounding gap this story resolves: no backend module owns
this closed set yet (``StageChangedEvent.stage`` is a plain ``str`` in
``backend/events/models.py``), so this mirrors the existing
``ui/shared/models.py`` precedent of a UI-only enum (``BadgeStatus``) staying
UI-only until a backend module needs the same closed set.

``ProgressViewModel`` is narrowed relative to ``implementation_structure.md``'s
full struct: it carries only the fields this story's controllers populate
(``counters``, ``stability``, plus the header fields). STORY-059 added the
``current_task`` field and STORY-060 adds the ``log`` field here -- ordinary
incremental growth of a struct this module alone owns and controls every
construction site of.
"""

from enum import StrEnum

import msgspec

from ollama_llm_bench.backend.domain import InferenceContext, ResultStatus, RunLogVerbosity

__all__: list[str] = [
    "CountersViewModel",
    "CurrentTaskViewModel",
    "HeaderAffordances",
    "LogLineViewModel",
    "LogViewModel",
    "ProgressViewModel",
    "RunStage",
    "StabilityViewModel",
]


class RunStage(StrEnum):
    """The ten pipeline-stage values named by ``description.md`` §3.1's stage-badge table.

    Five batched phases (``INITIALIZING``, ``INFERENCE``, ``KEYWORD_CHECK``,
    ``COSINE_CHECK``, ``JUDGE_CHECK``) plus the terminal/frozen states
    (``FINISHING``, ``COMPLETED``, ``FAILED``, ``STOPPED``, ``PAUSED``) from
    ``08_Cross_Cutting/08-B_benchmark_state_machine.md``.
    """

    INITIALIZING = "INITIALIZING"
    INFERENCE = "INFERENCE"
    KEYWORD_CHECK = "KEYWORD_CHECK"
    COSINE_CHECK = "COSINE_CHECK"
    JUDGE_CHECK = "JUDGE_CHECK"
    FINISHING = "FINISHING"
    COMPLETED = "COMPLETED"
    FAILED = "FAILED"
    STOPPED = "STOPPED"
    PAUSED = "PAUSED"


class CountersViewModel(msgspec.Struct, frozen=True, kw_only=True, gc=False):
    """The Run Progress counters, stage bar, per-stage badges, ETA, and model
    identification (description.md §4, §5, §6.1; implementation_structure.md §5)."""

    stage: RunStage
    tasks_done: int
    tasks_total: int
    eta_label: str
    total_time_label: str
    counts_by_status: dict[ResultStatus, int]
    bar_segments: tuple[tuple[str, int], ...]
    badge_counts: tuple[tuple[str, int], ...]
    judge_phase_active: bool
    provider_label: str
    model_label: str


class StabilityViewModel(msgspec.Struct, frozen=True, kw_only=True, gc=False):
    """The model- and provider-stability callouts (description.md §6.2, §6.3; AC-6).

    ``judge_excluded_text`` is an additive field beyond
    ``implementation_structure.md``'s example struct: the persistent red
    judge-model-exclusion callout (§6.2) is a *second*, independent callout
    alongside the test-model band -- this module owns the struct and controls
    every construction site, so the addition is ordinary incremental growth.
    """

    model_band: str
    model_text: str
    provider_band: str
    provider_text: str
    show_retry_probe: bool
    show_open_settings: bool
    judge_excluded_text: str | None = None


class CurrentTaskViewModel(msgspec.Struct, frozen=True, kw_only=True, gc=False):
    """The Current-task grid plus the Inference/Judge live progress sub-rows
    (description.md §7, §7.1; implementation_structure.md §5; STORY-059-AC-1..6)."""

    task_id: str | None
    stage_label: str
    task_time_label: str
    timeouts: int
    retry_active: bool
    retry_label: str | None
    inference_progress_visible: bool
    inference_progress_label: str | None
    judge_progress_visible: bool
    judge_progress_label: str | None
    last_progress_context: InferenceContext | None


class LogLineViewModel(msgspec.Struct, frozen=True, kw_only=True, gc=False):
    """One rendered Run Event Log line (description.md §8; STORY-060-AC-1).

    ``kind`` is the raw ``RunLogEventKind`` string value (not the enum itself --
    the view never branches on it, only ``html`` is rendered); ``html`` is the
    pre-built HTML fragment ``LogFormatter.format_event`` returned (or, for a
    past-run replay line, an HTML-escaped raw log-file line).
    """

    kind: str
    html: str


class LogViewModel(msgspec.Struct, frozen=True, kw_only=True, gc=False):
    """The Run Event Log panel's full render state (description.md §8;
    STORY-060-AC-1..6): the toolbar's verbosity/search state, the buffered and
    filtered lines, the auto-scroll preference, and the log-write-failure
    warning indicator."""

    verbosity: RunLogVerbosity
    lines: tuple[LogLineViewModel, ...]
    search_term: str
    auto_scroll: bool
    file_write_warning: bool


class HeaderAffordances(msgspec.Struct, frozen=True, kw_only=True, gc=False):
    """The header row's per-state control affordances (state_machine.md §4; AC-2).

    Grouped into one struct per ``coding-style.md``'s >4-parameter rule: passed
    as a single argument from ``select_header`` through
    ``ProgressView.apply_header`` to ``ProgressHeaderWidget.apply``.
    ``pause_resume_visible``/``stop_visible`` are additive fields resolving a
    STORY-058 defect: Pause/Stop are **hidden** (not merely disabled) in the
    ``Empty`` and ``ViewingPastRun`` states per ``08-L_ui_standardization.md``
    §1's no-placeholder-UI rule.
    """

    show_rename_pencil: bool
    pause_resume_label: str
    pause_resume_visible: bool
    pause_resume_enabled: bool
    stop_visible: bool
    stop_enabled: bool


class ProgressViewModel(msgspec.Struct, frozen=True, kw_only=True, gc=False):
    """The Progress widget's full render state (implementation_structure.md §5,
    narrowed per STORY-058's scope; STORY-059 added ``current_task``; STORY-060
    adds ``log``)."""

    widget_state: str
    run_name: str
    show_rename_pencil: bool
    pause_resume_label: str
    pause_resume_visible: bool
    pause_resume_enabled: bool
    stop_visible: bool
    stop_enabled: bool
    counters: CountersViewModel
    current_task: CurrentTaskViewModel
    stability: StabilityViewModel
    log: LogViewModel
