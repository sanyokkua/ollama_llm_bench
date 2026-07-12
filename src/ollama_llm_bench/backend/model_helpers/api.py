"""Public factory for the Model Capability Service (§4.8)."""

import icontract

from ollama_llm_bench.backend.infra import Clock
from ollama_llm_bench.backend.model_helpers._internal.capability_service import (
    _ModelCapabilityServiceImpl,
)
from ollama_llm_bench.backend.model_helpers.protocols import ModelCapabilityService
from ollama_llm_bench.backend.persistence.model_capabilities import ModelCapabilitiesStore

__all__: list[str] = ["make_model_capability_service"]


@icontract.require(lambda store: store is not None, "store must be constructed by the caller")
@icontract.require(lambda clock: clock is not None, "clock must be constructed by the caller")
def make_model_capability_service(
    *, store: ModelCapabilitiesStore, clock: Clock
) -> ModelCapabilityService:
    """Construct the Model Capability Service over an injected store and clock (§4.8).

    Args:
        store: The persistence store this service reads and writes capability
            records through.
        clock: The injected UTC time source used to stamp ``last_observed_at`` on
            every recorded observation.

    Returns:
        A synchronous ModelCapabilityService bound to the given store and clock.
    """
    return _ModelCapabilityServiceImpl(store=store, clock=clock)
