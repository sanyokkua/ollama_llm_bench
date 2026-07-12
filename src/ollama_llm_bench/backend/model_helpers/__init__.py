"""Model name parser, capability service, embedding-model classifier.

Source of truth: ``docs/v3_specification/11_Services_and_Algorithms/01_SERVICE_INVENTORY.md``
§4.7-§4.9. ``parse_model_name`` and ``is_embedding_model`` are pure functions with no
Protocol or double; ``ModelCapabilityService`` is a swap point over the injected
``ModelCapabilitiesStore``, constructed by ``make_model_capability_service``.
"""

from ollama_llm_bench.backend.model_helpers.api import make_model_capability_service
from ollama_llm_bench.backend.model_helpers.classifier import is_embedding_model
from ollama_llm_bench.backend.model_helpers.model_name import ModelNameParsed, parse_model_name
from ollama_llm_bench.backend.model_helpers.models import CapabilityObservation
from ollama_llm_bench.backend.model_helpers.protocols import ModelCapabilityService

__all__: list[str] = [
    "CapabilityObservation",
    "ModelCapabilityService",
    "ModelNameParsed",
    "is_embedding_model",
    "make_model_capability_service",
    "parse_model_name",
]
