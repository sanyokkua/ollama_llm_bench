"""Proves STORY-025-AC-4 — the judge/embedding checks respect the snapshot gate flags (spec §6.3, §6.4, §7)."""

import pytest

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
    make_flags_snapshot,
    make_model_entry,
    make_provider_config,
    make_provider_entry,
    make_provider_health,
    make_readiness_snapshot,
    make_run,
)


@pytest.mark.parametrize(
    ("phase_judge_enabled", "judge_run_analysis_enabled", "judge_model_live", "expect_warning"),
    [
        (True, False, False, True),  # needed via eval.phase_judge_enabled, missing -> warning
        (
            False,
            True,
            False,
            True,
        ),  # needed via feature.judge_run_analysis_enabled, missing -> warning
        (True, False, True, False),  # needed, present -> no warning
        (False, False, False, False),  # not needed, missing -> no warning even though missing
    ],
    ids=[
        "phase_judge_enabled_and_missing",
        "judge_run_analysis_enabled_and_missing",
        "needed_and_present",
        "not_needed_and_missing",
    ],
)
def test_judge_check_respects_snapshot_flags(
    *,
    phase_judge_enabled: bool,
    judge_run_analysis_enabled: bool,
    judge_model_live: bool,
    expect_warning: bool,
) -> None:
    """Proves: STORY-025-AC-4

    The judge check runs only when `eval.phase_judge_enabled` or
    `feature.judge_run_analysis_enabled` is true in the snapshot; when it
    does not run, a missing judge model produces no warning.
    """
    # Arrange
    run = make_run(
        providers=(
            make_provider_entry(provider_id=DEFAULT_PROVIDER_ID),
            make_provider_entry(provider_id=JUDGE_PROVIDER_ID),
        ),
        models=(
            make_model_entry(role=ModelRole.TEST, provider_id=DEFAULT_PROVIDER_ID),
            make_model_entry(
                role=ModelRole.JUDGE, provider_id=JUDGE_PROVIDER_ID, model_name="judge-model"
            ),
        ),
        settings_snapshot=make_flags_snapshot(
            phase_judge_enabled=phase_judge_enabled,
            judge_run_analysis_enabled=judge_run_analysis_enabled,
        ),
    )
    judge_live_models = ("judge-model",) if judge_model_live else ()
    inputs = RunDriftDetectionInputs(
        run=run,
        live_providers=(
            make_provider_config(provider_id=DEFAULT_PROVIDER_ID),
            make_provider_config(provider_id=JUDGE_PROVIDER_ID),
        ),
        live_models={
            DEFAULT_PROVIDER_ID: ("llama3",),
            JUDGE_PROVIDER_ID: judge_live_models,
        },
        process_environment={},
        readiness=make_readiness_snapshot(
            per_provider=(
                make_provider_health(provider_id=DEFAULT_PROVIDER_ID),
                make_provider_health(provider_id=JUDGE_PROVIDER_ID),
            )
        ),
        resumable_results=(),
    )
    detector = make_run_drift_detector()

    # Act
    result = detector.detect(inputs)

    # Assert
    has_judge_warning = any(w.kind is DriftKind.JUDGE_MODEL_UNAVAILABLE for w in result)
    assert has_judge_warning is expect_warning


@pytest.mark.parametrize(
    ("phase_cosine_enabled", "embedding_model_live", "expect_warning"),
    [
        (True, False, True),  # cosine needed, embedding missing -> warning
        (True, True, False),  # cosine needed, embedding present -> no warning
        (False, False, False),  # cosine not needed, missing -> no warning even though missing
    ],
    ids=["cosine_enabled_and_missing", "cosine_enabled_and_present", "cosine_disabled_and_missing"],
)
def test_embedding_check_respects_snapshot_flag(
    *, phase_cosine_enabled: bool, embedding_model_live: bool, expect_warning: bool
) -> None:
    """Proves: STORY-025-AC-4

    The embedding check runs only when `eval.phase_cosine_enabled` is true in
    the snapshot; when it does not run, a missing embedding model produces no
    warning.
    """
    # Arrange
    run = make_run(
        providers=(make_provider_entry(),),
        models=(
            make_model_entry(role=ModelRole.TEST),
            make_model_entry(role=ModelRole.EMBEDDING, model_name="nomic-embed-text"),
        ),
        settings_snapshot=make_flags_snapshot(phase_cosine_enabled=phase_cosine_enabled),
    )
    embedding_live_models = ("llama3", "nomic-embed-text") if embedding_model_live else ("llama3",)
    inputs = RunDriftDetectionInputs(
        run=run,
        live_providers=(make_provider_config(),),
        live_models={DEFAULT_PROVIDER_ID: embedding_live_models},
        process_environment={},
        readiness=make_readiness_snapshot(per_provider=(make_provider_health(),)),
        resumable_results=(),
    )
    detector = make_run_drift_detector()

    # Act
    result = detector.detect(inputs)

    # Assert
    has_embedding_warning = any(
        w.kind in (DriftKind.EMBEDDING_MODEL_UNAVAILABLE, DriftKind.EMBEDDING_NOW_UNREACHABLE)
        for w in result
    )
    assert has_embedding_warning is expect_warning


