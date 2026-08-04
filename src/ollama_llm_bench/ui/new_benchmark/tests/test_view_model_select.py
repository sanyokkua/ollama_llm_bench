"""Unit tests for ``_internal.view_model_select`` (STORY-055-AC-3, AC-6; STORY-081-AC-2).
No Qt involvement. Covers ``build_run_start_request`` (``RunStartRequestState`` ->
``RunStartRequest``, a pure mapping) and ``compute_start_button_state`` (the Start button's
``(enabled, tooltip)`` derivation, including the readiness gate).
"""

from ollama_llm_bench.backend.domain import (
    BenchmarkRunSettingEntry,
    ModelDescriptor,
    RunMode,
    RunStartRequest,
)
from ollama_llm_bench.ui.new_benchmark._internal.view_model_select import (
    RunStartRequestState,
    build_run_start_request,
    compute_start_button_state,
)


def test_build_run_start_request_maps_every_field() -> None:
    """Proves: STORY-055-AC-3

    Every ``RunStartRequest`` field is populated from its corresponding
    ``RunStartRequestState`` field -- the full assembly mapping, with the
    override checkbox on and dirty values present.
    """
    # Arrange
    state = RunStartRequestState(
        mode=RunMode.GRADED,
        selected_pairs=(("prov-a", "model-a"), ("prov-b", "model-b")),
        judge_provider_id="judge-prov",
        judge_model="judge-model",
        judge_analysis_enabled=True,
        task_paths=("tasks/one.yaml",),
        input_sizes=(64, 256),
        output_sizes=(64, 256),
        repeats=3,
        advanced_options_overridden=True,
        advanced_dirty_values={"benchmark.temperature": "0.5"},
    )
    # Act
    request = build_run_start_request(state)
    # Assert
    assert request == RunStartRequest(
        run_mode=RunMode.GRADED,
        test_models=(
            ModelDescriptor(provider_id="prov-a", model_name="model-a"),
            ModelDescriptor(provider_id="prov-b", model_name="model-b"),
        ),
        judge_model=ModelDescriptor(provider_id="judge-prov", model_name="judge-model"),
        judge_analysis_enabled=True,
        task_paths=("tasks/one.yaml",),
        performance_config=None,
        setting_overrides=(
            BenchmarkRunSettingEntry(setting_key="benchmark.temperature", setting_value="0.5"),
        ),
    )


def test_build_run_start_request_omits_overrides_when_not_overridden() -> None:
    """Proves: STORY-055-AC-3

    Given the checkbox is unchecked (``advanced_options_overridden=False``), the
    request carries an empty ``setting_overrides`` tuple even when
    ``advanced_dirty_values`` is non-empty -- the request-assembly half of DD-47's
    carriage rule.
    """
    # Arrange
    state = RunStartRequestState(
        mode=RunMode.SYNTHETIC,
        selected_pairs=(),
        judge_provider_id=None,
        judge_model=None,
        judge_analysis_enabled=False,
        task_paths=(),
        input_sizes=(64, 256),
        output_sizes=(64, 256),
        repeats=3,
        advanced_options_overridden=False,
        advanced_dirty_values={"benchmark.temperature": "0.5"},
    )
    # Act
    request = build_run_start_request(state)
    # Assert
    assert request.setting_overrides == ()


def test_build_run_start_request_leaves_judge_model_none_when_provider_or_model_unset() -> None:
    """Proves: STORY-055-AC-3

    A missing judge provider or judge model (either ``None``) produces a
    ``judge_model=None`` request field -- no partial ``ModelDescriptor`` is ever
    built from a half-selected judge.
    """
    # Arrange
    state = RunStartRequestState(
        mode=RunMode.SYNTHETIC,
        selected_pairs=(),
        judge_provider_id="judge-prov",
        judge_model=None,
        judge_analysis_enabled=False,
        task_paths=(),
        input_sizes=(64, 256),
        output_sizes=(64, 256),
        repeats=3,
        advanced_options_overridden=False,
        advanced_dirty_values={},
    )
    # Act
    request = build_run_start_request(state)
    # Assert
    assert request.judge_model is None


def test_start_button_disabled_when_readiness_is_not_ready() -> None:
    """Proves: STORY-081-AC-2

    A totally-failed health check must never leave an enabled run-start
    affordance (08-M_app_lifecycle.md section 5).
    """
    # Arrange / Act
    enabled, tooltip = compute_start_button_state(
        validation_entries=(), gate_idle=True, readiness_not_ready=True
    )
    # Assert
    assert (enabled, tooltip) == (False, "No provider is reachable — check provider settings.")


def test_start_button_enabled_when_readiness_is_usable() -> None:
    """Proves: STORY-081-AC-2

    A usable environment is left alone -- the readiness gate only fires on a
    total failure, never on DEGRADED.
    """
    # Arrange / Act
    enabled, tooltip = compute_start_button_state(
        validation_entries=(), gate_idle=True, readiness_not_ready=False
    )
    # Assert
    assert (enabled, tooltip) == (True, "")
