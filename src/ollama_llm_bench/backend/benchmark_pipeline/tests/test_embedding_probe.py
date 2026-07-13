"""Proves: STORY-029-AC-3"""

from ollama_llm_bench.backend.benchmark_pipeline._internal.embedding_probe import (
    run_embedding_probe,
    run_needs_embeddings,
)
from ollama_llm_bench.backend.domain import CosineScore, CosineThreshold


class _FailingEmbeddingService:
    def embed(self, text: str) -> tuple[float, ...]:
        return ()

    def cosine(self, text_a: str, text_b: str) -> CosineScore:
        return 0.0

    def cosine_threshold(self) -> CosineThreshold:
        return 0.5

    def is_short_circuited(self) -> bool:
        return False


class _WorkingEmbeddingService:
    def embed(self, text: str) -> tuple[float, ...]:
        return (0.1, 0.2, 0.3)

    def cosine(self, text_a: str, text_b: str) -> CosineScore:
        return 0.0

    def cosine_threshold(self) -> CosineThreshold:
        return 0.5

    def is_short_circuited(self) -> bool:
        return False


def test_run_needs_embeddings_true_when_cosine_enabled_with_golden_answer() -> None:
    """Proves: STORY-029-AC-3"""
    result = run_needs_embeddings(
        run_mode_graded=True,
        cosine_enabled=True,
        has_golden_answer_task=True,
        keyword_enabled=False,
        has_semantic_terms_task=False,
    )
    assert result is True


def test_run_start_embed_probe_fails_fast_before_inference() -> None:
    """Proves: STORY-029-AC-3

    A failing probe returns a non-None, redacted error string naming the
    embedding pair; a successful probe returns None.
    """
    failure = run_embedding_probe(embedding_service=_FailingEmbeddingService())
    success = run_embedding_probe(embedding_service=_WorkingEmbeddingService())

    assert failure is not None
    assert "embed" in failure.lower()
    assert success is None
