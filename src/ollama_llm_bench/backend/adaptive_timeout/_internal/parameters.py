"""Per-role parameter parsing from the frozen run snapshot (§2, §7)."""

from dataclasses import dataclass

import structlog

from ollama_llm_bench.backend.domain import AdaptiveTimeoutRole, BenchmarkRunSettingEntry

log = structlog.get_logger(__name__)

_INFERENCE_KEYS: dict[str, str] = {
    "min": "benchmark.min_timeout_seconds",
    "max": "benchmark.max_timeout_seconds",
    "steps": "benchmark.retry_count",
    "threshold": "benchmark.consecutive_max_timeouts_to_exclude",
}

_JUDGE_KEYS: dict[str, str] = {
    "min": "eval.judge_timeout_min_seconds",
    "max": "eval.judge_timeout_max_seconds",
    "steps": "eval.judge_timeout_escalation_steps",
    "threshold": "eval.judge_timeout_consecutive_threshold",
}

REQUIRED_SETTING_KEYS: frozenset[str] = frozenset(
    set(_INFERENCE_KEYS.values()) | set(_JUDGE_KEYS.values())
)


@dataclass(slots=True, frozen=True)
class _RoleParameters:
    """One role's escalation-ladder parameters (§7)."""

    min_timeout_seconds: int
    max_timeout_seconds: int
    escalation_steps: int
    consecutive_threshold: int


def parse_role_parameters(
    snapshot: tuple[BenchmarkRunSettingEntry, ...],
) -> dict[AdaptiveTimeoutRole, _RoleParameters]:
    """Read both parameter sets once from the frozen snapshot (§2).

    role=JUDGE and role=RUN_ANALYSIS share the same eval.judge_timeout_* values
    (DD-65) but the caller keys TimeoutState buckets by the full (provider,
    model, role) triple, so the two never share bucket state.

    Args:
        snapshot: The run's frozen per-run-overridable settings; must carry all
            eight adaptive-timeout keys (enforced by the api.py factory's
            icontract precondition, not here).

    Returns:
        A mapping from every AdaptiveTimeoutRole member to its _RoleParameters.
    """
    values = {entry.setting_key: entry.setting_value for entry in snapshot}
    inference = _build_parameters(values, _INFERENCE_KEYS, role_name="INFERENCE")
    judge = _build_parameters(values, _JUDGE_KEYS, role_name="JUDGE")
    return {
        AdaptiveTimeoutRole.INFERENCE: inference,
        AdaptiveTimeoutRole.JUDGE: judge,
        AdaptiveTimeoutRole.RUN_ANALYSIS: judge,
    }


def _build_parameters(
    values: dict[str, str], keys: dict[str, str], *, role_name: str
) -> _RoleParameters:
    params = _RoleParameters(
        min_timeout_seconds=int(values[keys["min"]]),
        max_timeout_seconds=int(values[keys["max"]]),
        escalation_steps=int(values[keys["steps"]]),
        consecutive_threshold=int(values[keys["threshold"]]),
    )
    if params.min_timeout_seconds > params.max_timeout_seconds:
        # Degenerate but valid (§8): the ladder collapses and every clamp caps
        # at role.max. Not fatal — logged once at construction.
        log.warning(
            "adaptive_timeout_degenerate_config",
            role=role_name,
            min_seconds=params.min_timeout_seconds,
            max_seconds=params.max_timeout_seconds,
        )
    return params
