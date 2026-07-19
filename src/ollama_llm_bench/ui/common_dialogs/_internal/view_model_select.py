"""Pure ``RunStartRequest``/``AppReadinessSnapshot`` -> ``RunSummaryViewModel``
derivation (STORY-055). No Qt import.
"""

from ollama_llm_bench.backend.domain import (
    AppReadinessSnapshot,
    PerformanceConfig,
    RunMode,
    RunStartRequest,
)
from ollama_llm_bench.ui.common_dialogs.models import RunSummaryViewModel
from ollama_llm_bench.ui.new_benchmark.models import RunValidationSeverity, ValidationEntry

__all__: list[str] = ["select_run_summary_view_model"]

_MODE_DISPLAY_NAMES: dict[RunMode, str] = {
    RunMode.SYNTHETIC: "Synthetic Benchmark",
    RunMode.TASKS: "Task Benchmark",
    RunMode.GRADED: "Graded Benchmark",
}


def select_run_summary_view_model(
    *,
    request: RunStartRequest,
    readiness: AppReadinessSnapshot,
    validation_entries: tuple[ValidationEntry, ...] = (),
) -> RunSummaryViewModel:
    """Derive the Run Summary dialog's ``ViewModel`` from the request under review.

    Args:
        request: The ``RunStartRequest`` about to be confirmed.
        readiness: The current readiness snapshot (re-checked on open, §8).
        validation_entries: The Run Validator's current findings; only soft
            warnings are rendered (§4 Warnings callout).

    Returns:
        The frozen ``RunSummaryViewModel`` the dialog renders.
    """
    mode = request.run_mode
    override_rows = tuple(
        f"{entry.setting_value} · {entry.setting_key}" for entry in request.setting_overrides
    )
    return RunSummaryViewModel(
        run_mode=mode,
        run_name_preview=f"{_MODE_DISPLAY_NAMES[mode]} — preview",
        test_model_rows=tuple(
            f"{target.provider_id} · {target.model_name}" for target in request.test_models
        ),
        work_to_be_done=_work_to_be_done(request),
        warnings=tuple(
            entry.message
            for entry in validation_entries
            if entry.severity is RunValidationSeverity.SOFT_WARNING
        ),
        synthetic_matrix_rows=(
            _synthetic_matrix_rows(request.performance_config)
            if mode is RunMode.SYNTHETIC
            else None
        ),
        task_file_summary=(
            f"{len(request.task_paths)} task file(s)"
            if mode in (RunMode.TASKS, RunMode.GRADED)
            else None
        ),
        judge_summary=_judge_summary(request),
        embedding_summary=(
            _embedding_summary(request, readiness) if mode is RunMode.GRADED else None
        ),
        inference_snapshot_rows=override_rows,
        pipeline_events_rows=(),
        evaluation_phase_rows=() if mode is RunMode.GRADED else None,
    )


def _judge_summary(request: RunStartRequest) -> str:
    if request.judge_model is None:
        return "No judge model configured."
    analysis_state = "on" if request.judge_analysis_enabled else "off"
    return (
        f"{request.judge_model.provider_id} · {request.judge_model.model_name} "
        f"(run analysis: {analysis_state})"
    )


def _embedding_summary(request: RunStartRequest, readiness: AppReadinessSnapshot) -> str:
    if request.embedding_model is None:
        return "No embedding model configured."
    reachability = "reachable" if readiness.embedding_reachable else "unreachable"
    return (
        f"{request.embedding_model.provider_id} · {request.embedding_model.model_name} "
        f"({reachability})"
    )


def _synthetic_matrix_rows(performance_config: PerformanceConfig | None) -> tuple[str, ...]:
    if performance_config is None:
        return ()
    return tuple(
        f"{input_size} in x {output_size} out x {performance_config.repeats} repeats"
        for input_size in performance_config.input_sizes
        for output_size in performance_config.output_sizes
    )


def _work_to_be_done(request: RunStartRequest) -> str:
    model_count = len(request.test_models)
    if request.run_mode is RunMode.SYNTHETIC and request.performance_config is not None:
        cell_count = len(request.performance_config.input_sizes) * len(
            request.performance_config.output_sizes
        )
        inference_calls = model_count * cell_count * request.performance_config.repeats
    else:
        # Simplified: counts task FILES, not parsed tasks -- the actual per-file task
        # count needs the (out-of-scope, backend) TaskFileLoader, which this dialog's
        # narrow RunSummaryGateway does not expose.
        inference_calls = model_count * len(request.task_paths)
    suffix = " + 1 run-analysis inference" if request.judge_analysis_enabled else ""
    return f"{inference_calls} inference call(s){suffix}"
