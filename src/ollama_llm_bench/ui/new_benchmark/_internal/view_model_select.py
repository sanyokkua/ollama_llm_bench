"""Pure state -> ``NewBenchmarkViewModel`` derivation (STORY-054, STORY-055). No Qt import."""

from collections.abc import Mapping

import msgspec

from ollama_llm_bench.backend.domain import (
    BenchmarkRunSettingEntry,
    ModelDescriptor,
    PerformanceConfig,
    ProviderConfig,
    RunMode,
    RunStartRequest,
    SettingKey,
)
from ollama_llm_bench.ui.new_benchmark._internal.section_visibility import visible_section_set
from ollama_llm_bench.ui.new_benchmark._internal.selection_store import SelectionStore
from ollama_llm_bench.ui.new_benchmark.models import (
    AdvancedOptionsViewModel,
    EmbeddingStatusViewModel,
    NewBenchmarkViewModel,
    RunValidationSeverity,
    SelectedModelPairViewModel,
    TaskFileRowViewModel,
    ValidationEntry,
)
from ollama_llm_bench.ui.new_benchmark.protocols import ModeVisibilityPolicy

__all__: list[str] = [
    "NewBenchmarkViewState",
    "RunStartRequestState",
    "SyntheticEstimateInputs",
    "build_run_start_request",
    "compute_start_button_state",
    "estimated_task_count",
    "select_estimate_line",
    "select_view_model",
]

_IN_FLIGHT_TOOLTIP = "Another inference activity is in flight — please wait."
_REVIEW_WARNINGS_TOOLTIP = "Click to review warnings before starting."
_ANALYSIS_SUFFIX = " + 1 run-analysis inference"


class NewBenchmarkViewState(msgspec.Struct, frozen=True, kw_only=True, gc=False):
    """Bundles ``select_view_model``'s non-``mode`` inputs (coding-style.md's 4-parameter
    hard maximum -- ``select_view_model`` would otherwise take 7 keyword arguments).

    Attributes:
        policy: The Mode Visibility Policy collaborator.
        task_file_rows: The Task Files section's current rows.
        selection: The Test Models section's selection store.
        provider_configs: Every known provider, keyed by ``provider_id``, for
            resolving a selected pair's display name.
        browsed_provider_id: The Test Models section's currently browsed provider.
        hide_embedding_models: The current hide-embedding checkbox state.
        judge_analysis_enabled: The Judge section's analysis-toggle state.
        judge_provider_id: The Judge section's currently selected provider.
        embedding_status: The Judge section's embedding status row content;
            ``None`` outside ``GRADED``.
        advanced_options: The Advanced Options section's current state.
        validation_entries: Every current Run Validator finding.
        start_enabled: Whether the Start Benchmark button is enabled.
        start_tooltip: The Start Benchmark button's tooltip.
        input_sizes: The Performance Matrix section's checked Input Sizes.
        output_sizes: The Performance Matrix section's checked Output Sizes.
        repeats: The Performance Matrix section's Repeats stepper value.
    """

    policy: ModeVisibilityPolicy
    task_file_rows: tuple[TaskFileRowViewModel, ...]
    selection: SelectionStore
    provider_configs: Mapping[str, ProviderConfig]
    browsed_provider_id: str | None
    hide_embedding_models: bool
    judge_analysis_enabled: bool
    judge_provider_id: str | None
    embedding_status: EmbeddingStatusViewModel | None
    advanced_options: AdvancedOptionsViewModel
    validation_entries: tuple[ValidationEntry, ...]
    start_enabled: bool
    start_tooltip: str
    input_sizes: tuple[int, ...]
    output_sizes: tuple[int, ...]
    repeats: int


class SyntheticEstimateInputs(msgspec.Struct, frozen=True, kw_only=True, gc=False):
    """Bundles the live-estimate factors (`synthetic.md` §4; 4-parameter maximum).

    Attributes:
        input_size_count: Checked Input Sizes toggle count.
        output_size_count: Checked Output Sizes toggle count.
        repeats: The Repeats stepper value.
        model_count: Selected ``(provider, model)`` pair count.
        analysis_enabled: The Generate-run-analysis toggle state.
    """

    input_size_count: int
    output_size_count: int
    repeats: int
    model_count: int
    analysis_enabled: bool


def estimated_task_count(inputs: SyntheticEstimateInputs) -> int:
    """Return `N_input_sizes x N_output_sizes x N_repeats x N_models` (§4.2)."""
    return inputs.input_size_count * inputs.output_size_count * inputs.repeats * inputs.model_count


def select_estimate_line(inputs: SyntheticEstimateInputs) -> str:
    """Render the live estimate line, appending the run-analysis suffix when ON."""
    suffix = _ANALYSIS_SUFFIX if inputs.analysis_enabled else ""
    return f"Estimated tasks: {estimated_task_count(inputs)}{suffix}"


