"""Table-driven aggregation tests for ``backend/readiness/_internal/aggregation.py``.

Source of truth: ``docs/v3_specification/11_Services_and_Algorithms/09_READINESS_PROBE.md``
§6.5 (Aggregation into the overall verdict).
"""

import pytest

from ollama_llm_bench.backend.domain import ProviderHealth, ReadinessState
from ollama_llm_bench.backend.readiness._internal.aggregation import aggregate

_PROVIDER_A = "a3b8c1d2-7f04-4b8e-9c1d-2e5f0a1b3c4d"
_PROVIDER_B = "b4c9d2e3-8015-4c9f-ad2e-3f6a1b2c4d5e"


def _health(
    provider_id: str,
    *,
    reachable: bool,
    discovery_supported: bool = True,
    model_count: int | None = 1,
) -> ProviderHealth:
    """Build a minimal, otherwise-arbitrary ``ProviderHealth`` row."""
    return ProviderHealth(
        provider_id=provider_id,
        reachable=reachable,
        discovery_supported=discovery_supported,
        model_count=model_count,
        last_probe_ms=10,
        probed_at=0,
    )


@pytest.mark.parametrize(
    ("health_results", "embedding_ok", "expected_overall"),
    [
        pytest.param((), False, ReadinessState.NOT_READY, id="zero_enabled_providers"),
        pytest.param((), True, ReadinessState.NOT_READY, id="zero_enabled_providers_embedding_any"),
        pytest.param(
            (_health(_PROVIDER_A, reachable=False),),
            False,
            ReadinessState.NOT_READY,
            id="one_enabled_none_reachable",
        ),
        pytest.param(
            (_health(_PROVIDER_A, reachable=False), _health(_PROVIDER_B, reachable=False)),
            True,
            ReadinessState.NOT_READY,
            id="two_enabled_none_reachable_embedding_any",
        ),
        pytest.param(
            (_health(_PROVIDER_A, reachable=True),),
            True,
            ReadinessState.READY,
            id="all_reachable_embedding_ok",
        ),
        pytest.param(
            (_health(_PROVIDER_A, reachable=True), _health(_PROVIDER_B, reachable=True)),
            True,
            ReadinessState.READY,
            id="all_reachable_multi_embedding_ok",
        ),
        pytest.param(
            (_health(_PROVIDER_A, reachable=True),),
            False,
            ReadinessState.DEGRADED,
            id="all_reachable_embedding_not_ok",
        ),
        pytest.param(
            (_health(_PROVIDER_A, reachable=True), _health(_PROVIDER_B, reachable=False)),
            True,
            ReadinessState.DEGRADED,
            id="partially_reachable_embedding_ok",
        ),
        pytest.param(
            (_health(_PROVIDER_A, reachable=True), _health(_PROVIDER_B, reachable=False)),
            False,
            ReadinessState.DEGRADED,
            id="partially_reachable_embedding_not_ok",
        ),
    ],
)
def test_overall_state_folds_provider_and_embedding_results(
    health_results: tuple[ProviderHealth, ...],
    *,
    embedding_ok: bool,
    expected_overall: ReadinessState,
) -> None:
    """Proves: STORY-016-AC-2

    The full §6.5 aggregation table: zero enabled providers and every-provider-
    unreachable both fold to ``NOT_READY``; all reachable with the embedding ok
    folds to ``READY``; all reachable with the embedding not ok, and any
    partially-reachable mix (regardless of the embedding result), fold to
    ``DEGRADED``.
    """
    # Act
    snapshot = aggregate(health_results, embedding_ok=embedding_ok)

    # Assert
    assert snapshot.overall == expected_overall


@pytest.mark.parametrize(
    ("reachable", "discovery_supported", "model_count", "counts_healthy"),
    [
        pytest.param(True, True, 1, True, id="reachable_discovery_supported_models_gt_0"),
        pytest.param(
            True, False, None, True, id="reachable_discovery_not_supported_anthropic_style"
        ),
        pytest.param(True, True, 0, True, id="reachable_discovery_supported_zero_models"),
        pytest.param(
            True, True, None, True, id="reachable_discovery_supported_listing_call_failed"
        ),
        pytest.param(False, True, None, False, id="unreachable_refused_auth_or_deadline"),
        pytest.param(False, False, None, False, id="enabled_but_env_var_unresolved"),
    ],
)
def test_provider_condition_maps_to_health_and_healthy_count(
    *,
    reachable: bool,
    discovery_supported: bool,
    model_count: int | None,
    counts_healthy: bool,
) -> None:
    """Proves: STORY-016-AC-3

    Every provider condition from the §6.5/§6.2 condition table maps to the
    correct healthy-count contribution: a provider counts as healthy purely
    on ``reachable``, regardless of ``discovery_supported`` or ``model_count``
    (the Anthropic-shaped no-discovery case, the zero-models case, and the
    failed-listing case are all still healthy when reachable).
    """
    # Arrange
    health = _health(
        _PROVIDER_A,
        reachable=reachable,
        discovery_supported=discovery_supported,
        model_count=model_count,
    )

    # Act
    snapshot = aggregate((health,), embedding_ok=True)

    # Assert
    expected_overall = ReadinessState.READY if counts_healthy else ReadinessState.NOT_READY
    assert snapshot.overall == expected_overall
