"""Proves STORY-025-AC-1 — a fully-satisfied snapshot yields an empty tuple."""

from ollama_llm_bench.backend.run_drift import RunDriftDetectionInputs, make_run_drift_detector
from ollama_llm_bench.backend.run_drift.tests.conftest import (
    DEFAULT_PROVIDER_ID,
    make_model_entry,
    make_provider_config,
    make_provider_entry,
    make_provider_health,
    make_readiness_snapshot,
    make_result,
    make_run,
)


def test_satisfiable_environment_returns_empty_tuple() -> None:
    """Proves: STORY-025-AC-1

    Given a run whose frozen snapshot is fully satisfied by the current
    environment in every checked dimension, when the detector runs, then it
    returns an empty tuple.
    """
    # Arrange
    run = make_run(
        providers=(make_provider_entry(),),
        models=(make_model_entry(),),
    )
    inputs = RunDriftDetectionInputs(
        run=run,
        live_providers=(make_provider_config(),),
        live_models={DEFAULT_PROVIDER_ID: ("llama3",)},
        process_environment={},
        readiness=make_readiness_snapshot(per_provider=(make_provider_health(),)),
        resumable_results=(make_result(),),
    )
    detector = make_run_drift_detector()

    # Act
    result = detector.detect(inputs)

    # Assert
    assert result == ()
