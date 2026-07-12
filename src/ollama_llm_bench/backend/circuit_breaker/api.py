"""Public factory for the Provider Circuit Breaker (§7, 08-E §18)."""

import icontract

from ollama_llm_bench.backend.circuit_breaker._internal.breaker import (
    _ProviderCircuitBreakerImpl,
)
from ollama_llm_bench.backend.circuit_breaker._internal.parameters import (
    REQUIRED_SETTING_KEYS,
    parse_breaker_parameters,
)
from ollama_llm_bench.backend.circuit_breaker.protocols import ProviderCircuitBreaker
from ollama_llm_bench.backend.domain import BenchmarkRunSettingEntry
from ollama_llm_bench.backend.infra import Clock

__all__: list[str] = ["make_circuit_breaker"]


def _has_all_required_keys(snapshot: tuple[BenchmarkRunSettingEntry, ...]) -> bool:
    present = {entry.setting_key for entry in snapshot}
    return REQUIRED_SETTING_KEYS.issubset(present)


@icontract.require(
    _has_all_required_keys,
    "snapshot must carry all three per-run-overridable circuit-breaker keys — "
    "RunSnapshotBuilder guarantees this; a missing key means the run-creation "
    "use case has a bug, not that the run itself is misconfigured",
)
def make_circuit_breaker(
    *, snapshot: tuple[BenchmarkRunSettingEntry, ...], clock: Clock
) -> ProviderCircuitBreaker:
    """Construct the Provider Circuit Breaker from a frozen run snapshot (§2, §7).

    Args:
        snapshot: The run's frozen per-run-overridable settings, read once at
            construction: ``circuit_breaker.enabled``,
            ``circuit_breaker.failure_threshold``, and
            ``circuit_breaker.cooldown_seconds``.
        clock: The injected monotonic clock used to measure the cooldown
            window (§6.5, §9). Never wall-clock.

    Returns:
        A synchronous, in-memory, run-scoped ProviderCircuitBreaker.
    """
    parameters = parse_breaker_parameters(snapshot)
    return _ProviderCircuitBreakerImpl(parameters=parameters, clock=clock)
