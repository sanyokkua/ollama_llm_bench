"""Service for querying and persisting model capability observations."""

import logging

from ollama_llm_bench.backend.core.interfaces import DataApi

logger = logging.getLogger(__name__)

_THINKING_CAPABILITY = "thinking"


class ModelCapabilityService:
    """Persists and retrieves per-model capability flags via the DataApi.

    Maps the integer DB representation (1/0/-1/None) to Python bool/None
    and delegates all persistence to the injected DataApi so the service
    itself is stateless between calls.
    """

    def __init__(self, *, data_api: DataApi) -> None:
        """Initialize with the data persistence layer.

        Args:
            data_api: DataApi instance used for reading and writing capability rows.
        """
        self._data_api = data_api

    def get(self, provider_id: str, model_name: str, capability: str) -> bool | None:
        """Retrieve a stored capability flag.

        Args:
            provider_id: Provider identifier.
            model_name: Model identifier.
            capability: Capability key (e.g. ``"thinking"``).

        Returns:
            True if supported, False if not supported, None if unknown or no row.
        """
        raw = self._data_api.get_model_capability(provider_id, model_name, capability)
        if raw is None or raw == -1:
            return None
        return raw == 1

    def remember(
        self,
        provider_id: str,
        model_name: str,
        capability: str,
        *,
        supported: bool,
        observed_via: str,
        detail: str | None = None,
    ) -> None:
        """Persist a capability observation.

        Args:
            provider_id: Provider identifier.
            model_name: Model identifier.
            capability: Capability key.
            supported: True if the capability is supported, False otherwise.
            observed_via: Short label describing the observation source.
            detail: Optional additional context such as the raw error message.
        """
        try:
            self._data_api.set_model_capability(
                provider_id,
                model_name,
                capability,
                supported=supported,
                observed_via=observed_via,
                detail=detail,
            )
        except Exception:
            logger.exception(
                "model_capability_persist_failed",
                extra={"provider_id": provider_id, "model_name": model_name, "capability": capability},
            )

    def supports_thinking(self, provider_id: str, model_name: str) -> bool | None:
        """Return whether the model supports extended thinking.

        Args:
            provider_id: Provider identifier.
            model_name: Model identifier.

        Returns:
            True if supported, False if not supported, None if unknown.
        """
        return self.get(provider_id, model_name, _THINKING_CAPABILITY)
