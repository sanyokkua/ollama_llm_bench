"""ProviderHealthChecker — background health probe for LLM providers."""

import concurrent.futures
import logging
import time
from dataclasses import dataclass

from ollama_llm_bench.backend.core.interfaces import LLMProviderApi

logger = logging.getLogger(__name__)


@dataclass(slots=True, frozen=True, kw_only=True)
class HealthCheckResult:
    """Result of a single provider health check."""

    provider_id: str
    is_healthy: bool
    model_count: int
    error_message: str
    latency_ms: int


class ProviderHealthChecker:
    """Performs synchronous health checks against LLM providers.

    Each check lists available models with a 5-second timeout and measures
    wall-clock latency. Never raises to the caller.
    """

    def check(self, provider: LLMProviderApi) -> HealthCheckResult:
        """Test provider reachability by fetching its model list.

        Args:
            provider: Live provider instance to probe.

        Returns:
            HealthCheckResult describing the outcome.
        """
        start_ns = time.monotonic_ns()
        with concurrent.futures.ThreadPoolExecutor(max_workers=1) as executor:
            future = executor.submit(provider.get_available_models)
            try:
                models = future.result(timeout=5)
                elapsed_ms = int((time.monotonic_ns() - start_ns) // 1_000_000)
                return HealthCheckResult(
                    provider_id=provider.provider_id,
                    is_healthy=True,
                    model_count=len(models),
                    error_message="",
                    latency_ms=elapsed_ms,
                )
            except Exception as exc:
                logger.debug(
                    "provider_health_check_failed",
                    extra={"provider_id": provider.provider_id, "error": str(exc)},
                )
                return HealthCheckResult(
                    provider_id=provider.provider_id,
                    is_healthy=False,
                    model_count=0,
                    error_message=str(exc),
                    latency_ms=0,
                )
