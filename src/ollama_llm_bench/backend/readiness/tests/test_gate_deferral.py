"""Tests for single-inference-gate deferral (§9, EC-RUN-13).

Source of truth: ``docs/v3_specification/11_Services_and_Algorithms/09_READINESS_PROBE.md``
§9; ``docs/v3_specification/08_Cross_Cutting/08-I_edge_cases.md`` EC-RUN-13.
"""

from ollama_llm_bench.backend.concurrency import make_inline_task_runner
from ollama_llm_bench.backend.domain import (
    GateLease,
    InferenceActivity,
    InferenceActivityContext,
    InferenceActivityState,
    ProviderHealth,
)
from ollama_llm_bench.backend.readiness.api import ReadinessService, make_readiness_service
from ollama_llm_bench.backend.readiness.tests.conftest import (
    FakeClock,
    FakeReadinessEmbeddingSelector,
    FakeReadinessLLMClient,
    FakeReadinessProviderRegistry,
    SpyEventBus,
    make_provider_config,
)
from ollama_llm_bench.backend.settings.testing import FakeSettingsService

_PROVIDER_ID = "a3b8c1d2-7f04-4b8e-9c1d-2e5f0a1b3c4d"
_EXPECTED_TRY_ACQUIRE_CALLS_ON_RETRY = 2


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


class _RefuseOnceThenIdleGate:
    """A gate double refusing the first acquire, then granting every later one.

    Simulates ``BENCHMARK_RUN`` holding the gate at the moment a readiness
    probe is requested (EC-RUN-13): the run finishes and the gate goes
    ``IDLE`` before the service's one deferred retry.
    """

    def __init__(self) -> None:
        self.try_acquire_calls = 0
        self.released_leases: list[GateLease] = []
        self._lease_counter = 0

    def try_acquire(
        self, activity: InferenceActivity, context: InferenceActivityContext
    ) -> GateLease | None:
        """Refuse exactly the first call; grant every subsequent one."""
        self.try_acquire_calls += 1
        if self.try_acquire_calls == 1:
            return None
        self._lease_counter += 1
        return GateLease(activity=activity, lease_id=self._lease_counter, acquired_at=0)

    def release(self, lease: GateLease) -> None:
        """Record the released lease."""
        self.released_leases.append(lease)

    def state(self) -> InferenceActivityState:
        """Report ``IDLE`` — irrelevant to this double; only ``is_busy`` is polled."""
        return InferenceActivityState(current=InferenceActivity.IDLE, context=None)

    def is_busy(self) -> bool:
        """Report ``IDLE`` (not busy) from the very first poll, so the retry proceeds fast."""
        return False


class _AlwaysRefusingGate:
    """A gate double that refuses every acquire attempt and never goes idle."""

    def __init__(self) -> None:
        self.try_acquire_calls = 0

    def try_acquire(
        self, activity: InferenceActivity, context: InferenceActivityContext
    ) -> GateLease | None:
        """Always refuse."""
        self.try_acquire_calls += 1
        return None

    def release(self, lease: GateLease) -> None:
        """Never called in this scenario; present only to satisfy the Protocol shape."""
        raise AssertionError("release must not be called when acquisition never succeeds")

    def state(self) -> InferenceActivityState:
        """Report ``BENCHMARK_RUN`` still holding the gate."""
        return InferenceActivityState(
            current=InferenceActivity.BENCHMARK_RUN,
            context=InferenceActivityContext(
                activity=InferenceActivity.BENCHMARK_RUN, started_at=0
            ),
        )

    def is_busy(self) -> bool:
        """Report perpetually busy."""
        return True


class _RaisingReadinessLLMClient(FakeReadinessLLMClient):
    """A ``ReadinessLLMClient`` whose ``probe_health`` always raises an arbitrary exception."""

    def probe_health(self) -> ProviderHealth:
        """Simulate an unexpected failure inside the leaf probe."""
        raise RuntimeError("simulated leaf-probe failure")


def _make_service_with_gate(*, gate: object, client: FakeReadinessLLMClient) -> ReadinessService:
    """Build a ``ReadinessService`` with one provider client, over a custom gate double."""
    registry = FakeReadinessProviderRegistry(
        enabled=(make_provider_config(provider_id=_PROVIDER_ID),),
        clients={_PROVIDER_ID: client},
    )
    return make_readiness_service(
        registry=registry,
        embedding_selector=FakeReadinessEmbeddingSelector(),
        settings=FakeSettingsService(),
        gate=gate,  # type: ignore[arg-type]
        event_bus=SpyEventBus(),
        task_runner=make_inline_task_runner(),
        clock=FakeClock(),
    )


def test_probe_deferred_when_gate_held_by_benchmark_run() -> None:
    """Proves: STORY-016-AC-7

    Covers EC-RUN-13. Given the single-inference gate is held by ``BENCHMARK_RUN``, when a
    readiness probe is requested, ``try_acquire(READINESS_PROBE, ...)``
    returns ``None``, no network probe is issued, and it is re-attempted
    once the gate goes ``IDLE`` — here on the very first poll, simulating
    the run finishing between the refused attempt and the retry.
    """
    # Arrange
    gate = _RefuseOnceThenIdleGate()
    client = FakeReadinessLLMClient(health=_reachable_health())
    service = _make_service_with_gate(gate=gate, client=client)

    # Act
    health = service.probe(_PROVIDER_ID)

    # Assert
    assert gate.try_acquire_calls == _EXPECTED_TRY_ACQUIRE_CALLS_ON_RETRY
    assert client.probe_health_calls == 1
    assert health.reachable is True


def test_probe_deferred_forever_when_gate_never_goes_idle_reports_deferred_health() -> None:
    """Proves: STORY-016-AC-7

    Covers EC-RUN-13. A request refused and never able to observe the gate go idle is
    reported as deferred data — never queued indefinitely and never an
    exception — with no network probe issued.
    """
    # Arrange
    gate = _AlwaysRefusingGate()
    client = FakeReadinessLLMClient(health=_reachable_health())
    service = _make_service_with_gate(gate=gate, client=client)

    # Act
    health = service.probe(_PROVIDER_ID)

    # Assert
    assert health.reachable is False
    assert client.probe_health_calls == 0
    assert health.last_error is not None
    assert "deferred" in health.last_error.lower()


def test_gate_is_released_in_finally_even_when_probe_raises() -> None:
    """Proves: STORY-016-AC-7

    Given the gate is acquired successfully, when the underlying probe
    raises an unexpected exception, the gate lease is still released — the
    acquire/release pairing holds even on an internal failure — and
    ``probe()`` returns collapsed unreachable data rather than letting the
    exception propagate, per the "never raises" contract.
    """
    # Arrange
    gate = _RefuseOnceThenIdleGate()
    client = _RaisingReadinessLLMClient(health=_reachable_health())
    service = _make_service_with_gate(gate=gate, client=client)

    # Act
    health = service.probe(_PROVIDER_ID)

    # Assert — the gate lease was still released despite the internal raise
    assert len(gate.released_leases) == 1
    assert health.reachable is False
    assert health.last_error is not None
