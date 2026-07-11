"""Tests for the one-provider probe path (§6.2) — timeout collapse and the missing-client case.

Source of truth: ``docs/v3_specification/11_Services_and_Algorithms/09_READINESS_PROBE.md``
§6.2, §7, §8, RP-08, RP-09.
"""

import threading

from ollama_llm_bench.backend.domain import ProviderHealth
from ollama_llm_bench.backend.readiness.api import make_readiness_service
from ollama_llm_bench.backend.readiness.tests.conftest import (
    FakeClock,
    FakeReadinessEmbeddingSelector,
    FakeReadinessLLMClient,
    FakeReadinessProviderRegistry,
    SpyEventBus,
    ThreadPoolTaskRunner,
    make_provider_config,
)
from ollama_llm_bench.backend.settings.testing import FakeSettingsService
from ollama_llm_bench.backend.stores.inference_activity.testing import FakeInferenceActivityStore

_PROVIDER_ID = "a3b8c1d2-7f04-4b8e-9c1d-2e5f0a1b3c4d"
_MISSING_PROVIDER_ID = "b4c9d2e3-8015-4c9f-ad2e-3f6a1b2c4d5e"
_SHORT_PROBE_TIMEOUT_MS = "50"
_SLOW_PROBE_BLOCK_S = 2.0


class _SlowReadinessLLMClient(FakeReadinessLLMClient):
    """A ``ReadinessLLMClient`` whose ``probe_health`` blocks longer than the configured timeout.

    Bounded (not infinite) so the underlying worker thread always finishes
    and the test process can exit cleanly even though the *caller* gives up
    on it much sooner via ``Future.result(timeout=...)``.
    """

    def probe_health(self) -> ProviderHealth:
        """Block past the configured probe timeout, then return the canned health."""
        threading.Event().wait(timeout=_SLOW_PROBE_BLOCK_S)
        return super().probe_health()


def test_provider_probe_exceeding_timeout_collapses_to_unreachable() -> None:
    """Proves: STORY-016-AC-2

    Covers RP-08. A provider whose leaf probe exceeds ``provider.probe_timeout_ms`` is
    reported ``reachable=False`` by the batch orchestration itself (the
    ``Future.result(timeout=...)`` collapse), and ``probe_all`` still
    completes with no exception escaping.
    """
    # Arrange
    client = _SlowReadinessLLMClient(health=_placeholder_health())
    registry = FakeReadinessProviderRegistry(
        enabled=(make_provider_config(provider_id=_PROVIDER_ID),),
        clients={_PROVIDER_ID: client},
    )
    bus = SpyEventBus()
    clock = FakeClock()
    settings = FakeSettingsService(
        initial_values={"provider.probe_timeout_ms": _SHORT_PROBE_TIMEOUT_MS}
    )
    task_runner = ThreadPoolTaskRunner[object](max_workers=4)
    service = make_readiness_service(
        registry=registry,
        embedding_selector=FakeReadinessEmbeddingSelector(),
        settings=settings,
        gate=FakeInferenceActivityStore(clock=clock, event_bus=bus),
        event_bus=bus,
        task_runner=task_runner,
        clock=clock,
    )

    # Act
    snapshot = service.probe_all()

    # Assert
    assert len(snapshot.per_provider) == 1
    assert snapshot.per_provider[0].reachable is False
    assert snapshot.per_provider[0].last_error is not None


def _placeholder_health() -> ProviderHealth:
    """A ``ProviderHealth`` value never actually returned in the timeout test."""
    return ProviderHealth(
        provider_id=_PROVIDER_ID,
        reachable=True,
        discovery_supported=False,
        model_count=None,
        last_probe_ms=10,
        probed_at=0,
    )


def test_enabled_provider_with_no_client_reports_missing_env_with_no_network_call() -> None:
    """Proves: STORY-016-AC-3

    Covers RP-09. An enabled provider whose api-key env-var name does not resolve has no
    client in the registry; ``probe`` catches ``ConfigurationError`` and
    reports ``reachable=False`` with a missing-environment-variable error,
    with no attempt to call anything client-shaped (the fake registry
    returns no client at all for this provider).
    """
    # Arrange
    registry = FakeReadinessProviderRegistry(
        enabled=(make_provider_config(provider_id=_MISSING_PROVIDER_ID),),
        clients={},
    )
    bus = SpyEventBus()
    clock = FakeClock()
    service = make_readiness_service(
        registry=registry,
        embedding_selector=FakeReadinessEmbeddingSelector(),
        settings=FakeSettingsService(),
        gate=FakeInferenceActivityStore(clock=clock, event_bus=bus),
        event_bus=bus,
        task_runner=ThreadPoolTaskRunner[object](max_workers=4),
        clock=clock,
    )

    # Act
    health = service.probe(_MISSING_PROVIDER_ID)

    # Assert
    assert health.reachable is False
    assert health.last_error == "missing environment variable"
