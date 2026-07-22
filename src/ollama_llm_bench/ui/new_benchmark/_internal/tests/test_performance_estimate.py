"""Property test for the Synthetic estimate derivation (STORY-071)."""

from hypothesis import given, strategies as st
import pytest

from ollama_llm_bench.backend.domain import RunMode
from ollama_llm_bench.ui.new_benchmark._internal.view_model_select import (
    RunStartRequestState,
    SyntheticEstimateInputs,
    build_run_start_request,
    estimated_task_count,
    select_estimate_line,
)

_EXPECTED_REPEATS = 3


@pytest.mark.property
@given(
    input_size_count=st.integers(min_value=1, max_value=5),
    output_size_count=st.integers(min_value=1, max_value=5),
    repeats=st.integers(min_value=1, max_value=20),
    model_count=st.integers(min_value=1, max_value=12),
    analysis_enabled=st.booleans(),
)
def test_estimate_equals_product_of_counts(
    input_size_count: int,
    output_size_count: int,
    repeats: int,
    model_count: int,
    *,
    analysis_enabled: bool,
) -> None:
    """Proves: STORY-071-AC-2

    For every combination of at least one input size, one output size, repeats
    1..20, and model count >= 1, the displayed estimate equals
    N_input x N_output x N_repeats x N_models.
    """
    inputs = SyntheticEstimateInputs(
        input_size_count=input_size_count,
        output_size_count=output_size_count,
        repeats=repeats,
        model_count=model_count,
        analysis_enabled=analysis_enabled,
    )
    count = estimated_task_count(inputs)
    assert count == input_size_count * output_size_count * repeats * model_count
    assert f"Estimated tasks: {count}" in select_estimate_line(inputs)


def test_estimate_suffix_present_only_when_analysis_enabled() -> None:
    """Proves: STORY-071-AC-3

    The pure line builder appends ' + 1 run-analysis inference' exactly when the
    analysis toggle is on, leaving the base count unchanged.
    """
    base = SyntheticEstimateInputs(
        input_size_count=2, output_size_count=2, repeats=3, model_count=1, analysis_enabled=False
    )
    enabled = SyntheticEstimateInputs(
        input_size_count=2, output_size_count=2, repeats=3, model_count=1, analysis_enabled=True
    )
    assert select_estimate_line(base) == "Estimated tasks: 12"
    assert select_estimate_line(enabled) == "Estimated tasks: 12 + 1 run-analysis inference"


def test_build_request_populates_performance_config_in_synthetic() -> None:
    """Proves: STORY-071-AC-5

    build_run_start_request assembles PerformanceConfig from the matrix fields in
    SYNTHETIC and leaves it None in TASKS.
    """
    # `RunStartRequestState(mode=..., **common)` upsets mypy's keyword-argument
    # inference for a heterogeneous dict, so both constructions are spelled out
    # field-by-field instead (per the story-071 task-2 brief).
    synthetic = build_run_start_request(
        RunStartRequestState(
            mode=RunMode.SYNTHETIC,
            selected_pairs=(("prov-1", "model-a"),),
            judge_provider_id=None,
            judge_model=None,
            judge_analysis_enabled=False,
            task_paths=(),
            input_sizes=(64, 256),
            output_sizes=(64,),
            repeats=_EXPECTED_REPEATS,
            advanced_options_overridden=False,
            advanced_dirty_values={},
        )
    )
    tasks = build_run_start_request(
        RunStartRequestState(
            mode=RunMode.TASKS,
            selected_pairs=(("prov-1", "model-a"),),
            judge_provider_id=None,
            judge_model=None,
            judge_analysis_enabled=False,
            task_paths=(),
            input_sizes=(64, 256),
            output_sizes=(64,),
            repeats=_EXPECTED_REPEATS,
            advanced_options_overridden=False,
            advanced_dirty_values={},
        )
    )
    assert synthetic.performance_config is not None
    assert synthetic.performance_config.input_sizes == (64, 256)
    assert synthetic.performance_config.output_sizes == (64,)
    assert synthetic.performance_config.repeats == _EXPECTED_REPEATS
    assert tasks.performance_config is None
