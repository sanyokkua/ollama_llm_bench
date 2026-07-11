"""Tests for ``_app_readiness_changed`` change-detection emission (§6.5, §8, RP-11).

Source of truth: ``docs/v3_specification/11_Services_and_Algorithms/09_READINESS_PROBE.md``
§6.4, §6.5.
"""

from ollama_llm_bench.backend.concurrency import make_inline_task_runner
from ollama_llm_bench.backend.domain import ProviderHealth
from ollama_llm_bench.backend.events import SIGNAL_APP_READINESS_CHANGED
from ollama_llm_bench.backend.readiness.api import make_readiness_service
from ollama_llm_bench.backend.readiness.tests.conftest import (
    FakeClock,
    FakeReadinessEmbeddingSelector,
    FakeReadinessLLMClient,
    FakeReadinessProviderRegistry,
    SpyEventBus,
    make_provider_config,
)
from ollama_llm_bench.backend.settings.testing import FakeSettingsService
from ollama_llm_bench.backend.stores.inference_activity.testing import FakeInferenceActivityStore

_PROVIDER_ID = "a3b8c1d2-7f04-4b8e-9c1d-2e5f0a1b3c4d"
_EXPECTED_EVENT_COUNT_AFTER_CHANGE = 2


class _MutableHealthReadinessLLMClient(FakeReadinessLLMClient):
    """A ``ReadinessLLMClient`` double whose canned health can be swapped between probes."""

    def set_health(self, health: ProviderHealth) -> None:
        """Replace the health this client's next ``probe_health()`` call returns."""
        self._health = health


def _reachable_health() -> ProviderHealth:
    """A minimal reachable ``ProviderHealth`` row for the fixed test provider."""
    return ProviderHealth(
        provider_id=_PROVIDER_ID,
        reachable=True,
        discovery_supported=False,
        model_count=None,
        last_probe_ms=10,
        probed_at=0,
    )


def _readiness_event_count(bus: SpyEventBus) -> int:
    """Count emissions on the ``_app_readiness_changed`` signal."""
    return sum(1 for name, _ in bus.emitted if name == SIGNAL_APP_READINESS_CHANGED)


def test_event_emitted_only_on_snapshot_change() -> None:
    """Proves: STORY-016-AC-6

    Covers RP-11. The first ``probe_all()`` recomputes a snapshot that
    differs from the ``CHECKING`` cached one, so it emits exactly one
    ``_app_readiness_changed`` event; a second ``probe_all()`` recomputing
    the identical snapshot emits none.
    """
    # Arrange
    client = FakeReadinessLLMClient(health=_reachable_health())
    registry = FakeReadinessProviderRegistry(
        enabled=(make_provider_config(provider_id=_PROVIDER_ID),),
        clients={_PROVIDER_ID: client},
    )
    bus = SpyEventBus()
    clock = FakeClock()
    service = make_readiness_service(
        registry=registry,
        embedding_selector=FakeReadinessEmbeddingSelector(),
        settings=FakeSettingsService(),
        gate=FakeInferenceActivityStore(clock=clock, event_bus=bus),
        event_bus=bus,
        task_runner=make_inline_task_runner(),
        clock=clock,
    )

    # Act
    service.probe_all()
    count_after_first = _readiness_event_count(bus)
    service.probe_all()
    count_after_second = _readiness_event_count(bus)

    # Assert
    assert count_after_first == 1
    assert count_after_second == 1


def test_event_emitted_again_when_snapshot_differs() -> None:
    """Proves: STORY-016-AC-6

    Given a recomputed snapshot that differs from the cached one — the
    provider having gone from reachable to unreachable between two
    ``probe_all()`` calls — exactly one more event is emitted for the
    change.
    """
    # Arrange
    client = _MutableHealthReadinessLLMClient(health=_reachable_health())
    registry = FakeReadinessProviderRegistry(
        enabled=(make_provider_config(provider_id=_PROVIDER_ID),),
        clients={_PROVIDER_ID: client},
    )
    bus = SpyEventBus()
    clock = FakeClock()
    service = make_readiness_service(
        registry=registry,
        embedding_selector=FakeReadinessEmbeddingSelector(),
        settings=FakeSettingsService(),
        gate=FakeInferenceActivityStore(clock=clock, event_bus=bus),
        event_bus=bus,
        task_runner=make_inline_task_runner(),
        clock=clock,
    )
    service.probe_all()
    assert _readiness_event_count(bus) == 1

    # Act — the provider goes unreachable, changing the aggregate result
    client.set_health(
        ProviderHealth(
            provider_id=_PROVIDER_ID,
            reachable=False,
            discovery_supported=False,
            model_count=None,
            last_probe_ms=10,
            probed_at=0,
        )
    )
    service.probe_all()

    # Assert
    assert _readiness_event_count(bus) == _EXPECTED_EVENT_COUNT_AFTER_CHANGE
