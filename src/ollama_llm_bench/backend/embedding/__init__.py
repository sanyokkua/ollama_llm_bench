"""Embedding Service — LRU-cached embeddings and the clamped Cosine Score.

Source of truth: ``docs/v3_specification/11_Services_and_Algorithms/06_EMBEDDING_SERVICE.md``
and ``08_Cross_Cutting/08-E_interfaces_contracts.md`` §10.

Turns text into a numeric vector through the run's embedding ``LLMClient``, computes the
whole-text cosine similarity between two texts as the clamped ``[0.0, 1.0]`` Cosine
Score, looks up the single ``eval.cosine_threshold`` from the run snapshot, memoises
vectors in a bounded LRU cache so a golden answer embedded once is reused across every
test model in the run, and short-circuits the whole cosine dimension run-wide after
``eval.embedding_consecutive_failures_to_skip`` consecutive embedding failures (DD-70).
The service is the only producer of a numeric quality value in the application; it
decides no ``PASS``/``FAIL`` itself.
"""

from ollama_llm_bench.backend.embedding.api import is_embedding_model, make_embedding_service
from ollama_llm_bench.backend.embedding.protocols import EmbeddingService

__all__: list[str] = [
    "EmbeddingService",
    "is_embedding_model",
    "make_embedding_service",
]
