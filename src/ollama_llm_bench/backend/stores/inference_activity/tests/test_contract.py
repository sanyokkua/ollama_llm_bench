"""Shared contract-test suite for ``InferenceActivityStore`` (real gate + fake).

Parametrized over ``(InferenceActivityGate via make_inference_activity_store,
FakeInferenceActivityStore)`` so the same assertions run against both implementations,
proving the fake is a faithful stand-in for ``try_acquire``/``release``/``state``/
``is_busy`` semantics — see the ``testing-standard-pyqt`` skill's "shared contract-test
suite per Protocol" section.
"""

import pytest

from ollama_llm_bench.backend.domain.models import InferenceActivity, InferenceActivityContext
from ollama_llm_bench.backend.stores.inference_activity.api import make_inference_activity_store
from ollama_llm_bench.backend.stores.inference_activity.protocols import InferenceActivityStore
from ollama_llm_bench.backend.stores.inference_activity.testing import FakeInferenceActivityStore
from ollama_llm_bench.backend.stores.inference_activity.tests.conftest import (
    FakeClock,
    SpyEventBus,
)


@pytest.fixture(params=["real", "fake"])
def activity_store(request: pytest.FixtureRequest) -> InferenceActivityStore:
    """An ``InferenceActivityStore`` — either the real gate or its fake — sharing
    their own fresh ``FakeClock``/``SpyEventBus`` collaborators per test."""
    clock = FakeClock()
    event_bus = SpyEventBus()
    if request.param == "real":
        return make_inference_activity_store(clock=clock, event_bus=event_bus)
    return FakeInferenceActivityStore(clock=clock, event_bus=event_bus)


def _make_context(*, activity: InferenceActivity) -> InferenceActivityContext:
    return InferenceActivityContext(activity=activity, started_at=0)


def test_fresh_store_starts_idle_and_not_busy(activity_store: InferenceActivityStore) -> None:
    """Proves: STORY-015-AC-1

    A freshly constructed store — real or fake — starts IDLE with ``is_busy()`` False.
    """
    # Arrange / Act
    state = activity_store.state()

    # Assert
    assert state.current == InferenceActivity.IDLE
    assert activity_store.is_busy() is False


def test_try_acquire_on_idle_store_returns_lease_matching_activity(
    activity_store: InferenceActivityStore,
) -> None:
    """Proves: STORY-015-AC-1

    ``try_acquire`` on an IDLE store returns a lease whose ``activity`` matches the
    requested activity, and the store becomes busy.
    """
    # Arrange
    context = _make_context(activity=InferenceActivity.PROVIDER_TEST)

    # Act
    lease = activity_store.try_acquire(InferenceActivity.PROVIDER_TEST, context)

    # Assert
    assert lease is not None
    assert lease.activity == InferenceActivity.PROVIDER_TEST
    assert activity_store.is_busy() is True


def test_try_acquire_on_held_store_returns_none(activity_store: InferenceActivityStore) -> None:
    """Proves: STORY-015-AC-2

    ``try_acquire`` against an already-held store returns None and does not disturb
    the existing holder.
    """
    # Arrange
    first_context = _make_context(activity=InferenceActivity.JUDGE_ANALYSIS)
    first_lease = activity_store.try_acquire(InferenceActivity.JUDGE_ANALYSIS, first_context)
    assert first_lease is not None

    # Act
    second_context = _make_context(activity=InferenceActivity.PROVIDER_TEST)
    second_lease = activity_store.try_acquire(InferenceActivity.PROVIDER_TEST, second_context)

    # Assert
    assert second_lease is None
    assert activity_store.state().current == InferenceActivity.JUDGE_ANALYSIS


def test_release_with_current_lease_returns_store_to_idle(
    activity_store: InferenceActivityStore,
) -> None:
    """Proves: STORY-015-AC-3

    Releasing the current holder's lease returns the store to IDLE and not-busy.
    """
    # Arrange
    context = _make_context(activity=InferenceActivity.READINESS_PROBE)
    lease = activity_store.try_acquire(InferenceActivity.READINESS_PROBE, context)
    assert lease is not None

    # Act
    activity_store.release(lease)

    # Assert
    assert activity_store.state().current == InferenceActivity.IDLE
    assert activity_store.is_busy() is False


def test_release_with_stale_lease_is_a_noop(activity_store: InferenceActivityStore) -> None:
    """Proves: STORY-015-AC-4

    Releasing a stale (already-superseded) lease never disturbs a later holder.
    """
    # Arrange
    first_context = _make_context(activity=InferenceActivity.PROVIDER_TEST)
    first_lease = activity_store.try_acquire(InferenceActivity.PROVIDER_TEST, first_context)
    assert first_lease is not None
    activity_store.release(first_lease)
    second_context = _make_context(activity=InferenceActivity.READINESS_PROBE)
    second_lease = activity_store.try_acquire(InferenceActivity.READINESS_PROBE, second_context)
    assert second_lease is not None

    # Act
    activity_store.release(first_lease)

    # Assert
    assert activity_store.state().current == InferenceActivity.READINESS_PROBE
