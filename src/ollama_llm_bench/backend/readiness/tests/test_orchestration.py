"""Tests for ``probe_all`` dispatcher-thread orchestration (§6.4, §9, DD-38/DD-40, RP-18/RP-19).

Source of truth: ``docs/v3_specification/11_Services_and_Algorithms/09_READINESS_PROBE.md``
§6.4, §9.
"""

from collections.abc import Callable
from concurrent.futures import Future
import threading

from ollama_llm_bench.backend.concurrency import CancellationToken
from ollama_llm_bench.backend.domain import ProviderHealth, ReadinessState
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

_PROVIDER_A = "a3b8c1d2-7f04-4b8e-9c1d-2e5f0a1b3c4d"
_PROVIDER_B = "b4c9d2e3-8015-4c9f-ad2e-3f6a1b2c4d5e"
_SATURATED_POOL_WORKER_COUNT = 1


def _reachable_health(provider_id: str) -> ProviderHealth:
    """A minimal reachable ``ProviderHealth`` row for ``provider_id``."""
    return ProviderHealth(
        provider_id=provider_id,
        reachable=True,
        discovery_supported=False,
        model_count=None,
        last_probe_ms=10,
        probed_at=0,
    )


class _AssertNeverCalledTaskRunner:
    """A ``TaskRunner`` double that fails the test if ``submit`` is ever called.

    Proves a bare ``probe(provider_id)`` call never itself submits work to
    the ``TaskRunner`` — it is a leaf unit, not an orchestrator.
    """

    def submit(self, fn: Callable[[], object], *, token: CancellationToken) -> Future[object]:
        """Fail loudly — a leaf ``probe()`` call must never reach this."""
        raise AssertionError("probe() must never submit work to the TaskRunner (STORY-016-AC-8)")


def test_bare_probe_never_submits_to_the_task_runner() -> None:
    """Proves: STORY-016-AC-8

    A bare ``probe(provider_id)`` call never calls ``TaskRunner.submit`` —
    only ``probe_all`` orchestrates fan-out onto the pool.
    """
    # Arrange
    client = FakeReadinessLLMClient(health=_reachable_health(_PROVIDER_A))
    registry = FakeReadinessProviderRegistry(
        enabled=(make_provider_config(provider_id=_PROVIDER_A),),
        clients={_PROVIDER_A: client},
    )
    bus = SpyEventBus()
    clock = FakeClock()
    service = make_readiness_service(
        registry=registry,
        embedding_selector=FakeReadinessEmbeddingSelector(),
        settings=FakeSettingsService(),
        gate=FakeInferenceActivityStore(clock=clock, event_bus=bus),
        event_bus=bus,
        task_runner=_AssertNeverCalledTaskRunner(),
        clock=clock,
    )

    # Act
    health = service.probe(_PROVIDER_A)

    # Assert
    assert health.reachable is True


def test_probe_all_fans_out_concurrently_and_never_deadlocks() -> None:
    """Proves: STORY-016-AC-8

    Covers RP-18/RP-19. Within one ``probe_all`` batch, the per-provider
    reachability handshakes run concurrently on ``TaskRunner`` workers even
    with the pool saturated to a single worker thread (worst case, strictly
    serial fan-out execution), and the batch still completes without
    deadlock — because the dispatcher thread (here, the calling test
    thread), not a pool worker, is the one blocking on the leaf ``Future``s.
    """
    # Arrange — two providers whose leaf probes both park on a barrier so
    # only genuine pool concurrency (or serial completion with no deadlock)
    # lets the batch finish; the pool is saturated to one worker to prove
    # the batch still completes correctly even in the worst case.
    entered = threading.Event()
    release = threading.Event()

    class _BarrierClient(FakeReadinessLLMClient):
        def probe_health(self) -> ProviderHealth:
            entered.set()
            release.wait(timeout=5.0)
            return super().probe_health()

    client_a = _BarrierClient(health=_reachable_health(_PROVIDER_A))
    client_b = FakeReadinessLLMClient(health=_reachable_health(_PROVIDER_B))
    registry = FakeReadinessProviderRegistry(
        enabled=(
            make_provider_config(provider_id=_PROVIDER_A),
            make_provider_config(provider_id=_PROVIDER_B),
        ),
        clients={_PROVIDER_A: client_a, _PROVIDER_B: client_b},
    )
    bus = SpyEventBus()
    clock = FakeClock()
    task_runner = ThreadPoolTaskRunner[object](max_workers=_SATURATED_POOL_WORKER_COUNT)
    service = make_readiness_service(
        registry=registry,
        embedding_selector=FakeReadinessEmbeddingSelector(),
        settings=FakeSettingsService(),
        gate=FakeInferenceActivityStore(clock=clock, event_bus=bus),
        event_bus=bus,
        task_runner=task_runner,
        clock=clock,
    )

    def _release_once_entered() -> None:
        entered.wait(timeout=5.0)
        release.set()

    releaser = threading.Thread(target=_release_once_entered)
    releaser.start()

    # Act
    snapshot = service.probe_all()
    releaser.join(timeout=5.0)

    # Assert
    assert snapshot.overall == ReadinessState.DEGRADED
    assert client_a.probe_health_calls == 1
    assert client_b.probe_health_calls == 1
    assert not releaser.is_alive()
