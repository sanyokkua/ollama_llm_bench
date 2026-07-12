"""AdaptiveTimeoutService — this module's swap point (08-E §17)."""

from typing import Protocol

from ollama_llm_bench.backend.adaptive_timeout.models import AdaptiveTimeoutModelState
from ollama_llm_bench.backend.domain import AdaptiveTimeoutRole, ModelName, ProviderId


class AdaptiveTimeoutService(Protocol):
    """Per-(provider, model, role) adaptive timeout and stability tracking (§6)."""

    def next_budget(
        self,
        provider_id: ProviderId,
        model_name: ModelName,
        role: AdaptiveTimeoutRole,
        attempt_index: int = 1,
    ) -> int:
        """fast-synchronous; never raises.

        Args:
            provider_id: The target's provider.
            model_name: The target's model.
            role: Selects the per-role bucket and parameter set.
            attempt_index: 1-based index of the attempt within the current task.

        Returns:
            The timeout budget, in seconds, always within
            [role.min_timeout_seconds, role.max_timeout_seconds].
        """
        ...

    def record_success(
        self,
        provider_id: ProviderId,
        model_name: ModelName,
        role: AdaptiveTimeoutRole,
        observed_ms: int,
    ) -> None:
        """fast-synchronous; never raises.

        Promotes the bucket's last-known-good budget when ``observed_ms`` exceeds
        it, and resets the in-run consecutive max-timeout counter to 0.
        """
        ...

    def record_timeout(
        self,
        provider_id: ProviderId,
        model_name: ModelName,
        role: AdaptiveTimeoutRole,
    ) -> None:
        """fast-synchronous; never raises.

        Increments the consecutive max-timeout counter when the last-queried
        budget for this bucket was at the role's maximum, and may flip the
        bucket to EXCLUDED when the role's consecutive_threshold is reached.
        """
        ...

    def is_excluded(
        self, provider_id: ProviderId, model_name: ModelName, role: AdaptiveTimeoutRole
    ) -> bool:
        """fast-synchronous; never raises. Independent per role."""
        ...

    def model_state(
        self, provider_id: ProviderId, model_name: ModelName, role: AdaptiveTimeoutRole
    ) -> AdaptiveTimeoutModelState:
        """fast-synchronous; never raises."""
        ...
