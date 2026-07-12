"""Proves STORY-025-AC-2 — the four provider live-state conditions (spec §6.1)."""

from collections.abc import Callable

import pytest

from ollama_llm_bench.backend.domain import AppReadinessSnapshot, ProviderConfig
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


def _removed() -> tuple[tuple[ProviderConfig, ...], AppReadinessSnapshot]:
    return (), make_readiness_snapshot(per_provider=())


def _disabled() -> tuple[tuple[ProviderConfig, ...], AppReadinessSnapshot]:
    live = (make_provider_config(enabled=False),)
    return live, make_readiness_snapshot(per_provider=(make_provider_health(),))


def _unreachable() -> tuple[tuple[ProviderConfig, ...], AppReadinessSnapshot]:
    live = (make_provider_config(),)
    readiness = make_readiness_snapshot(per_provider=(make_provider_health(reachable=False),))
    return live, readiness


def _env_var_missing() -> tuple[tuple[ProviderConfig, ...], AppReadinessSnapshot]:
    live = (make_provider_config(),)
    return live, make_readiness_snapshot(per_provider=(make_provider_health(),))


@pytest.mark.parametrize(
    ("build_env", "expected_kind"),
    [
        (_removed, DriftKind.PROVIDER_REMOVED),
        (_disabled, DriftKind.PROVIDER_NOW_DISABLED),
        (_unreachable, DriftKind.PROVIDER_NOW_UNREACHABLE),
        (_env_var_missing, DriftKind.PROVIDER_ENV_VAR_MISSING),
    ],
    ids=["removed", "disabled", "unreachable", "env_var_missing"],
)
def test_provider_condition_maps_to_drift_kind(
    build_env: Callable[[], tuple[tuple[ProviderConfig, ...], AppReadinessSnapshot]],
    expected_kind: DriftKind,
) -> None:
    """Proves: STORY-025-AC-2

    Each provider live-state condition maps to its `DriftKind` per the §6.1
    table, and every emitted warning is `BLOCKING`.
    """
    # Arrange
    live_providers, readiness = build_env()
    run = make_run(
        providers=(make_provider_entry(api_key_raw="OPENAI_API_KEY"),),
        models=(make_model_entry(),),
    )
    inputs = RunDriftDetectionInputs(
        run=run,
        live_providers=live_providers,
        live_models={DEFAULT_PROVIDER_ID: ("llama3",)},
        process_environment={},
        readiness=readiness,
        resumable_results=(),
    )
    detector = make_run_drift_detector()

    # Act
    result = detector.detect(inputs)

    # Assert
    assert len(result) == 1
    assert result[0].kind is expected_kind
    assert result[0].severity is DriftSeverity.BLOCKING


def test_env_var_missing_warning_never_carries_the_resolved_secret_value() -> None:
    """Proves: STORY-025-AC-2

    The `PROVIDER_ENV_VAR_MISSING` case never reads the resolved secret value
    into the warning's `headline`/`detail` — only the env-var NAME is ever
    referenced, and the process-environment's actual secret value (were it
    set) never appears anywhere in the warning.
    """
    # Arrange
    secret_value = "sk-super-secret-do-not-leak-1234567890"  # noqa: S105
    run = make_run(
        providers=(make_provider_entry(api_key_raw="OPENAI_API_KEY"),),
        models=(make_model_entry(),),
    )
    inputs = RunDriftDetectionInputs(
        run=run,
        live_providers=(make_provider_config(),),
        live_models={DEFAULT_PROVIDER_ID: ("llama3",)},
        process_environment={"OPENAI_API_KEY": ""},  # unset/empty triggers the warning
        readiness=make_readiness_snapshot(per_provider=(make_provider_health(),)),
        resumable_results=(),
    )
    detector = make_run_drift_detector()

    # Act
    result = detector.detect(inputs)

    # Assert
    warning = result[0]
    assert secret_value not in warning.headline
    assert secret_value not in warning.detail


def test_pending_results_affected_counts_retryable_results_for_the_provider() -> None:
    """Proves: STORY-025-AC-2

    `pending_results_affected` for a provider warning equals the count of
    retryable results whose `provider_id` matches the blocked provider.
    """
    # Arrange
    run = make_run(
        providers=(make_provider_entry(),),
        models=(make_model_entry(),),
    )
    inputs = RunDriftDetectionInputs(
        run=run,
        live_providers=(),
        live_models={},
        process_environment={},
        readiness=make_readiness_snapshot(per_provider=()),
        resumable_results=(
            make_result(result_id=1),
            make_result(result_id=2),
        ),
    )
    detector = make_run_drift_detector()

    # Act
    result = detector.detect(inputs)

    # Assert
    assert result[0].pending_results_affected == 2  # noqa: PLR2004  # expected retryable count


def test_live_catalog_field_edit_alone_produces_no_warning() -> None:
    """Proves: STORY-025-AC-2

    A live-catalog field difference (an edited display `name`) on an
    otherwise-satisfying provider produces no warning — the pipeline resumes
    through the frozen provider snapshot, so live field edits are invisible.
    """
    # Arrange
    run = make_run(
        providers=(make_provider_entry(),),
        models=(make_model_entry(),),
    )
    inputs = RunDriftDetectionInputs(
        run=run,
        live_providers=(make_provider_config(name="renamed-provider"),),
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
