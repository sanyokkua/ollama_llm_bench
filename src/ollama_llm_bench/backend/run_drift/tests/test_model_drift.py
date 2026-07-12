"""Proves STORY-025-AC-3 — test-model drift and the skip-under-provider-block rule (spec §6.2)."""

from ollama_llm_bench.backend.run_drift import (
    DriftKind,
    DriftSeverity,
    RunDriftDetectionInputs,
    make_run_drift_detector,
)
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

_EXPECTED_AFFECTED_COUNT = 2


def test_test_model_gone_emits_blocking_warning_with_affected_count() -> None:
    """Proves: STORY-025-AC-3

    Given a `TEST`-role model absent from its provider's live catalog, when
    that provider is not itself `BLOCKING`-warned, then one
    `MODEL_NO_LONGER_AVAILABLE` (`BLOCKING`) is emitted with the count of that
    target's retryable results.
    """
    # Arrange
    run = make_run(
        providers=(make_provider_entry(),),
        models=(make_model_entry(model_name="llama3"),),
    )
    inputs = RunDriftDetectionInputs(
        run=run,
        live_providers=(make_provider_config(),),
        live_models={DEFAULT_PROVIDER_ID: ("some-other-model",)},
        process_environment={},
        readiness=make_readiness_snapshot(per_provider=(make_provider_health(),)),
        resumable_results=(
            make_result(result_id=1, model_name="llama3"),
            make_result(result_id=2, model_name="llama3"),
        ),
    )
    detector = make_run_drift_detector()

    # Act
    result = detector.detect(inputs)

    # Assert
    assert len(result) == 1
    assert result[0].kind is DriftKind.MODEL_NO_LONGER_AVAILABLE
    assert result[0].severity is DriftSeverity.BLOCKING
    assert result[0].pending_results_affected == _EXPECTED_AFFECTED_COUNT


def test_model_check_skipped_when_provider_already_blocked() -> None:
    """Proves: STORY-025-AC-3

    Given a `TEST`-role model on a provider that is already `BLOCKING`-warned
    (here: removed), then no separate `MODEL_NO_LONGER_AVAILABLE` is emitted —
    the results are attributed to the provider warning only.
    """
    # Arrange
    run = make_run(
        providers=(make_provider_entry(),),
        models=(make_model_entry(model_name="llama3"),),
    )
    inputs = RunDriftDetectionInputs(
        run=run,
        live_providers=(),  # provider removed -> BLOCKING PROVIDER_REMOVED
        live_models={},
        process_environment={},
        readiness=make_readiness_snapshot(per_provider=()),
        resumable_results=(make_result(model_name="llama3"),),
    )
    detector = make_run_drift_detector()

    # Act
    result = detector.detect(inputs)

    # Assert
    assert len(result) == 1
    assert result[0].kind is DriftKind.PROVIDER_REMOVED
    assert all(warning.kind is not DriftKind.MODEL_NO_LONGER_AVAILABLE for warning in result)
