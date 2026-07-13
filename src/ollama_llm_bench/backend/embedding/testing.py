"""A configurable fake EmbeddingService for downstream module tests."""

from ollama_llm_bench.backend.domain import CosineScore, CosineThreshold
from ollama_llm_bench.backend.embedding._internal.math import compute_cosine

__all__: list[str] = ["FakeEmbeddingService"]


class FakeEmbeddingService:
    """An in-memory fake returning deterministic vectors, with externally settable
    threshold/short-circuit state for downstream-module test setup.

    Args:
        cosine_threshold: The value ``cosine_threshold()`` returns.
    """

    def __init__(self, *, cosine_threshold: CosineThreshold = 0.85) -> None:
        self._cosine_threshold = cosine_threshold
        self._short_circuited = False
        self.embed_calls: list[str] = []
        self.cosine_calls: list[tuple[str, str]] = []

    def embed(self, text: str) -> tuple[float, ...]:
        """Record the call and return a deterministic hash-derived vector."""
        self.embed_calls.append(text)
        if self._short_circuited:
            return ()
        normalised_text = text.strip()
        if not normalised_text:
            return (0.0, 0.0, 0.0)
        seed = abs(hash(normalised_text))
        return (float(seed % 97) + 1.0, float(seed % 53) + 1.0, float(seed % 17) + 1.0)

    def cosine(self, text_a: str, text_b: str) -> CosineScore:
        """Record the call and compute the cosine over the fake's deterministic vectors."""
        self.cosine_calls.append((text_a, text_b))
        return compute_cosine(self.embed(text_a), self.embed(text_b))

    def cosine_threshold(self) -> CosineThreshold:
        """Return whatever the constructor or ``set_cosine_threshold`` configured."""
        return self._cosine_threshold

    def is_short_circuited(self) -> bool:
        """Return whatever ``set_short_circuited`` configured; ``False`` by default."""
        return self._short_circuited

    def set_cosine_threshold(self, threshold: CosineThreshold) -> None:
        """Test helper: change the value ``cosine_threshold()`` returns."""
        self._cosine_threshold = threshold

    def set_short_circuited(self, *, short_circuited: bool) -> None:
        """Test helper: force ``is_short_circuited()``'s return value."""
        self._short_circuited = short_circuited
