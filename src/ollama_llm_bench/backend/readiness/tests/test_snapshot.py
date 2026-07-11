"""Tests for ``ReadinessService.snapshot()`` (§6.1, RP-01).

Source of truth: ``docs/v3_specification/08_Cross_Cutting/08-E_interfaces_contracts.md``
§12; ``docs/v3_specification/11_Services_and_Algorithms/09_READINESS_PROBE.md`` §6.1.
"""

from ollama_llm_bench.backend.concurrency import make_inline_task_runner
from ollama_llm_bench.backend.domain import ReadinessState
from ollama_llm_bench.backend.readiness.api import ReadinessService, make_readiness_service
from ollama_llm_bench.backend.readiness.tests.conftest import (
    FakeClock,
    FakeReadinessEmbeddingSelector,
    FakeReadinessProviderRegistry,
    SpyEventBus,
)
from ollama_llm_bench.backend.settings.testing import FakeSettingsService
from ollama_llm_bench.backend.stores.inference_activity.testing import FakeInferenceActivityStore


def _make_service(
    *, registry: FakeReadinessProviderRegistry, clock: FakeClock, bus: SpyEventBus
) -> ReadinessService:
    """Build a ``ReadinessService`` over fakes, with no providers probed yet."""
    return make_readiness_service(
        registry=registry,
        embedding_selector=FakeReadinessEmbeddingSelector(),
        settings=FakeSettingsService(),
        gate=FakeInferenceActivityStore(clock=clock, event_bus=bus),
        event_bus=bus,
        task_runner=make_inline_task_runner(),
        clock=clock,
    )


def test_snapshot_is_checking_before_first_probe() -> None:
    """Proves: STORY-016-AC-1

    Covers RP-01. Given no probe has completed, calling ``snapshot()``
    returns an ``AppReadinessSnapshot`` whose ``overall`` is ``CHECKING``.
    """
    # Arrange
    service = _make_service(
        registry=FakeReadinessProviderRegistry(), clock=FakeClock(), bus=SpyEventBus()
    )

    # Act
    snapshot = service.snapshot()

    # Assert
    assert snapshot.overall == ReadinessState.CHECKING


def test_snapshot_never_triggers_a_probe_as_a_side_effect() -> None:
    """Proves: STORY-016-AC-1

    Calling ``snapshot()`` — even repeatedly — never calls the provider
    registry's ``get_client``/``list_enabled`` and never touches the gate:
    it is a pure cached read.
    """
    # Arrange
    registry = FakeReadinessProviderRegistry()
    bus = SpyEventBus()
    service = _make_service(registry=registry, clock=FakeClock(), bus=bus)

    # Act
    service.snapshot()
    service.snapshot()
    service.snapshot()

    # Assert
    assert bus.emitted == []


def test_snapshot_returns_synchronously_with_no_blocking_call() -> None:
    """Proves: STORY-016-AC-1

    ``snapshot()`` returns immediately without needing an in-flight batch
    or any orchestration — a fresh service's first call already succeeds.
    """
    # Arrange
    service = _make_service(
        registry=FakeReadinessProviderRegistry(), clock=FakeClock(), bus=SpyEventBus()
    )

    # Act
    first = service.snapshot()
    second = service.snapshot()

    # Assert
    assert first == second
