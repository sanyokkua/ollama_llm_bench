"""ModelCapabilityService — this module's swap point (§4.8).

Source of truth: ``docs/v3_specification/11_Services_and_Algorithms/01_SERVICE_INVENTORY.md``
§4.8. Not one of the ``08-E`` contract Protocols — defined here, following the Service
Inventory's own ``backend.model_helpers.protocols.ModelCapabilityService`` module path.
"""

from typing import Protocol

from ollama_llm_bench.backend.domain import ModelCapabilityRecord, ModelName, ProviderId
from ollama_llm_bench.backend.model_helpers.models import CapabilityObservation

__all__: list[str] = ["ModelCapabilityService"]


class ModelCapabilityService(Protocol):
    """Query and persist observed per-``(provider, model)`` capability flags (§4.8).

    Reads and writes through the injected ``ModelCapabilitiesStore``. Every method
    is fast-synchronous and callable from any thread; none swallows a storage
    failure — a ``PersistenceError`` raised by the store passes through unchanged.
    """

    def get_capabilities(
        self, provider_id: ProviderId, model_name: ModelName
    ) -> tuple[ModelCapabilityRecord, ...]:
        """Return the cached capability records for one ``(provider, model)`` pair.

        fast-synchronous.

        Args:
            provider_id: The target's provider.
            model_name: The target's model.

        Returns:
            Exactly the records the injected ``ModelCapabilitiesStore`` reports for
            this pair — no filtering or transformation.

        Raises:
            PersistenceError: The underlying store read failed.
        """
        ...

    def record_capability(
        self,
        provider_id: ProviderId,
        model_name: ModelName,
        observation: CapabilityObservation,
    ) -> None:
        """Record one observed capability for a ``(provider, model)`` pair.

        fast-synchronous. Writes exactly one upsert through the store on the
        ``(provider_id, model_name, observation.capability)`` primary key.

        Args:
            provider_id: The target's provider.
            model_name: The target's model.
            observation: The capability, its tri-state ``supported`` value, its
                ``CapabilitySource``, and an optional detail note.

        Raises:
            PersistenceError: The underlying store write failed.
        """
        ...

    def is_streaming_supported(self, provider_id: ProviderId, model_name: ModelName) -> bool:
        """Return whether streaming is a recorded-supported capability for the pair.

        fast-synchronous.

        Args:
            provider_id: The target's provider.
            model_name: The target's model.

        Returns:
            ``True`` exactly when a cached ``STREAMING`` capability record for this
            pair has ``supported == 1``; ``False`` when the record is absent or its
            ``supported`` value is ``0`` or ``-1``.

        Raises:
            PersistenceError: The underlying store read failed.
        """
        ...
