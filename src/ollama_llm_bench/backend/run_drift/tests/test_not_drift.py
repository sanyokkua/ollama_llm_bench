"""Proves STORY-025-AC-5 — live-selection and settings differences are NOT drift (DD-57, spec §6.4, §6.5)."""

from ollama_llm_bench.backend.domain import ModelRole
from ollama_llm_bench.backend.run_drift import RunDriftDetectionInputs, make_run_drift_detector
from ollama_llm_bench.backend.run_drift.tests.conftest import (
    DEFAULT_PROVIDER_ID,
    make_flags_snapshot,
    make_model_entry,
    make_provider_config,
    make_provider_entry,
    make_provider_health,
    make_readiness_snapshot,
    make_run,
    make_setting_entry,
)


def test_live_embedding_selection_change_is_not_drift() -> None:
    """Proves: STORY-025-AC-5

    Given a live embedding selection that differs from the run's frozen
    `EMBEDDING`-role pair while the frozen pair itself is still available and
    reachable, when the cosine phase is enabled, then no embedding warning is
    emitted — the resumed cosine phase uses the frozen pair, so a
    live-selection change is not drift (DD-57).

    The detector's inputs carry no live-embedding-selection field at all
    (`RunDriftDetectionInputs` has no such input) — this test proves that
    fact behaviourally: `live_models` for the frozen pair's provider lists
    both the frozen model and a different "currently live-selected" model,
    and only the frozen pair's availability is what matters.
    """
    # Arrange
    run = make_run(
        providers=(make_provider_entry(),),
        models=(
            make_model_entry(role=ModelRole.TEST),
            make_model_entry(role=ModelRole.EMBEDDING, model_name="nomic-embed-text"),
        ),
        settings_snapshot=make_flags_snapshot(phase_cosine_enabled=True),
    )
    inputs = RunDriftDetectionInputs(
        run=run,
        live_providers=(make_provider_config(),),
        # The live catalog still advertises the frozen embedding model,
        # alongside some other model the user may have live-selected instead.
        live_models={DEFAULT_PROVIDER_ID: ("llama3", "nomic-embed-text", "a-different-embedder")},
        process_environment={},
        readiness=make_readiness_snapshot(per_provider=(make_provider_health(),)),
        resumable_results=(),
    )
    detector = make_run_drift_detector()

    # Act
    result = detector.detect(inputs)

    # Assert
    assert result == ()


def test_settings_value_differing_from_current_default_is_not_drift() -> None:
    """Proves: STORY-025-AC-5

    Given a snapshot key that differs from the current default or
    user-saved value, no warning of any kind is emitted — there is no
    settings-difference check in this module at all (DD-57); the run resumes
    on its frozen snapshot regardless of live settings.
    """
    # Arrange: a fully-satisfied environment, but the frozen snapshot carries
    # an arbitrary setting value ("benchmark.retry_count") that would differ
    # from any live default/user-saved value. No live "current settings"
    # input even exists for the detector to compare against.
    run = make_run(
        providers=(make_provider_entry(),),
        models=(make_model_entry(),),
        settings_snapshot=(
            *make_flags_snapshot(),
            make_setting_entry(setting_key="benchmark.retry_count", setting_value="99"),
        ),
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
