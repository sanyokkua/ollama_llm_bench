"""A deterministic in-memory fake ``ModelCapabilitiesStore`` for downstream module tests.

Source of truth: ``docs/v3_specification/11_Services_and_Algorithms/01_SERVICE_INVENTORY.md``
§6 (test-double convention) — every contract service is faked in its own package's
``testing.py``, honouring the same contract as the real ``SqliteModelCapabilitiesStore``.
"""

from ollama_llm_bench.backend.domain import ModelCapabilityRecord, ModelName, ProviderId

__all__: list[str] = ["FakeModelCapabilitiesStore"]

_RecordKey = tuple[ProviderId, ModelName, str]


class FakeModelCapabilitiesStore:
    """An in-memory, deterministic double honouring the ``ModelCapabilitiesStore`` contract.

    No network, no real filesystem, no real clock — a test seeds records directly
    via the constructor or ordinary ``upsert_model_capability`` calls.
    """

    def __init__(self, *, records: tuple[ModelCapabilityRecord, ...] = ()) -> None:
        self._records: dict[_RecordKey, ModelCapabilityRecord] = {
            _key(record): record for record in records
        }

    def list_model_capabilities(
        self, provider_id: ProviderId, model_name: ModelName
    ) -> tuple[ModelCapabilityRecord, ...]:
        """Return every stored record for this ``(provider, model)`` pair."""
        return tuple(
            record
            for (rec_provider, rec_model, _capability), record in self._records.items()
            if rec_provider == provider_id and rec_model == model_name
        )

    def upsert_model_capability(self, record: ModelCapabilityRecord) -> None:
        """Insert or update one record on its ``(provider_id, model_name, capability)`` key."""
        self._records[_key(record)] = record


def _key(record: ModelCapabilityRecord) -> _RecordKey:
    """Build the fake's primary-key tuple, mirroring the real table's PK."""
    return (record.provider_id, record.model_name, record.capability.value)
