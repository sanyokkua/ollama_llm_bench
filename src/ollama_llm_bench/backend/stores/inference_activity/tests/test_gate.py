"""Acquire/release/exclusivity tests for ``InferenceActivityGate`` (STORY-015-AC-1..4)."""

from concurrent.futures import ThreadPoolExecutor

from ollama_llm_bench.backend.domain.models import (
    GateLease,
    InferenceActivity,
    InferenceActivityContext,
)
from ollama_llm_bench.backend.events.models import SIGNAL_INFERENCE_ACTIVITY_CHANGED
from ollama_llm_bench.backend.stores.inference_activity._internal.gate import (
    InferenceActivityGate,
)
from ollama_llm_bench.backend.stores.inference_activity.tests.conftest import (
    FakeClock,
    SpyEventBus,
)


def _make_context(*, activity: InferenceActivity, started_at: int = 0) -> InferenceActivityContext:
    return InferenceActivityContext(activity=activity, started_at=started_at)


def test_acquire_holds_gate_and_emits_activity_changed(
    fake_clock: FakeClock, spy_event_bus: SpyEventBus
) -> None:
    """Proves: STORY-015-AC-1

    Given the gate is IDLE, acquiring it returns a lease whose activity matches, the
    state reflects the held activity and context, ``is_busy()`` becomes True, and
    exactly one ``_inference_activity_changed`` event is emitted.
    """
    # Arrange
    gate = InferenceActivityGate(clock=fake_clock, event_bus=spy_event_bus)
    context = _make_context(activity=InferenceActivity.PROVIDER_TEST, started_at=1000)

    # Act
    lease = gate.try_acquire(InferenceActivity.PROVIDER_TEST, context)

    # Assert
    assert lease is not None
    assert lease.activity == InferenceActivity.PROVIDER_TEST
    state = gate.state()
    assert state.current == InferenceActivity.PROVIDER_TEST
    assert state.context == context
    assert gate.is_busy() is True
    changed_events = [e for e in spy_event_bus.emitted if e[0] == SIGNAL_INFERENCE_ACTIVITY_CHANGED]
    assert len(changed_events) == 1


def test_gate_is_mutually_exclusive_under_concurrent_acquire(
    fake_clock: FakeClock, spy_event_bus: SpyEventBus
) -> None:
    """Proves: STORY-015-AC-2

    For many threads calling ``try_acquire`` concurrently against one initially IDLE
    gate, exactly one call returns a lease and every other call returns None — this is
    the phase-level gate-exclusivity concurrency test.
    """
    # Arrange
    gate = InferenceActivityGate(clock=fake_clock, event_bus=spy_event_bus)
    thread_count = 40

    def _attempt(_index: int) -> GateLease | None:
        context = _make_context(activity=InferenceActivity.READINESS_PROBE)
        return gate.try_acquire(InferenceActivity.READINESS_PROBE, context)

    # Act
    with ThreadPoolExecutor(max_workers=thread_count) as pool:
        results = list(pool.map(_attempt, range(thread_count)))

    # Assert
    successes = [result for result in results if result is not None]
    failures = [result for result in results if result is None]
    assert len(successes) == 1
    assert len(failures) == thread_count - 1


def test_release_frees_gate_and_is_idempotent(
    fake_clock: FakeClock, spy_event_bus: SpyEventBus
) -> None:
    """Proves: STORY-015-AC-3

    Given a lease is the current holder, releasing it returns the gate to IDLE, makes
    ``is_busy()`` False, emits one ``_inference_activity_changed`` event, and a second
    release with the same now-superseded lease is a no-op that emits no further event.
    """
    # Arrange
    gate = InferenceActivityGate(clock=fake_clock, event_bus=spy_event_bus)
    context = _make_context(activity=InferenceActivity.JUDGE_ANALYSIS)
    lease = gate.try_acquire(InferenceActivity.JUDGE_ANALYSIS, context)
    assert lease is not None
    events_before_release = len(spy_event_bus.emitted)

    # Act
    gate.release(lease)
    events_after_first_release = len(spy_event_bus.emitted)
    gate.release(lease)

    # Assert
    assert gate.state().current == InferenceActivity.IDLE
    assert gate.is_busy() is False
    assert events_after_first_release - events_before_release == 1
    assert len(spy_event_bus.emitted) == events_after_first_release


def test_superseded_lease_release_never_frees_successor_hold(
    fake_clock: FakeClock, spy_event_bus: SpyEventBus
) -> None:
    """Proves: STORY-015-AC-4

    Given activity A holds the gate under lease L1 and is released, and activity B
    then acquires it under lease L2, a late release(L1) is a logged no-op and B's
    hold under L2 is preserved.
    """
    # Arrange
    gate = InferenceActivityGate(clock=fake_clock, event_bus=spy_event_bus)
    context_a = _make_context(activity=InferenceActivity.PROVIDER_TEST)
    lease_a = gate.try_acquire(InferenceActivity.PROVIDER_TEST, context_a)
    assert lease_a is not None
    gate.release(lease_a)
    context_b = _make_context(activity=InferenceActivity.READINESS_PROBE)
    lease_b = gate.try_acquire(InferenceActivity.READINESS_PROBE, context_b)
    assert lease_b is not None

    # Act
    gate.release(lease_a)

    # Assert
    state = gate.state()
    assert state.current == InferenceActivity.READINESS_PROBE
    assert state.context == context_b
    assert gate.is_busy() is True
