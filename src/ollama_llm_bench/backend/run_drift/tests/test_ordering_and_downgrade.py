"""Proves STORY-025-AC-6 — result ordering and the absent-readiness downgrade (spec §6.5, §8)."""

from ollama_llm_bench.backend.domain import ModelRole
from ollama_llm_bench.backend.run_drift import (
    DriftKind,
    DriftSeverity,
    RunDriftDetectionInputs,
    make_run_drift_detector,
)
from ollama_llm_bench.backend.run_drift.tests.conftest import (
    DEFAULT_PROVIDER_ID,
    JUDGE_PROVIDER_ID,
    make_model_entry,
    make_provider_config,
    make_provider_entry,
    make_provider_health,
    make_readiness_snapshot,
    make_run,
)

_LOWER_PROVIDER_ID = "00000000-0000-4000-8000-000000000000"


def test_ordering_is_blocking_before_warning_then_by_provider_id_then_model_name() -> None:
    """Proves: STORY-025-AC-6

    Given a mix of `BLOCKING` and `WARNING` items across multiple providers
    and models, when the detector assembles its result, then the tuple is
    ordered `BLOCKING` before `WARNING` and, within each severity, by
    `provider_id` (nulls last) then `model_name` (nulls last).
    """
    # Arrange: two providers.
    # - JUDGE_PROVIDER_ID (higher UUID) is disabled -> BLOCKING PROVIDER_NOW_DISABLED.
    # - _LOWER_PROVIDER_ID (lower UUID, unreachable, readiness ABSENT) -> WARNING
    #   PROVIDER_NOW_UNREACHABLE (downgraded per §8).
    run = make_run(
        providers=(
            make_provider_entry(provider_id=_LOWER_PROVIDER_ID),
            make_provider_entry(provider_id=JUDGE_PROVIDER_ID),
        ),
        models=(
            make_model_entry(role=ModelRole.TEST, provider_id=_LOWER_PROVIDER_ID),
            make_model_entry(role=ModelRole.TEST, provider_id=JUDGE_PROVIDER_ID),
        ),
    )
    inputs = RunDriftDetectionInputs(
        run=run,
        live_providers=(
            make_provider_config(provider_id=_LOWER_PROVIDER_ID, enabled=True),
            make_provider_config(provider_id=JUDGE_PROVIDER_ID, enabled=False),
        ),
        live_models={_LOWER_PROVIDER_ID: ("llama3",), JUDGE_PROVIDER_ID: ("llama3",)},
        process_environment={},
        readiness=None,  # absent readiness -> reachability warnings downgrade to WARNING
        resumable_results=(),
    )
    detector = make_run_drift_detector()

    # Act
    result = detector.detect(inputs)

    # Assert
    assert [w.severity for w in result] == [DriftSeverity.BLOCKING, DriftSeverity.WARNING]
    assert result[0].provider_id == JUDGE_PROVIDER_ID
    assert result[1].provider_id == _LOWER_PROVIDER_ID


def test_ordering_sorts_by_provider_id_then_model_name_within_same_severity() -> None:
    """Proves: STORY-025-AC-6

    Within the same severity, items are ordered by `provider_id` first, then
    by `model_name` (nulls last) — proven here by two `BLOCKING`
    `MODEL_NO_LONGER_AVAILABLE` warnings on the same provider with different
    model names.
    """
    # Arrange
    run = make_run(
        providers=(make_provider_entry(),),
        models=(
            make_model_entry(model_name="z-model"),
            make_model_entry(model_name="a-model"),
        ),
    )
    inputs = RunDriftDetectionInputs(
        run=run,
        live_providers=(make_provider_config(),),
        live_models={DEFAULT_PROVIDER_ID: ()},  # neither model is advertised
        process_environment={},
        readiness=make_readiness_snapshot(per_provider=(make_provider_health(),)),
        resumable_results=(),
    )
    detector = make_run_drift_detector()

    # Act
    result = detector.detect(inputs)

    # Assert
    assert [w.model_name for w in result] == ["a-model", "z-model"]


def test_absent_readiness_downgrades_reachability_warning_to_warning_severity() -> None:
    """Proves: STORY-025-AC-6

    Given an absent readiness snapshot, reachability-related warnings are
    emitted as `WARNING` rather than `BLOCKING`, and the detector does not
    raise.
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
        readiness=None,
        resumable_results=(),
    )
    detector = make_run_drift_detector()

    # Act
    result = detector.detect(inputs)

    # Assert
    assert len(result) == 1
    assert result[0].kind is DriftKind.PROVIDER_NOW_UNREACHABLE
    assert result[0].severity is DriftSeverity.WARNING


def test_incomplete_run_snapshot_yields_single_blocking_provider_removed_warning() -> None:
    """Proves: STORY-025-AC-6

    Given a run snapshot with no `providers` or no `models` (a corrupt run
    record per spec §8), when the detector runs, then it returns a single
    `BLOCKING` warning with `kind = PROVIDER_REMOVED` and a detail naming the
    incomplete snapshot, and it does not raise.
    """
    # Arrange
    run = make_run(providers=(), models=())
    inputs = RunDriftDetectionInputs(
        run=run,
        live_providers=(),
        live_models={},
        process_environment={},
        readiness=None,
        resumable_results=(),
    )
    detector = make_run_drift_detector()

    # Act
    result = detector.detect(inputs)

    # Assert
    assert len(result) == 1
    assert result[0].kind is DriftKind.PROVIDER_REMOVED
    assert result[0].severity is DriftSeverity.BLOCKING
    assert "incomplete" in result[0].detail.lower()
