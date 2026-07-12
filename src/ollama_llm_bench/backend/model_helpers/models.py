"""DTOs owned by ``backend/model_helpers/``.

Source of truth: ``docs/v3_specification/11_Services_and_Algorithms/01_SERVICE_INVENTORY.md``
§4.8.
"""

import msgspec

from ollama_llm_bench.backend.domain import CapabilitySource, ModelCapability

__all__: list[str] = ["CapabilityObservation"]


class CapabilityObservation(msgspec.Struct, frozen=True, kw_only=True, gc=False):
    """One capability observation to record for a ``(provider, model)`` pair.

    Bundles ``ModelCapabilityService.record_capability``'s non-identity fields so the
    method stays within the project's parameter-count limit (`coding-style.md`),
    mirroring how ``LLMClient.chat`` bundles its request fields into ``ChatRequest``.
    """

    capability: ModelCapability
    supported: int
    source: CapabilitySource
    detail: str | None = None
