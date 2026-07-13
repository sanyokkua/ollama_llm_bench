"""Tests for backend/evaluation/_internal/cosine.py."""

import pytest

from ollama_llm_bench.backend.embedding.testing import FakeEmbeddingService
from ollama_llm_bench.backend.evaluation._internal.cosine import _CosineEvaluatorImpl


def test_cosine_disabled_skips_and_leaves_both_fields_none() -> None:
    """Proves: STORY-028-AC-3

    cosine_enabled=false performs no cosine computation.
    """
    evaluator = _CosineEvaluatorImpl(embedding_service=FakeEmbeddingService())

    result = evaluator.evaluate(response="Paris", golden_answer="Paris", cosine_enabled=False)

    assert result.verdict is None
    assert result.similarity is None


def test_no_golden_answer_skips_and_leaves_both_fields_none() -> None:
    """Proves: STORY-028-AC-3

    A missing golden_answer performs no cosine computation, even when
    cosine_enabled is true.
    """
    evaluator = _CosineEvaluatorImpl(embedding_service=FakeEmbeddingService())

    result = evaluator.evaluate(response="Paris", golden_answer=None, cosine_enabled=True)

    assert result.verdict is None
    assert result.similarity is None


def test_score_at_or_above_threshold_passes() -> None:
    """Proves: STORY-028-AC-3

    An identical response/golden pair scores 1.0 and always clears the
    threshold, always storing the numeric similarity.
    """
    evaluator = _CosineEvaluatorImpl(embedding_service=FakeEmbeddingService(cosine_threshold=0.85))

    result = evaluator.evaluate(response="Paris", golden_answer="Paris", cosine_enabled=True)

    assert result.verdict is not None
    assert result.verdict.value == "pass"
    assert result.similarity == pytest.approx(1.0)


def test_score_below_threshold_fails() -> None:
    """Proves: STORY-028-AC-3

    A response/golden pair failing to clear a threshold of 1.0 (anything
    short of an identical string) fails, still storing the numeric score.
    """
    evaluator = _CosineEvaluatorImpl(embedding_service=FakeEmbeddingService(cosine_threshold=1.0))

    result = evaluator.evaluate(
        response="Lyon", golden_answer="Paris, the capital of France", cosine_enabled=True
    )

    assert result.verdict is not None
    assert result.verdict.value == "fail"
    assert result.similarity is not None
