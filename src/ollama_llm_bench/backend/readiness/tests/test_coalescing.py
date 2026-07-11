"""Tests for coalescing overlapping ``probe_all()`` requests (§6.6, RP-10).

Source of truth: ``docs/v3_specification/11_Services_and_Algorithms/09_READINESS_PROBE.md``
§6.6.
"""

from concurrent.futures import ThreadPoolExecutor
import threading

from ollama_llm_bench.backend.domain import AppReadinessSnapshot, ProviderHealth, ReadinessState
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


class _SlowGatingReadinessLLMClient(FakeReadinessLLMClient):
    """A ``ReadinessLLMClient`` whose ``probe_health`` blocks until released.

    Lets a test hold one batch "in flight" deterministically, so a second
    concurrent ``probe_all()`` call is provably issued while the first is
    still running — no timing-based sleep race.
    """

    def __init__(self, *, health: ProviderHealth, release_gate: threading.Event) -> None:
        super().__init__(health=health, supports_embedding=False, supports_discovery=False)
        self._release_gate = release_gate
        self.probe_started = threading.Event()

    def probe_health(self) -> ProviderHealth:
        """Signal that the probe has started, then block until released."""
        self.probe_started.set()
        self._release_gate.wait(timeout=5.0)
        return super().probe_health()


def test_overlapping_probe_all_calls_coalesce_to_one_batch() -> None:
    """Proves: STORY-016-AC-5

    Covers RP-10. Given a second ``probe_all()`` is issued while the first
    batch is still in flight, when both complete, only one provider-probe
    batch ran, both callers receive the same ``AppReadinessSnapshot``, and
    exactly one ``_app_readiness_changed`` event is emitted.
    """
    # Arrange
    release_gate = threading.Event()
    health = ProviderHealth(
        provider_id=_PROVIDER_ID,
        reachable=True,
        discovery_supported=False,
        model_count=None,
        last_probe_ms=10,
        probed_at=0,
    )
    client = _SlowGatingReadinessLLMClient(health=health, release_gate=release_gate)
    registry = FakeReadinessProviderRegistry(
        enabled=(make_provider_config(provider_id=_PROVIDER_ID),),
        clients={_PROVIDER_ID: client},
    )
    bus = SpyEventBus()
    clock = FakeClock()
    task_runner = ThreadPoolTaskRunner[object](max_workers=4)
    service = make_readiness_service(
        registry=registry,
        embedding_selector=FakeReadinessEmbeddingSelector(),
        settings=FakeSettingsService(),
        gate=FakeInferenceActivityStore(clock=clock, event_bus=bus),
        event_bus=bus,
        task_runner=task_runner,
        clock=clock,
    )

    # Act — the first probe_all() runs on a background thread and blocks
    # mid-batch (the leaf probe is parked on release_gate); once that leaf
    # probe has genuinely started, a second probe_all() is issued from a
    # second caller thread while the first batch is still provably in
    # flight, and only then is the leaf probe released to finish.
    with ThreadPoolExecutor(max_workers=2) as caller_pool:
        first_future = caller_pool.submit(service.probe_all)
        client.probe_started.wait(timeout=5.0)
        second_future = caller_pool.submit(service.probe_all)
        release_gate.set()
        first_result: AppReadinessSnapshot = first_future.result(timeout=5.0)
        second_result: AppReadinessSnapshot = second_future.result(timeout=5.0)

    # Assert
    assert client.probe_health_calls == 1
    assert first_result == second_result
    readiness_events = [e for e in bus.emitted if e[0] == "_app_readiness_changed"]
    assert len(readiness_events) == 1
    # DEGRADED: the sole provider is reachable but no embedding selection was
    # configured — the point under test is the coalescing, not the verdict.
    assert first_result.overall == ReadinessState.DEGRADED
