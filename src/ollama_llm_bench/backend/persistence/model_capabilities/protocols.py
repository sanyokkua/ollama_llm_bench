"""The ``ModelCapabilitiesStore`` contract owned by this module.

Source of truth: ``docs/v3_specification/08_Cross_Cutting/08-E_interfaces_contracts.md``
§7.5.
"""

from typing import Protocol

from ollama_llm_bench.backend.domain import ModelCapabilityRecord, ModelName, ProviderId

__all__: list[str] = [
    "ModelCapabilitiesStore",
]


class ModelCapabilitiesStore(Protocol):
    """Cached per-``(provider, model)`` capability records.

    fast-synchronous: every method is a quick SQLite read/write under WAL and
    may be called from either the GUI thread or the dispatcher thread.
    """

    def list_model_capabilities(
        self, provider_id: ProviderId, model_name: ModelName
    ) -> tuple[ModelCapabilityRecord, ...]:
        """Return the cached capability records for one model.

        Raises:
            PersistenceError: The underlying read failed.
        """
        ...

    def upsert_model_capability(self, record: ModelCapabilityRecord) -> None:
        """Insert or update one capability record on the
        ``(provider_id, model_name, capability)`` primary key.

        Raises:
            PersistenceError: The underlying write failed.
        """
        ...
