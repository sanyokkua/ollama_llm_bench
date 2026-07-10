"""Shared fixtures for ``backend/concurrency/`` colocated tests."""

import pytest

from ollama_llm_bench.backend.infra.protocols import Clock


class _FakeClock:
    """A deterministic, injectable ``Clock`` with a manually advanceable monotonic
    counter, used to construct ``CancellationToken`` instances under test with no
    dependency on real wall-clock or monotonic time."""

    def __init__(self) -> None:
        self._monotonic_ms = 0

    def now_utc(self) -> str:
        return "2026-01-01T00:00:00+00:00"

    def monotonic_ms(self) -> int:
        return self._monotonic_ms

    def advance_ms(self, delta_ms: int) -> None:
        self._monotonic_ms += delta_ms


@pytest.fixture
def fake_clock() -> Clock:
    """A deterministic ``Clock`` fixture, fresh per test."""
    return _FakeClock()