def test_judge_check_needed_but_no_judge_entry_in_snapshot_emits_no_warning() -> None:
    """Proves: STORY-025-AC-4

    When the snapshot needs the judge but carries no `JUDGE`-role
    `BenchmarkRunModelEntry` at all, the check finds nothing to evaluate and
    emits no warning.
    """
    # Arrange
    run = make_run(
        providers=(make_provider_entry(),),
        models=(make_model_entry(role=ModelRole.TEST),),
        settings_snapshot=make_flags_snapshot(phase_judge_enabled=True),
    )
    inputs = RunDriftDetectionInputs(
        run=run,
        live_providers=(make_provider_config(),),
        live_models={DEFAULT_PROVIDER_ID: ("llama3",)},
        process_environment={},
        readiness=make_readiness_snapshot(per_provider=(make_provider_health(),)),
        resumable_results=(),
    )
    detector = make_run_drift_detector()

    # Act
    result = detector.detect(inputs)

    # Assert
    assert result == ()


def test_judge_check_skipped_when_judge_provider_already_blocked() -> None:
    """Proves: STORY-025-AC-4

    Resolve the judge's `provider_id` against Check 1's results (spec §6.3):
    when that provider is already `BLOCKING`-warned (here: removed), the
    judge is implicitly unavailable and `JUDGE_MODEL_UNAVAILABLE` still fires,
    with its detail pointing at the provider warning rather than repeating
    the diagnosis.
    """
    # Arrange
    run = make_run(
        providers=(make_provider_entry(provider_id=JUDGE_PROVIDER_ID),),
        models=(make_model_entry(role=ModelRole.JUDGE, provider_id=JUDGE_PROVIDER_ID),),
        settings_snapshot=make_flags_snapshot(phase_judge_enabled=True),
    )
    inputs = RunDriftDetectionInputs(
        run=run,
        live_providers=(),  # judge provider removed -> BLOCKING PROVIDER_REMOVED
        live_models={},
        process_environment={},
        readiness=make_readiness_snapshot(per_provider=()),
        resumable_results=(),
    )
    detector = make_run_drift_detector()

    # Act
    result = detector.detect(inputs)

    # Assert
    judge_warnings = [w for w in result if w.kind is DriftKind.JUDGE_MODEL_UNAVAILABLE]
    assert len(judge_warnings) == 1
    assert judge_warnings[0].detail == "see the provider warning above"


def test_embedding_check_needed_but_no_embedding_entry_in_snapshot_emits_no_warning() -> None:
    """Proves: STORY-025-AC-4

    When cosine is needed but the snapshot carries no `EMBEDDING`-role
    `BenchmarkRunModelEntry` at all, the check finds nothing to evaluate and
    emits no warning.
    """
    # Arrange
    run = make_run(
        providers=(make_provider_entry(),),
        models=(make_model_entry(role=ModelRole.TEST),),
        settings_snapshot=make_flags_snapshot(phase_cosine_enabled=True),
    )
    inputs = RunDriftDetectionInputs(
        run=run,
        live_providers=(make_provider_config(),),
        live_models={DEFAULT_PROVIDER_ID: ("llama3",)},
        process_environment={},
        readiness=make_readiness_snapshot(per_provider=(make_provider_health(),)),
        resumable_results=(),
    )
    detector = make_run_drift_detector()

    # Act
    result = detector.detect(inputs)

    # Assert
    assert result == ()


def test_embedding_check_skipped_when_embedding_provider_already_blocked() -> None:
    """Proves: STORY-025-AC-4

    When the frozen embedding pair's provider already produced a `BLOCKING`
    warning in Check 1 (spec §6.4), the embedding warning's `detail` points
    at it rather than repeating the diagnosis.
    """
    # Arrange
    run = make_run(
        providers=(make_provider_entry(provider_id=DEFAULT_PROVIDER_ID),),
        models=(
            make_model_entry(
                role=ModelRole.EMBEDDING,
                provider_id=DEFAULT_PROVIDER_ID,
                model_name="nomic-embed-text",
            ),
        ),
        settings_snapshot=make_flags_snapshot(phase_cosine_enabled=True),
    )
    inputs = RunDriftDetectionInputs(
        run=run,
        live_providers=(),  # embedding provider removed -> BLOCKING PROVIDER_REMOVED
        live_models={},
        process_environment={},
        readiness=make_readiness_snapshot(per_provider=()),
        resumable_results=(),
    )
    detector = make_run_drift_detector()

    # Act
    result = detector.detect(inputs)

    # Assert
    embedding_warnings = [w for w in result if w.kind is DriftKind.EMBEDDING_NOW_UNREACHABLE]
    assert len(embedding_warnings) == 1
    assert embedding_warnings[0].detail == "see the provider warning above"


