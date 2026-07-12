"""Public factory for the Adaptive Timeout Service (§7, 08-E §17)."""

import icontract

from ollama_llm_bench.backend.adaptive_timeout._internal.parameters import (
    REQUIRED_SETTING_KEYS,
    parse_role_parameters,
)
from ollama_llm_bench.backend.adaptive_timeout._internal.service import (
    _AdaptiveTimeoutServiceImpl,
)
from ollama_llm_bench.backend.adaptive_timeout.protocols import AdaptiveTimeoutService
from ollama_llm_bench.backend.domain import BenchmarkRunSettingEntry

__all__: list[str] = ["make_adaptive_timeout_service"]


def _has_all_required_keys(snapshot: tuple[BenchmarkRunSettingEntry, ...]) -> bool:
    present = {entry.setting_key for entry in snapshot}
    return REQUIRED_SETTING_KEYS.issubset(present)


@icontract.require(
    _has_all_required_keys,
    "snapshot must carry all eight per-run-overridable adaptive-timeout keys — "
    "RunSnapshotBuilder guarantees this; a missing key means the run-creation "
    "use case has a bug, not that the run itself is misconfigured",
)
def make_adaptive_timeout_service(
    *, snapshot: tuple[BenchmarkRunSettingEntry, ...]
) -> AdaptiveTimeoutService:
    """Construct the Adaptive Timeout Service from a frozen run snapshot (§2).

    Args:
        snapshot: The run's frozen per-run-overridable settings, read once at
            construction. Both the role=INFERENCE ``benchmark.*`` ladder and the
            role=JUDGE ``eval.judge_timeout_*`` ladder (also used by
            role=RUN_ANALYSIS, DD-65) are parsed from it.

    Returns:
        A synchronous, in-memory AdaptiveTimeoutService bound to this run.
    """
    parameters = parse_role_parameters(snapshot)
    return _AdaptiveTimeoutServiceImpl(parameters=parameters)
