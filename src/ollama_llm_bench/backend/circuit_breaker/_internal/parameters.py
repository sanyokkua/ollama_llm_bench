"""Circuit-breaker parameter parsing from the frozen run snapshot (§2, §7)."""

from dataclasses import dataclass

from ollama_llm_bench.backend.domain import BenchmarkRunSettingEntry

_ENABLED_KEY = "circuit_breaker.enabled"
_FAILURE_THRESHOLD_KEY = "circuit_breaker.failure_threshold"
_COOLDOWN_SECONDS_KEY = "circuit_breaker.cooldown_seconds"

REQUIRED_SETTING_KEYS: frozenset[str] = frozenset(
    {_ENABLED_KEY, _FAILURE_THRESHOLD_KEY, _COOLDOWN_SECONDS_KEY}
)


@dataclass(slots=True, frozen=True)
class _BreakerParameters:
    """The breaker's three run-frozen configuration values (§7)."""

    enabled: bool
    failure_threshold: int
    cooldown_seconds: int


def parse_breaker_parameters(
    snapshot: tuple[BenchmarkRunSettingEntry, ...],
) -> _BreakerParameters:
    """Read the three circuit-breaker keys once from the frozen snapshot (§2, §7).

    Args:
        snapshot: The run's frozen per-run-overridable settings; must carry all
            three circuit-breaker keys (enforced by the api.py factory's
            icontract precondition, not here).

    Returns:
        The parsed, immutable breaker parameters for the run's lifetime.
    """
    values = {entry.setting_key: entry.setting_value for entry in snapshot}
    return _BreakerParameters(
        enabled=_coerce_bool(values[_ENABLED_KEY]),
        failure_threshold=int(values[_FAILURE_THRESHOLD_KEY]),
        cooldown_seconds=int(values[_COOLDOWN_SECONDS_KEY]),
    )


def _coerce_bool(raw: str) -> bool:
    """Coerce a registry-storage-form boolean string to ``bool``."""
    return raw.strip().lower() == "true"
