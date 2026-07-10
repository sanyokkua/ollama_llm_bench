"""Tests proving STORY-004-AC-1: the ``Clock`` Protocol's default implementation.

Source of truth: ``docs/v3_specification/08_Cross_Cutting/08-E_interfaces_contracts.md``
§5 (Clock).
"""

from datetime import UTC, datetime
from typing import TYPE_CHECKING

from ollama_llm_bench.backend.infra.api import make_system_clock

if TYPE_CHECKING:
    from ollama_llm_bench.backend.infra.protocols import Clock

_FIXED_MONOTONIC_MS = 42


class _FakeClock:
    """A deterministic, injectable ``Clock`` used by other modules' tests."""

    def __init__(self, *, fixed_now_utc: str, fixed_monotonic_ms: int) -> None:
        self._fixed_now_utc = fixed_now_utc
        self._fixed_monotonic_ms = fixed_monotonic_ms

    def now_utc(self) -> str:
        return self._fixed_now_utc

    def monotonic_ms(self) -> int:
        return self._fixed_monotonic_ms


def test_clock_now_utc_and_monotonic_ms_contract() -> None:
    """Proves: STORY-004-AC-1

    The real ``SystemClock`` (obtained via ``make_system_clock``) returns a
    ``now_utc()`` value that round-trips as a valid ISO-8601 UTC timestamp and a
    ``monotonic_ms()`` value that is non-decreasing across two successive calls;
    a fake, injectable ``Clock`` produces fully deterministic values in tests.
    """
    # Arrange
    clock: Clock = make_system_clock()

    # Act
    now_utc = clock.now_utc()
    parsed = datetime.fromisoformat(now_utc)
    first_monotonic_ms = clock.monotonic_ms()
    second_monotonic_ms = clock.monotonic_ms()

    fake_clock: Clock = _FakeClock(
        fixed_now_utc="2026-01-01T00:00:00+00:00", fixed_monotonic_ms=_FIXED_MONOTONIC_MS
    )

    # Assert
    assert parsed.tzinfo is not None
    assert parsed.utcoffset() == UTC.utcoffset(None)
    assert second_monotonic_ms >= first_monotonic_ms
    assert fake_clock.now_utc() == "2026-01-01T00:00:00+00:00"
    assert fake_clock.monotonic_ms() == _FIXED_MONOTONIC_MS
    assert fake_clock.now_utc() == fake_clock.now_utc()
    assert fake_clock.monotonic_ms() == fake_clock.monotonic_ms()
