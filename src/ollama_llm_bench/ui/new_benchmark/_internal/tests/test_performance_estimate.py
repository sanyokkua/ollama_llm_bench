"""Property test for the Synthetic estimate derivation (STORY-071), plus the
full-widget rendering tests proving the estimate line actually reaches the
Performance Matrix section's label (AC-2, AC-3).
"""

from hypothesis import given, strategies as st
from PySide6.QtWidgets import QCheckBox, QLabel
import pytest
from pytestqt.qtbot import QtBot

from ollama_llm_bench.backend.domain import RunMode
from ollama_llm_bench.ui.new_benchmark._internal.view_model_select import (
    RunStartRequestState,
    SyntheticEstimateInputs,
    build_run_start_request,
    estimated_task_count,
    select_estimate_line,
)
from ollama_llm_bench.ui.new_benchmark.testing import FakeRunValidator
from ollama_llm_bench.ui.new_benchmark.tests.conftest import (
    FakeEventBus,
    _RealBackedModeVisibilityPolicy,
)
from ollama_llm_bench.ui.new_benchmark.tests.test_validation_and_start import _build_widget
from ollama_llm_bench.ui.theme import PlatformKind, ThemeManager

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


def test_run_analysis_toggle_appends_estimate_suffix(
    qtbot: QtBot,
    fake_event_bus: FakeEventBus,
    real_mode_visibility_policy: _RealBackedModeVisibilityPolicy,
    theme_manager: ThemeManager,
    platform_kind: PlatformKind,
) -> None:
    """Proves: STORY-071-AC-3

    Turning the Generate-run-analysis toggle ON appends ' + 1 run-analysis
    inference' to the rendered estimate line; turning it OFF removes the suffix
    and leaves the base task count unchanged.
    """
    # Arrange
    view, _gateway = _build_widget(
        run_validator=FakeRunValidator(entries=()),
        fake_event_bus=fake_event_bus,
        real_mode_visibility_policy=real_mode_visibility_policy,
        theme_manager=theme_manager,
        platform_kind=platform_kind,
    )
    qtbot.addWidget(view)
    estimate = view.performance_matrix_section.findChild(
        QLabel, "new_benchmark.performance_matrix.estimate"
    )
    assert estimate is not None
    base_text = estimate.text()  # type: ignore[unreachable]  # mypy false positive with narrowing
    assert not base_text.endswith(" + 1 run-analysis inference")
    # Act: toggle ON (direct private-attribute access mirrors
    # tests/test_advanced_options.py's `widget._activation_box.setChecked(...)`
    # pattern -- the Judge section's analysis checkbox carries no object name
    # and no public toggle method, only the read-only `judge_analysis_enabled`
    # property).
    view.judge_section._analysis_checkbox.setChecked(True)
    # Assert
    assert estimate.text() == f"{base_text} + 1 run-analysis inference"
    # Act: toggle OFF
    view.judge_section._analysis_checkbox.setChecked(False)
    # Assert
    assert estimate.text() == base_text


def test_estimate_line_updates_on_matrix_change(
    qtbot: QtBot,
    fake_event_bus: FakeEventBus,
    real_mode_visibility_policy: _RealBackedModeVisibilityPolicy,
    theme_manager: ThemeManager,
    platform_kind: PlatformKind,
) -> None:
    """Proves: STORY-071-AC-2

    Checking another size toggle re-renders the estimate line with the new
    product (2x2x3 -> 3x2x3 with zero models stays 0-based on model count;
    select one pair via the selection store first so the product is non-zero).
    """
    # Arrange
    view, _gateway = _build_widget(
        run_validator=FakeRunValidator(entries=()),
        fake_event_bus=fake_event_bus,
        real_mode_visibility_policy=real_mode_visibility_policy,
        theme_manager=theme_manager,
        platform_kind=platform_kind,
    )
    qtbot.addWidget(view)
    # SelectionStore.add takes (provider_id, model_name) as two positional
    # strings (`_internal/selection_store.py`), not a single pair tuple.
    view.test_models_section.selection.add("prov-1", "model-a")
    view.test_models_section.selection_changed.emit()  # re-render (2*2*3*1 = 12)
    estimate = view.performance_matrix_section.findChild(
        QLabel, "new_benchmark.performance_matrix.estimate"
    )
    assert estimate is not None
    assert estimate.text() == "Estimated tasks: 12"  # type: ignore[unreachable]  # mypy false positive with narrowing
    md_box = view.performance_matrix_section.findChild(
        QCheckBox, "new_benchmark.performance_matrix.input.MD"
    )
    assert md_box is not None
    md_box.setChecked(True)  # 3*2*3*1 = 18
    assert estimate.text() == "Estimated tasks: 18"