def test_embedding_check_reachability_recheck_downgrades_with_absent_readiness() -> None:
    """Proves: STORY-025-AC-4

    Check 4 re-checks reachability of the frozen embedding pair's provider
    independently of Check 1 (spec §6.4). When the provider passed Check 1
    (readiness absent downgrades Check 1's own finding to `WARNING`, so the
    provider is not `BLOCKING`-warned and Check 4 is not skipped) but no
    readiness data exists to confirm reachability, Check 4 still emits
    `EMBEDDING_NOW_UNREACHABLE` at `BLOCKING` severity — an un-evaluable
    embedding-reachability dimension is not silently treated as satisfied.
    """
    # Arrange
    run = make_run(
        providers=(make_provider_entry(),),
        models=(
            make_model_entry(
                role=ModelRole.EMBEDDING,
                provider_id=DEFAULT_PROVIDER_ID,
                model_name="nomic-embed-text",
            ),
        ),
        settings_snapshot=make_flags_snapshot(phase_cosine_enabled=True),
    )
    inputs = RunDriftDetectionInputs(
        run=run,
        live_providers=(make_provider_config(),),
        live_models={DEFAULT_PROVIDER_ID: ("nomic-embed-text",)},
        process_environment={},
        readiness=None,  # absent -> Check 1 downgrades to WARNING, provider not blocked
        resumable_results=(),
    )
    detector = make_run_drift_detector()

    # Act
    result = detector.detect(inputs)

    # Assert
    embedding_warnings = [w for w in result if w.kind is DriftKind.EMBEDDING_NOW_UNREACHABLE]
    assert len(embedding_warnings) == 1
    assert embedding_warnings[0].severity is DriftSeverity.BLOCKING


def test_embedding_check_treats_a_readiness_snapshot_with_no_matching_health_as_unreachable() -> (
    None
):
    """Proves: STORY-025-AC-4

    When a readiness snapshot is present but carries no `ProviderHealth`
    entry for the frozen embedding pair's provider (a partial probe result —
    here the embedding provider is not itself one of the run's frozen
    `providers`, so Check 1 never evaluates it and cannot pre-block it),
    Check 4's own reachability lookup treats the no-match case as
    unreachable rather than assuming satisfaction from silence.
    """
    # Arrange: the run's providers snapshot only names JUDGE_PROVIDER_ID; the
    # EMBEDDING entry's provider (DEFAULT_PROVIDER_ID) is absent from
    # run.providers, so Check 1 never marks it blocked and Check 4's own
    # `_provider_reachable` lookup runs standalone against the readiness
    # snapshot, which has no health entry for it either.
    run = make_run(
        providers=(make_provider_entry(provider_id=JUDGE_PROVIDER_ID),),
        models=(
            make_model_entry(role=ModelRole.TEST, provider_id=JUDGE_PROVIDER_ID),
            make_model_entry(
                role=ModelRole.EMBEDDING,
                provider_id=DEFAULT_PROVIDER_ID,
                model_name="nomic-embed-text",
            ),
        ),
        settings_snapshot=make_flags_snapshot(phase_cosine_enabled=True),
    )
    inputs = RunDriftDetectionInputs(
        run=run,
        live_providers=(
            make_provider_config(provider_id=JUDGE_PROVIDER_ID),
            make_provider_config(provider_id=DEFAULT_PROVIDER_ID),
        ),
        live_models={
            JUDGE_PROVIDER_ID: ("llama3",),
            DEFAULT_PROVIDER_ID: ("nomic-embed-text",),
        },
        process_environment={},
        readiness=make_readiness_snapshot(
            per_provider=(make_provider_health(provider_id=JUDGE_PROVIDER_ID),)
        ),
        resumable_results=(),
    )
    detector = make_run_drift_detector()

    # Act
    result = detector.detect(inputs)

    # Assert
    embedding_warnings = [w for w in result if w.kind is DriftKind.EMBEDDING_NOW_UNREACHABLE]
    assert len(embedding_warnings) == 1
    assert embedding_warnings[0].severity is DriftSeverity.BLOCKING
    assert embedding_warnings[0].detail == ""
