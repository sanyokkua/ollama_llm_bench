"""Shared fixtures and local test doubles for ``backend/stores/inference_activity/`` tests.

``backend/stores/inference_activity/testing.py`` exports ``FakeInferenceActivityStore`` — a
fake of *this module's own Protocol* — for *downstream* consumers; it would be circular to
use it to test this module itself (``test_contract.py`` is the deliberate exception: it
parametrizes over both the real ``InferenceActivityGate`` and ``FakeInferenceActivityStore``
to prove the fake is a faithful stand-in). These tests instead need a controllable fake of
this module's collaborator Protocols (``Clock``, ``EventBus``), defined locally here — no
suitable fake already exists under ``backend/settings/tests/`` or ``backend/infra/tests/``
(those modules' fakes are scoped to their own collaborators).
"""

from collections.abc import Callable
from datetime import UTC, datetime

import pytest

from ollama_llm_bench.backend.domain.models import Iso8601Utc
from ollama_llm_bench.backend.events.protocols import Subscription


class FakeClock:
    """A fully controllable ``Clock`` double.

    ``now_utc()`` and ``monotonic_ms()`` are independent, test-driven values — advancing
    one never implicitly advances the other, so watchdog elapsed-time arithmetic
    (``monotonic_ms``-only, per the gate's design constraints) can be exercised
    deterministically with no real waiting/sleeping.
    """

    def __init__(self, *, start_monotonic_ms: int = 0) -> None:
        self._monotonic_ms = start_monotonic_ms
        self._now = datetime(2026, 1, 1, tzinfo=UTC)

    def now_utc(self) -> Iso8601Utc:
        """Return the fake's current wall-clock instant as an ISO-8601 UTC string."""
        return self._now.isoformat()

    def monotonic_ms(self) -> int:
        """Return the fake's current monotonic millisecond counter."""
        return self._monotonic_ms

    def advance_monotonic_ms(self, delta_ms: int) -> None:
        """Move the monotonic counter forward by ``delta_ms``, leaving wall-clock untouched."""
        self._monotonic_ms += delta_ms


class SpyEventBus:
    """A minimal in-memory ``EventBus`` double recording every ``emit`` call, in order."""

    def __init__(self) -> None:
        self.emitted: list[tuple[str, object]] = []

    def subscribe(
        self, signal_name: str, handler: Callable[[object], None], owner: object | None = None
    ) -> Subscription:
        """Unused by these tests; present only to satisfy the Protocol shape."""
        raise NotImplementedError(
            "subscribe is not exercised by backend/stores/inference_activity tests"
        )

    def emit(self, signal_name: str, payload: object) -> None:
        """Record the emitted ``(signal_name, payload)`` pair, in call order."""
        self.emitted.append((signal_name, payload))


@pytest.fixture
def fake_clock() -> FakeClock:
    """A fresh ``FakeClock`` starting at monotonic 0."""
    return FakeClock()


@pytest.fixture
def spy_event_bus() -> SpyEventBus:
    """A fresh ``SpyEventBus`` with no recorded emissions."""
    return SpyEventBus()
