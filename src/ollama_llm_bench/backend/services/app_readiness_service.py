"""App readiness probe: provider and embedding health snapshot."""

import concurrent.futures
import logging

from ollama_llm_bench.backend.core.interfaces import (
    AppReadinessServiceApi,
    AppSettingsServiceApi,
    EmbeddingProviderApi,
    ProviderRegistryApi,
)
from ollama_llm_bench.backend.core.models import AppReadinessChangedEvent, ReadinessVerdict, RunMode
from ollama_llm_bench.backend.services.app_settings_service import SETTING_COSINE_ENABLED
from ollama_llm_bench.backend.services.provider_health_checker import ProviderHealthChecker

_EMBEDDING_MODES: frozenset[RunMode] = frozenset({RunMode.FULL_GRADING, RunMode.PROMPT_EVAL})

logger = logging.getLogger(__name__)


class AppReadinessService(AppReadinessServiceApi):
    """Probes provider and embedding health and computes per-mode readiness verdicts."""

    def __init__(
        self,
        *,
        provider_registry: ProviderRegistryApi,
        embedding_provider: EmbeddingProviderApi,
        app_settings: AppSettingsServiceApi,
        health_checker: ProviderHealthChecker,
    ) -> None:
        self._registry = provider_registry
        self._embedding_provider = embedding_provider
        self._settings = app_settings
        self._checker = health_checker

    def compute_snapshot(self) -> AppReadinessChangedEvent:
        """Synchronously probe all enabled providers and embedding, return health snapshot.

        Runs provider checks in parallel via ThreadPoolExecutor.
        This method blocks and should be called from a background thread.

        Returns:
            AppReadinessChangedEvent describing overall provider and embedding health.
        """
        providers = self._registry.get_enabled_providers()
        unhealthy: list[str] = []
        has_any_models = False

        if providers:
            with concurrent.futures.ThreadPoolExecutor(max_workers=len(providers)) as pool:
                futures = {pool.submit(self._checker.check, p): p for p in providers}
                for future, provider in futures.items():
                    try:
                        result = future.result(timeout=8)
                        if not result.is_healthy:
                            unhealthy.append(result.provider_id)
                        elif result.model_count > 0:
                            has_any_models = True
                    except Exception:
                        logger.exception(
                            "provider_readiness_probe_failed",
                            extra={"provider_id": provider.provider_id},
                        )
                        unhealthy.append(provider.provider_id)

        # When cosine is disabled the embedding probe is irrelevant; treat as ok.
        embedding_ok = True
        embedding_error = ""
        cosine_on = self._settings.get_bool(SETTING_COSINE_ENABLED, default=True)
        if cosine_on:
            embedding_ok = False
            try:
                vectors = self._embedding_provider.encode(["health"])
                embedding_ok = len(vectors) > 0 and len(vectors[0]) > 0
                if not embedding_ok:
                    embedding_error = "Embedding returned empty vector"
            except Exception as exc:
                logger.exception("embedding_readiness_probe_failed")
                embedding_error = str(exc)

        return AppReadinessChangedEvent(
            has_any_models=has_any_models,
            embedding_ok=embedding_ok,
            embedding_error=embedding_error,
            unhealthy_providers=tuple(unhealthy),
        )

    def verdict_for(self, mode: RunMode, snapshot: AppReadinessChangedEvent) -> ReadinessVerdict:
        """Compute a per-mode verdict from a health snapshot. Pure function, no I/O.

        Args:
            mode: The run mode to evaluate.
            snapshot: Health snapshot from a prior compute_snapshot() call.

        Returns:
            ReadinessVerdict describing whether the mode is startable and why not.
        """
        issues: list[str] = []

        if not snapshot.has_any_models:
            issues.append("No enabled providers have any models available.")

        if mode in _EMBEDDING_MODES and not snapshot.embedding_ok:
            reason = snapshot.embedding_error or "Embedding model unreachable."
            issues.append(f"Mode '{mode.value}' requires embedding: {reason}")

        if issues:
            return ReadinessVerdict(
                mode=mode,
                is_ready=False,
                issues=tuple(issues),
                severity="error",
            )
        if snapshot.unhealthy_providers:
            names = ", ".join(snapshot.unhealthy_providers)
            return ReadinessVerdict(
                mode=mode,
                is_ready=True,
                issues=(f"Some providers unreachable: {names}",),
                severity="warning",
            )
        return ReadinessVerdict(mode=mode, is_ready=True, issues=(), severity="ok")
