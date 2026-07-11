"""Tests that ``probe``/``probe_all`` collapse an arbitrary leaf-probe failure into data.

Source of truth: ``docs/v3_specification/11_Services_and_Algorithms/09_READINESS_PROBE.md``
§8 (Error handling) — "Neither `probe_all`, `probe`, nor `snapshot` ever raises."
"""

from ollama_llm_bench.backend.concurrency import make_inline_task_runner
from ollama_llm_bench.backend.domain import ProviderHealth
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


class _RaisingReadinessLLMClient(FakeReadinessLLMClient):
    """A ``ReadinessLLMClient`` whose ``probe_health`` always raises an arbitrary exception."""

    def probe_health(self) -> ProviderHealth:
        """Simulate an unexpected failure inside the leaf probe."""
        raise RuntimeError("simulated leaf-probe failure")


def _make_service_with_raising_client() -> object:
    """Build a ``ReadinessService`` whose sole provider's client always raises."""
    client = _RaisingReadinessLLMClient(
        health=ProviderHealth(
            provider_id=_PROVIDER_ID,
            reachable=True,
            discovery_supported=False,
            model_count=None,
            last_probe_ms=10,
            probed_at=0,
        )
    )
    registry = FakeReadinessProviderRegistry(
        enabled=(make_provider_config(provider_id=_PROVIDER_ID),),
        clients={_PROVIDER_ID: client},
    )
    bus = SpyEventBus()
    clock = FakeClock()
    return make_readiness_service(
        registry=registry,
        embedding_selector=FakeReadinessEmbeddingSelector(),
        settings=FakeSettingsService(),
        gate=FakeInferenceActivityStore(clock=clock, event_bus=bus),
        event_bus=bus,
        task_runner=make_inline_task_runner(),
        clock=clock,
    )


def test_probe_collapses_an_arbitrary_leaf_exception_to_unreachable_health() -> None:
    """Proves: STORY-016-AC-7

    The story text and the ``ReadinessService`` docstrings both assert
    ``probe`` "never raises" for ANY leaf-probe failure. An arbitrary
    exception raised by ``client.probe_health()`` itself — not just a
    ``ConfigurationError`` from ``get_client`` — must be collapsed into an
    unreachable-shaped ``ProviderHealth`` rather than propagating.
    """
    # Arrange
    service = _make_service_with_raising_client()

    # Act
    health = service.probe(_PROVIDER_ID)  # type: ignore[attr-defined]

    # Assert
    assert health.reachable is False
    assert health.last_error is not None


def test_probe_all_collapses_an_arbitrary_leaf_exception_to_unreachable_snapshot() -> None:
    """Proves: STORY-016-AC-2

    The per-provider leaf unit submitted inside ``_fan_out_health_probes``
    calls ``self._probe_one`` directly; an arbitrary exception raised by
    ``client.probe_health()`` must be collapsed into unreachable
    ``ProviderHealth`` data rather than propagating out of ``probe_all()``,
    per the "never raises" contract in ``09_READINESS_PROBE.md`` §5/§8.
    """
    # Arrange
    service = _make_service_with_raising_client()

    # Act
    snapshot = service.probe_all()  # type: ignore[attr-defined]

    # Assert
    assert len(snapshot.per_provider) == 1
    assert snapshot.per_provider[0].reachable is False
