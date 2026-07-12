"""The concrete AdaptiveTimeoutService: the ladder, outcome bookkeeping, and
per-role exclusion tracking (§6)."""

from ollama_llm_bench.backend.adaptive_timeout._internal.parameters import _RoleParameters
from ollama_llm_bench.backend.adaptive_timeout._internal.state import _BucketState, _TimeoutState
from ollama_llm_bench.backend.adaptive_timeout.models import AdaptiveTimeoutModelState
from ollama_llm_bench.backend.domain import AdaptiveTimeoutRole, ModelName, ProviderId

_BucketKey = tuple[ProviderId, ModelName, AdaptiveTimeoutRole]

_STATE_TO_MODEL_STATE: dict[_BucketState, AdaptiveTimeoutModelState] = {
    _BucketState.FRESH: AdaptiveTimeoutModelState.OK,
    _BucketState.PROMOTED: AdaptiveTimeoutModelState.OK,
    _BucketState.AT_MAX: AdaptiveTimeoutModelState.WARN,
    _BucketState.EXCLUDED: AdaptiveTimeoutModelState.EXCLUDED,
}


class _AdaptiveTimeoutServiceImpl:
    """Synchronous, single-owner (dispatcher-thread-only per §9), lock-free."""

    def __init__(self, *, parameters: dict[AdaptiveTimeoutRole, _RoleParameters]) -> None:
        self._parameters = parameters
        self._buckets: dict[_BucketKey, _TimeoutState] = {}

    def next_budget(
        self,
        provider_id: ProviderId,
        model_name: ModelName,
        role: AdaptiveTimeoutRole,
        attempt_index: int = 1,
    ) -> int:
        params = self._parameters[role]
        bucket = self._get_or_create_bucket(provider_id, model_name, role, params)
        budget_ms = _ladder_budget_ms(
            last_known_good_ms=bucket.last_known_good_ms,
            attempt_index=attempt_index,
            params=params,
        )
        bucket.last_queried_budget_ms = budget_ms
        return round(budget_ms / 1000)

    def record_success(
        self,
        provider_id: ProviderId,
        model_name: ModelName,
        role: AdaptiveTimeoutRole,
        observed_ms: int,
    ) -> None:
        params = self._parameters[role]
        bucket = self._get_or_create_bucket(provider_id, model_name, role, params)
        if bucket.state is _BucketState.EXCLUDED:
            return
        bucket.consecutive_max_timeouts = 0
        # promote — never lower (§6.4 rule 1)
        bucket.last_known_good_ms = max(bucket.last_known_good_ms, observed_ms)
        bucket.state = (
            _BucketState.PROMOTED
            if bucket.last_known_good_ms > params.min_timeout_seconds * 1000
            else _BucketState.FRESH
        )

    def record_timeout(
        self, provider_id: ProviderId, model_name: ModelName, role: AdaptiveTimeoutRole
    ) -> None:
        params = self._parameters[role]
        bucket = self._get_or_create_bucket(provider_id, model_name, role, params)
        if bucket.state is _BucketState.EXCLUDED:
            return
        at_max = bucket.last_queried_budget_ms >= params.max_timeout_seconds * 1000
        if at_max:
            bucket.consecutive_max_timeouts += 1
            bucket.state = (
                _BucketState.EXCLUDED
                if bucket.consecutive_max_timeouts >= params.consecutive_threshold
                else _BucketState.AT_MAX
            )
        elif bucket.last_known_good_ms >= params.max_timeout_seconds * 1000:
            # Defensive parity with the §6.4 pseudocode's sub-max branch: unreachable
            # in practice (LKG >= max forces every future budget to max via the
            # ladder's floor >= ceil collapse), kept for literal spec fidelity.
            bucket.state = _BucketState.AT_MAX

    def is_excluded(
        self, provider_id: ProviderId, model_name: ModelName, role: AdaptiveTimeoutRole
    ) -> bool:
        params = self._parameters[role]
        bucket = self._get_or_create_bucket(provider_id, model_name, role, params)
        return bucket.state is _BucketState.EXCLUDED

    def model_state(
        self, provider_id: ProviderId, model_name: ModelName, role: AdaptiveTimeoutRole
    ) -> AdaptiveTimeoutModelState:
        params = self._parameters[role]
        bucket = self._get_or_create_bucket(provider_id, model_name, role, params)
        return _STATE_TO_MODEL_STATE[bucket.state]

    def _get_or_create_bucket(
        self,
        provider_id: ProviderId,
        model_name: ModelName,
        role: AdaptiveTimeoutRole,
        params: _RoleParameters,
    ) -> _TimeoutState:
        key: _BucketKey = (provider_id, model_name, role)
        if key not in self._buckets:
            floor_ms = params.min_timeout_seconds * 1000
            self._buckets[key] = _TimeoutState(
                state=_BucketState.FRESH,
                last_known_good_ms=floor_ms,
                consecutive_max_timeouts=0,
                last_queried_budget_ms=floor_ms,
            )
        return self._buckets[key]


def _ladder_budget_ms(
    *, last_known_good_ms: int, attempt_index: int, params: _RoleParameters
) -> int:
    """The escalation ladder of §6.3, computed in milliseconds."""
    floor_ms = last_known_good_ms
    ceil_ms = params.max_timeout_seconds * 1000
    steps = params.escalation_steps

    if attempt_index == 1 or steps == 0 or floor_ms >= ceil_ms:
        budget_ms = floor_ms
    else:
        rung = min(attempt_index - 1, steps)
        budget_ms = round(floor_ms + (ceil_ms - floor_ms) * rung / steps)

    # role.max is the outer ceiling even when role.min > role.max (a degenerate
    # but valid config, §8/T-13): clamp against max FIRST, min second — a naive
    # max(min_ms, min(budget_ms, ceil_ms)) would instead float a degenerate
    # config UP to min_ms, breaking AC-6's "every budget <= role.max" guarantee.
    min_ms = params.min_timeout_seconds * 1000
    return min(ceil_ms, max(min_ms, budget_ms))
