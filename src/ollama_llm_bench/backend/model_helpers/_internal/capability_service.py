"""The concrete ModelCapabilityService: reads and writes through a store (§4.8)."""

from ollama_llm_bench.backend.domain import (
    ModelCapability,
    ModelCapabilityRecord,
    ModelName,
    ProviderId,
)
from ollama_llm_bench.backend.infra import Clock
from ollama_llm_bench.backend.model_helpers.models import CapabilityObservation
from ollama_llm_bench.backend.persistence.model_capabilities import ModelCapabilitiesStore


class _ModelCapabilityServiceImpl:
    """Synchronous pass-through / single-upsert wrapper over a ``ModelCapabilitiesStore``."""

    def __init__(self, *, store: ModelCapabilitiesStore, clock: Clock) -> None:
        self._store = store
        self._clock = clock

    def get_capabilities(
        self, provider_id: ProviderId, model_name: ModelName
    ) -> tuple[ModelCapabilityRecord, ...]:
        """Return exactly the records the injected store reports for this pair (§4.8)."""
        return self._store.list_model_capabilities(provider_id, model_name)

    def record_capability(
        self,
        provider_id: ProviderId,
        model_name: ModelName,
        observation: CapabilityObservation,
    ) -> None:
        """Build and upsert exactly one ``ModelCapabilityRecord`` (§4.8)."""
        record = ModelCapabilityRecord(
            provider_id=provider_id,
            model_name=model_name,
            capability=observation.capability,
            supported=observation.supported,
            last_observed_at=self._clock.now_utc(),
            observed_via=observation.source,
            detail=observation.detail,
        )
        self._store.upsert_model_capability(record)

    def is_streaming_supported(self, provider_id: ProviderId, model_name: ModelName) -> bool:
        """Return ``True`` exactly when the STREAMING record's ``supported`` is 1 (§4.8)."""
        records = self.get_capabilities(provider_id, model_name)
        for record in records:
            if record.capability is ModelCapability.STREAMING:
                return record.supported == 1
        return False
