"""A configurable fake ModelCapabilityService for downstream module tests."""

from ollama_llm_bench.backend.domain import (
    ModelCapability,
    ModelCapabilityRecord,
    ModelName,
    ProviderId,
)
from ollama_llm_bench.backend.model_helpers.models import CapabilityObservation

__all__: list[str] = ["FakeModelCapabilityService"]

_RecordKey = tuple[ProviderId, ModelName, ModelCapability]


class FakeModelCapabilityService:
    """An in-memory fake keyed by ``(provider_id, model_name, capability)``.

    No real store behind it — a test seeds records directly via ``seed_record``
    or through ordinary ``record_capability`` calls.
    """

    def __init__(self, *, now_utc: str = "2026-01-01T00:00:00Z") -> None:
        self._now_utc = now_utc
        self._records: dict[_RecordKey, ModelCapabilityRecord] = {}
        self.recorded_calls: list[tuple[ProviderId, ModelName, CapabilityObservation]] = []

    def get_capabilities(
        self, provider_id: ProviderId, model_name: ModelName
    ) -> tuple[ModelCapabilityRecord, ...]:
        """Return every seeded/recorded record for this ``(provider, model)`` pair."""
        return tuple(
            record
            for (rec_provider, rec_model, _capability), record in self._records.items()
            if rec_provider == provider_id and rec_model == model_name
        )

    def record_capability(
        self,
        provider_id: ProviderId,
        model_name: ModelName,
        observation: CapabilityObservation,
    ) -> None:
        """Record the call and upsert one fake record, keyed on the primary key."""
        self.recorded_calls.append((provider_id, model_name, observation))
        record = ModelCapabilityRecord(
            provider_id=provider_id,
            model_name=model_name,
            capability=observation.capability,
            supported=observation.supported,
            last_observed_at=self._now_utc,
            observed_via=observation.source,
            detail=observation.detail,
        )
        self._records[(provider_id, model_name, observation.capability)] = record

    def is_streaming_supported(self, provider_id: ProviderId, model_name: ModelName) -> bool:
        """Return ``True`` exactly when the seeded STREAMING record's ``supported`` is 1."""
        record = self._records.get((provider_id, model_name, ModelCapability.STREAMING))
        return record is not None and record.supported == 1

    def seed_record(self, record: ModelCapabilityRecord) -> None:
        """Test helper: insert a fully-formed record directly, bypassing the clock."""
        self._records[(record.provider_id, record.model_name, record.capability)] = record
