"""Pure view-model derivation for the Run Analysis tab (STORY-065).

Source of truth: ``docs/v3_specification/05_Result_Widget/tabs/run_analysis_tab.md``
§5 (generation-metadata line), §7 (toolbar gating), §9 (empty/generating/ready/failed
states). No Qt involvement -- directly unit-testable, matching every sibling tab's
``select.py`` shape (``coding-style.md``).
"""

import msgspec

from ollama_llm_bench.backend.domain import (
    BenchmarkRun,
    InferenceActivity,
    InferenceActivityState,
    RunStatus,
)
from ollama_llm_bench.ui.results.models import JudgeAnalysisViewModel

__all__: list[str] = [
    "JudgeAnalysisSessionState",
    "format_metadata_line",
    "select_judge_analysis_view_model",
]

_NO_RUN_MESSAGE = "Select a run to view its analysis."
_NOT_GENERATED_RUNNING = "Run-level analysis is generated when the benchmark finishes."
_NOT_GENERATED_NOT_REQUESTED = (
    "Run-level analysis was not requested for this run. Click Generate analysis to produce it now."
)
_GENERATING_MESSAGE = "Generating run-level analysis..."
_GENERATING_METADATA = "Generating..."
_FAILED_MESSAGE = "Run-level analysis could not be generated. See the run log for details."

_TOOLTIP_NON_TERMINAL = (
    "A benchmark run is in progress; analysis can be generated when it finishes."
)
_TOOLTIP_GATE_BUSY = (
    "Another inference activity is in flight; analysis can be generated when it finishes."
)
_TOOLTIP_NO_RESULTS = "This run has no completed results — there is nothing to analyse."

_LABEL_GENERATE = "Generate analysis"
_LABEL_REGENERATE = "Regenerate analysis"
_LABEL_GENERATING = "Generating..."


class JudgeAnalysisSessionState(msgspec.Struct, frozen=True, kw_only=True, gc=False):
    """The session-only, non-persisted state one run's tab render additionally needs
    (STORY-065's Notes): the completed-this-session metadata line, and the most
    recent generation/regeneration's classified failure reason, if any.

    Declared privately to this sub-feature (not ``ui/results/models.py``) -- it never
    crosses this tab's own controller/select boundary and is never handed to another
    module.
    """

    metadata_line: str | None = None
    error_banner: str | None = None


def format_metadata_line(
    *, generated_at_display: str, duration_s: float, model_display: str
) -> str:
    """Render the toolbar's "Generated ... - N.N s - model: ..." metadata strip (§5)."""
    return f"Generated {generated_at_display} · {duration_s:.1f} s · model: {model_display}"


def select_judge_analysis_view_model(
    *,
    run: BenchmarkRun | None,
    has_completed_results: bool,
    is_terminal: bool,
    gate_state: InferenceActivityState,
    session: JudgeAnalysisSessionState,
) -> JudgeAnalysisViewModel:
    """Derive the tab's full render state from the current run and gate snapshot.

    Args:
        run: The selected run's header, or ``None`` before any run is selected.
        has_completed_results: Whether ``run`` has at least one ``COMPLETED`` result
            (§7's "the run has zero completed results" gate).
        is_terminal: Whether every run in the application is currently terminal
            (the view-only-during-run rule shared by every Result Widget tab).
        gate_state: The single-inference gate's current activity and context.
        session: The session-only metadata line / error banner for ``run``.

    Returns:
        The frozen ``JudgeAnalysisViewModel`` the view renders.
    """
    if run is None:
        return _no_run_view_model()
    gate_run_id = gate_state.context.run_id if gate_state.context is not None else None
    is_generating = (
        gate_state.current is InferenceActivity.JUDGE_ANALYSIS and gate_run_id == run.run_id
    )
    label = _LABEL_REGENERATE if run.run_analysis is not None else _LABEL_GENERATE
    if is_generating:
        return _generating_view_model(run=run)
    enabled, tooltip = _button_gate(
        has_completed_results=has_completed_results,
        is_terminal=is_terminal,
        gate_activity=gate_state.current,
    )
    if run.run_analysis is not None:
        return JudgeAnalysisViewModel(
            state="ready",
            narrative_markdown=run.run_analysis,
            empty_state_message=None,
            metadata_line=session.metadata_line,
            error_banner=session.error_banner,
            copy_enabled=True,
            generate_button_label=label,
            generate_button_enabled=enabled,
            generate_button_tooltip=tooltip,
        )
    if session.error_banner is not None:
        return JudgeAnalysisViewModel(
            state="failed",
            narrative_markdown=None,
            empty_state_message=_FAILED_MESSAGE,
            metadata_line=None,
            error_banner=session.error_banner,
            copy_enabled=False,
            generate_button_label=label,
            generate_button_enabled=enabled,
            generate_button_tooltip=tooltip,
        )
    message = (
        _NOT_GENERATED_RUNNING
        if run.status is RunStatus.INCOMPLETE
        else _NOT_GENERATED_NOT_REQUESTED
    )
    return JudgeAnalysisViewModel(
        state="empty",
        narrative_markdown=None,
        empty_state_message=message,
        metadata_line=None,
        error_banner=None,
        copy_enabled=False,
        generate_button_label=label,
        generate_button_enabled=enabled,
        generate_button_tooltip=tooltip,
    )


def _no_run_view_model() -> JudgeAnalysisViewModel:
    return JudgeAnalysisViewModel(
        state="empty",
        narrative_markdown=None,
        empty_state_message=_NO_RUN_MESSAGE,
        metadata_line=None,
        error_banner=None,
        copy_enabled=False,
        generate_button_label=_LABEL_GENERATE,
        generate_button_enabled=False,
        generate_button_tooltip=None,
    )


def _generating_view_model(*, run: BenchmarkRun) -> JudgeAnalysisViewModel:
    return JudgeAnalysisViewModel(
        state="generating",
        narrative_markdown=run.run_analysis,
        empty_state_message=_GENERATING_MESSAGE,
        metadata_line=_GENERATING_METADATA,
        error_banner=None,
        copy_enabled=run.run_analysis is not None,
        generate_button_label=_LABEL_GENERATING,
        generate_button_enabled=False,
        generate_button_tooltip=None,
    )


def _button_gate(
    *, has_completed_results: bool, is_terminal: bool, gate_activity: InferenceActivity
) -> tuple[bool, str | None]:
    if not is_terminal:
        return False, _TOOLTIP_NON_TERMINAL
    if gate_activity is not InferenceActivity.IDLE:
        return False, _TOOLTIP_GATE_BUSY
    if not has_completed_results:
        return False, _TOOLTIP_NO_RESULTS
    return True, None
