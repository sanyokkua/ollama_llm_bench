"""Tests for ``ReadinessService.record_embedding_capability_result`` (STORY-110-AC-10).

Source of truth: ``docs/v3_specification/08_Cross_Cutting/08-E_interfaces_contracts.md``
§12 (Readiness Service); ``docs/v3_specification/11_Services_and_Algorithms/
09_READINESS_PROBE.md`` §6.5 (aggregation); ``docs/v3_specification/
11_Services_and_Algorithms/06_EMBEDDING_SERVICE.md`` §6.6a (the billable Test-Embedding
capability check).

``SettingsGateway.probe_embedding()`` (``adapters/ui_gateways/``) runs the real, billable
``embed("probe")`` call and reports its outcome here -- a stronger signal than the free
handshake-only check ``probe_all`` runs on its own (``09_READINESS_PROBE.md`` §6.3). This
method is what lets that stronger signal actually reach a later ``snapshot()`` read (e.g.
the New Benchmark widget's ``GRADED``-mode gate, ``08-J`` §5.7).
"""

from ollama_llm_bench.backend.concurrency import make_inline_task_runner
from ollama_llm_bench.backend.domain import ProviderHealth, ReadinessState
from ollama_llm_bench.backend.events import SIGNAL_APP_READINESS_CHANGED
from ollama_llm_bench.backend.readiness.api import make_readiness_service
from ollama_llm_bench.backend.readiness.protocols import ReadinessService
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

_PROVIDER_ID = "c5d0e3f4-9126-4dab-be3f-4a7b2c3d5e6f"


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


def _make_service(*, bus: SpyEventBus, clock: FakeClock) -> ReadinessService:
    """A ``ReadinessService`` over one reachable provider and no embedding selection."""
    client = FakeReadinessLLMClient(health=_reachable_health())
    registry = FakeReadinessProviderRegistry(
        enabled=(make_provider_config(provider_id=_PROVIDER_ID),),
        clients={_PROVIDER_ID: client},
    )
    return make_readiness_service(
        registry=registry,
        embedding_selector=FakeReadinessEmbeddingSelector(),
        settings=FakeSettingsService(),
        gate=FakeInferenceActivityStore(clock=clock, event_bus=bus),
        event_bus=bus,
        task_runner=make_inline_task_runner(),
        clock=clock,
    )


def test_record_embedding_capability_result_updates_the_cached_snapshot() -> None:
    """Proves: STORY-110-AC-10

    Given a cached snapshot from ``probe_all()`` (one reachable provider, no
    embedding selection so ``embedding_reachable`` starts ``False`` and
    ``overall`` is ``DEGRADED``), when ``record_embedding_capability_result
    (reachable=True)`` is called, then the held snapshot's
    ``embedding_reachable`` field becomes ``True`` and ``overall`` recomputes
    to ``READY`` through the same aggregation fold ``probe_all`` uses --
    without re-probing any provider.
    """
    # Arrange
    bus = SpyEventBus()
    clock = FakeClock()
    service = _make_service(bus=bus, clock=clock)
    service.probe_all()
    before = service.snapshot()
    assert before.embedding_reachable is False
    assert before.overall == ReadinessState.DEGRADED

    # Act
    service.record_embedding_capability_result(reachable=True)

    # Assert
    after = service.snapshot()
    assert after.embedding_reachable is True
    assert after.overall == ReadinessState.READY
    assert after.per_provider == before.per_provider


def test_record_embedding_capability_result_emits_only_on_a_real_change() -> None:
    """Proves: STORY-110-AC-10

    Reuses the same change-detection emission path ``probe_all`` uses
    (RP-11): recording an unchanged ``embedding_reachable`` value emits no
    further ``_app_readiness_changed`` event, but recording a value that
    actually differs emits exactly one more.
    """
    # Arrange
    bus = SpyEventBus()
    clock = FakeClock()
    service = _make_service(bus=bus, clock=clock)
    service.probe_all()
    count_after_probe = _readiness_event_count(bus)

    # Act -- unchanged: probe_all already cached embedding_reachable=False
    service.record_embedding_capability_result(reachable=False)
    count_after_noop = _readiness_event_count(bus)

    # Act -- a real change
    service.record_embedding_capability_result(reachable=True)
    count_after_change = _readiness_event_count(bus)

    # Assert
    assert count_after_noop == count_after_probe
    assert count_after_change == count_after_probe + 1


def _readiness_event_count(bus: SpyEventBus) -> int:
    """Count emissions on the ``_app_readiness_changed`` signal."""
    return sum(1 for name, _ in bus.emitted if name == SIGNAL_APP_READINESS_CHANGED)