def select_view_model(*, mode: RunMode, state: NewBenchmarkViewState) -> NewBenchmarkViewModel:
    """Derive the full widget ``ViewModel`` from current controller-held state.

    Args:
        mode: The currently selected run mode.
        state: Every other piece of controller-held state this derivation needs.

    Returns:
        The frozen ``NewBenchmarkViewModel`` snapshot the view renders.
    """
    selected_models = tuple(
        SelectedModelPairViewModel(
            provider_id=provider_id,
            provider_name=state.provider_configs[provider_id].name
            if provider_id in state.provider_configs
            else provider_id,
            model_name=model_name,
        )
        for provider_id, model_name in state.selection.pairs
    )
    return NewBenchmarkViewModel(
        mode=mode,
        visible_sections=tuple(visible_section_set(mode=mode, policy=state.policy)),
        task_file_rows=state.task_file_rows,
        selected_models=selected_models,
        browsed_provider_id=state.browsed_provider_id,
        available_model_names=(),
        selected_model_names_for_browsed_provider=(),
        hide_embedding_models=state.hide_embedding_models,
        judge_analysis_enabled=state.judge_analysis_enabled,
        judge_provider_id=state.judge_provider_id,
        embedding_status=state.embedding_status,
        advanced_options=state.advanced_options,
        validation_entries=state.validation_entries,
        start_enabled=state.start_enabled,
        start_tooltip=state.start_tooltip,
        synthetic_estimate_line=(
            select_estimate_line(
                SyntheticEstimateInputs(
                    input_size_count=len(state.input_sizes),
                    output_size_count=len(state.output_sizes),
                    repeats=state.repeats,
                    model_count=len(selected_models),
                    analysis_enabled=state.judge_analysis_enabled,
                )
            )
            if mode is RunMode.SYNTHETIC
            else None
        ),
    )


class RunStartRequestState(msgspec.Struct, frozen=True, kw_only=True, gc=False):
    """Bundles ``build_run_start_request``'s inputs (coding-style.md's 4-parameter
    hard maximum).

    Attributes:
        mode: The currently selected run mode.
        selected_pairs: Every selected ``(provider_id, model_name)`` test-model pair.
        judge_provider_id: The Judge section's selected provider, or ``None``.
        judge_model: The Judge section's selected model, or ``None``.
        judge_analysis_enabled: The Judge section's analysis-toggle state.
        task_paths: The Task Files section's current file paths (empty in ``SYNTHETIC``).
        input_sizes: The Performance Matrix section's checked Input Sizes; used to
            assemble ``PerformanceConfig`` in ``SYNTHETIC`` (§7.4).
        output_sizes: The Performance Matrix section's checked Output Sizes; used to
            assemble ``PerformanceConfig`` in ``SYNTHETIC`` (§7.4).
        repeats: The Performance Matrix section's Repeats stepper value; used to
            assemble ``PerformanceConfig`` in ``SYNTHETIC`` (§7.4).
        advanced_options_overridden: The Advanced Options activation-checkbox state.
        advanced_dirty_values: The subset of ``advanced_options.values`` the user
            changed from its seeded value -- only these are carried (DD-47).
    """

    mode: RunMode
    selected_pairs: tuple[tuple[str, str], ...]
    judge_provider_id: str | None
    judge_model: str | None
    judge_analysis_enabled: bool
    task_paths: tuple[str, ...]
    input_sizes: tuple[int, ...]
    output_sizes: tuple[int, ...]
    repeats: int
    advanced_options_overridden: bool
    advanced_dirty_values: Mapping[SettingKey, str]


def build_run_start_request(state: RunStartRequestState) -> RunStartRequest:
    """Assemble a ``RunStartRequest`` from current widget state (STORY-055-AC-3, AC-6).

    Args:
        state: Every field the request needs, gathered from the widget's sections.

    Returns:
        The frozen ``RunStartRequest`` -- both the Run Validator's `validate()` input
        and, on Start, the payload handed to ``NewBenchmarkGateway.start_run``.
    """
    test_models = tuple(
        ModelDescriptor(provider_id=provider_id, model_name=model_name)
        for provider_id, model_name in state.selected_pairs
    )
    judge_model = (
        ModelDescriptor(provider_id=state.judge_provider_id, model_name=state.judge_model)
        if state.judge_provider_id and state.judge_model
        else None
    )
    setting_overrides = (
        tuple(
            BenchmarkRunSettingEntry(setting_key=key, setting_value=value)
            for key, value in sorted(state.advanced_dirty_values.items())
        )
        if state.advanced_options_overridden
        else ()
    )
    performance_config = (
        PerformanceConfig(
            input_sizes=state.input_sizes,
            output_sizes=state.output_sizes,
            repeats=state.repeats,
        )
        if state.mode is RunMode.SYNTHETIC
        else None
    )
    return RunStartRequest(
        run_mode=state.mode,
        test_models=test_models,
        judge_model=judge_model,
        judge_analysis_enabled=state.judge_analysis_enabled,
        task_paths=state.task_paths,
        performance_config=performance_config,
        setting_overrides=setting_overrides,
    )


def compute_start_button_state(
    *, validation_entries: tuple[ValidationEntry, ...], gate_idle: bool
) -> tuple[bool, str]:
    """Derive the Start button's ``(enabled, tooltip)`` pair (STORY-055-AC-4, AC-5).

    Args:
        validation_entries: The Run Validator's current findings.
        gate_idle: Whether the single-inference gate is currently ``IDLE``.

    Returns:
        ``(True, "")`` when nothing blocks Start and there is nothing to review;
        ``(True, "Click to review warnings before starting.")`` when only soft
        warnings remain; ``(False, <tooltip>)`` otherwise -- a joined hard-error
        message list takes precedence over the in-flight-gate tooltip.
    """
    hard_error_messages = tuple(
        entry.message
        for entry in validation_entries
        if entry.severity is RunValidationSeverity.HARD_ERROR
    )
    if hard_error_messages:
        return False, "\n".join(hard_error_messages)
    if not gate_idle:
        return False, _IN_FLIGHT_TOOLTIP
    if validation_entries:
        return True, _REVIEW_WARNINGS_TOOLTIP
    return True, ""
