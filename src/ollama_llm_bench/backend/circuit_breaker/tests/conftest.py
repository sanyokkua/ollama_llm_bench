"""Shared test helpers for backend/circuit_breaker/tests/.

``backend/infra`` has no shared fake ``Clock`` reusable here without importing a
concrete real implementation (see ``backend/stores/inference_activity/tests/conftest.py``
for the identical precedent) — a local ``FakeClock`` is defined instead.
"""

from datetime import UTC, datetime

from ollama_llm_bench.backend.domain import BenchmarkRunSettingEntry
from ollama_llm_bench.backend.domain.models import Iso8601Utc


def build_snapshot(
    *,
    enabled: bool = True,
    failure_threshold: int = 5,
    cooldown_seconds: int = 60,
) -> tuple[BenchmarkRunSettingEntry, ...]:
    """Build a valid 3-key circuit-breaker snapshot (defaults per spec §7).

    Args:
        enabled: ``circuit_breaker.enabled`` override.
        failure_threshold: ``circuit_breaker.failure_threshold`` override.
        cooldown_seconds: ``circuit_breaker.cooldown_seconds`` override.

    Returns:
        A tuple of 3 ``BenchmarkRunSettingEntry`` rows, one per circuit-breaker key.
    """
    values: dict[str, str] = {
        "circuit_breaker.enabled": "true" if enabled else "false",
        "circuit_breaker.failure_threshold": str(failure_threshold),
        "circuit_breaker.cooldown_seconds": str(cooldown_seconds),
    }
    return tuple(
        BenchmarkRunSettingEntry(setting_key=key, setting_value=value)
        for key, value in values.items()
    )


class FakeClock:
    """A fully controllable ``Clock`` double.

    Only ``monotonic_ms()`` is exercised by this module, but ``now_utc()`` is
    implemented too so the fake satisfies the full ``Clock`` Protocol shape.
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
        """Move the monotonic counter forward by ``delta_ms``."""
        self._monotonic_ms += delta_ms
