"""A configurable fake AdaptiveTimeoutService for downstream module tests."""

from ollama_llm_bench.backend.adaptive_timeout.models import AdaptiveTimeoutModelState
from ollama_llm_bench.backend.domain import AdaptiveTimeoutRole, ModelName, ProviderId

__all__: list[str] = ["FakeAdaptiveTimeoutService"]

_BucketKey = tuple[ProviderId, ModelName, AdaptiveTimeoutRole]


class FakeAdaptiveTimeoutService:
    """An in-memory fake returning a fixed budget, with externally settable
    exclusion/state for downstream-module test setup.

    Args:
        fixed_budget_seconds: The value every ``next_budget`` call returns.
    """

    def __init__(self, *, fixed_budget_seconds: int = 60) -> None:
        self._fixed_budget_seconds = fixed_budget_seconds
        self._excluded: set[_BucketKey] = set()
        self._states: dict[_BucketKey, AdaptiveTimeoutModelState] = {}
        self.recorded_successes: list[tuple[ProviderId, ModelName, AdaptiveTimeoutRole, int]] = []
        self.recorded_timeouts: list[tuple[ProviderId, ModelName, AdaptiveTimeoutRole]] = []

    def next_budget(
        self,
        provider_id: ProviderId,  # noqa: ARG002  # fixed-budget fake: query input unused by design
        model_name: ModelName,  # noqa: ARG002  # fixed-budget fake: query input unused by design
        role: AdaptiveTimeoutRole,  # noqa: ARG002  # fixed-budget fake: query input unused by design
        attempt_index: int = 1,  # noqa: ARG002  # fixed-budget fake: query input unused by design
    ) -> int:
        """Return the fixed budget regardless of attempt_index."""
        return self._fixed_budget_seconds

    def record_success(
        self,
        provider_id: ProviderId,
        model_name: ModelName,
        role: AdaptiveTimeoutRole,
        observed_ms: int,
    ) -> None:
        """Record the call for later assertion; no state machine behind it."""
        self.recorded_successes.append((provider_id, model_name, role, observed_ms))

    def record_timeout(
        self, provider_id: ProviderId, model_name: ModelName, role: AdaptiveTimeoutRole
    ) -> None:
        """Record the call for later assertion; no state machine behind it."""
        self.recorded_timeouts.append((provider_id, model_name, role))

    def is_excluded(
        self, provider_id: ProviderId, model_name: ModelName, role: AdaptiveTimeoutRole
    ) -> bool:
        """Return whatever ``set_excluded`` configured for this bucket."""
        return (provider_id, model_name, role) in self._excluded

    def model_state(
        self, provider_id: ProviderId, model_name: ModelName, role: AdaptiveTimeoutRole
    ) -> AdaptiveTimeoutModelState:
        """Return whatever ``set_model_state`` configured, or OK by default."""
        key = (provider_id, model_name, role)
        if key in self._excluded:
            return AdaptiveTimeoutModelState.EXCLUDED
        return self._states.get(key, AdaptiveTimeoutModelState.OK)

    def set_excluded(
        self, provider_id: ProviderId, model_name: ModelName, role: AdaptiveTimeoutRole
    ) -> None:
        """Test helper: force a (provider, model, role) target into EXCLUDED."""
        self._excluded.add((provider_id, model_name, role))

    def set_model_state(
        self,
        provider_id: ProviderId,
        model_name: ModelName,
        role: AdaptiveTimeoutRole,
        state: AdaptiveTimeoutModelState,
    ) -> None:
        """Test helper: force a (provider, model, role) target's model_state."""
        self._states[(provider_id, model_name, role)] = state
