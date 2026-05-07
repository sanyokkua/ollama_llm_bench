"""Unit tests for KeywordEvaluator — Layer 2 keyword and semantic term checks."""

import pytest
from pytest_mock import MockerFixture

from ollama_llm_bench.backend.core.interfaces import EmbeddingProviderApi, EvaluatorApi
from ollama_llm_bench.backend.core.models import (
    BenchmarkResult,
    BenchmarkTask,
    Difficulty,
    EvalLayer,
    EvalVerdict,
    RequiredTerms,
    ResponseScope,
    TaskType,
)
from ollama_llm_bench.backend.services.evaluators.keyword_evaluator import (
    _SEMANTIC_FAIL_THRESHOLD,
    _SEMANTIC_PASS_THRESHOLD,
    KeywordEvaluator,
    _cosine_similarity,
)

# ---------------------------------------------------------------------------
# Helper factories
# ---------------------------------------------------------------------------


def _make_task(
    *,
    required_terms: RequiredTerms | None = None,
    question: str = "What is the capital of France?",
) -> BenchmarkTask:
    return BenchmarkTask(
        task_id="t1",
        category="geography",
        sub_category="capitals",
        task_type=TaskType.FACTUAL_QA,
        question=question,
        golden_answer="Paris",
        pass_criteria="",
        fail_criteria="",
        difficulty=Difficulty.EASY,
        response_scope=ResponseScope.CONTAINS,
        required_terms=required_terms,
    )


def _make_result(
    *,
    sanitized_response: str | None = None,
    raw_response: str | None = None,
) -> BenchmarkResult:
    return BenchmarkResult(
        sanitized_response=sanitized_response,
        raw_response=raw_response,
    )


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------


class TestLayerProperty:
    def test_layer_returns_keyword(self, mocker: MockerFixture) -> None:
        mock_embedding = mocker.Mock(spec=EmbeddingProviderApi)
        evaluator = KeywordEvaluator(embedding_service=mock_embedding)
        assert evaluator.layer is EvalLayer.KEYWORD


class TestInterfaceConformance:
    def test_isinstance_check_passes(self, mocker: MockerFixture) -> None:
        mock_embedding = mocker.Mock(spec=EmbeddingProviderApi)
        evaluator = KeywordEvaluator(embedding_service=mock_embedding)
        assert isinstance(evaluator, EvaluatorApi)


class TestEmptyRequiredTerms:
    def test_required_terms_is_none_returns_unknown_non_terminal(self, mocker: MockerFixture) -> None:
        mock_embedding = mocker.Mock(spec=EmbeddingProviderApi)
        evaluator = KeywordEvaluator(embedding_service=mock_embedding)
        task = _make_task(required_terms=None)
        result = _make_result(sanitized_response="Paris is the capital.")

        outcome = evaluator.evaluate(task, result)

        assert outcome.verdict is EvalVerdict.UNKNOWN
        assert outcome.is_terminal is False

    def test_required_terms_all_empty_tuples_returns_unknown_non_terminal(self, mocker: MockerFixture) -> None:
        mock_embedding = mocker.Mock(spec=EmbeddingProviderApi)
        evaluator = KeywordEvaluator(embedding_service=mock_embedding)
        task = _make_task(required_terms=RequiredTerms(exact=(), semantic=(), forbidden=()))
        result = _make_result(sanitized_response="Paris is the capital.")

        outcome = evaluator.evaluate(task, result)

        assert outcome.verdict is EvalVerdict.UNKNOWN
        assert outcome.is_terminal is False

    def test_empty_required_terms_does_not_call_embedding_service(self, mocker: MockerFixture) -> None:
        mock_embedding = mocker.Mock(spec=EmbeddingProviderApi)
        evaluator = KeywordEvaluator(embedding_service=mock_embedding)
        task = _make_task(required_terms=None)
        result = _make_result(sanitized_response="Paris is the capital.")

        evaluator.evaluate(task, result)

        mock_embedding.encode.assert_not_called()


class TestForbiddenTermCheck:
    def test_forbidden_term_found_returns_terminal_fail(self, mocker: MockerFixture) -> None:
        mock_embedding = mocker.Mock(spec=EmbeddingProviderApi)
        evaluator = KeywordEvaluator(embedding_service=mock_embedding)
        task = _make_task(required_terms=RequiredTerms(forbidden=("wrong",)))
        result = _make_result(sanitized_response="This answer is wrong unfortunately.")

        outcome = evaluator.evaluate(task, result)

        assert outcome.verdict is EvalVerdict.FAIL
        assert outcome.is_terminal is True
        assert outcome.score == 0.0
        assert outcome.layer is EvalLayer.KEYWORD
        assert "wrong" in outcome.reasoning
        assert len(outcome.found_forbidden_terms) > 0
        assert "wrong" in outcome.found_forbidden_terms

    def test_forbidden_term_check_is_case_insensitive(self, mocker: MockerFixture) -> None:
        mock_embedding = mocker.Mock(spec=EmbeddingProviderApi)
        evaluator = KeywordEvaluator(embedding_service=mock_embedding)
        task = _make_task(required_terms=RequiredTerms(forbidden=("WRONG",)))
        result = _make_result(sanitized_response="This answer is wrong unfortunately.")

        outcome = evaluator.evaluate(task, result)

        assert outcome.verdict is EvalVerdict.FAIL
        assert outcome.is_terminal is True

    def test_forbidden_term_not_found_continues_pipeline(self, mocker: MockerFixture) -> None:
        mock_embedding = mocker.Mock(spec=EmbeddingProviderApi)
        evaluator = KeywordEvaluator(embedding_service=mock_embedding)
        # No exact or semantic terms either — should return UNKNOWN (no required terms active)
        task = _make_task(required_terms=RequiredTerms(forbidden=("forbidden_word",)))
        result = _make_result(sanitized_response="Paris is the capital of France.")

        outcome = evaluator.evaluate(task, result)

        # Forbidden term not found, no exact/semantic — falls through to UNKNOWN
        assert outcome.verdict is EvalVerdict.UNKNOWN
        assert outcome.is_terminal is False

    def test_forbidden_match_does_not_call_embedding_service(self, mocker: MockerFixture) -> None:
        mock_embedding = mocker.Mock(spec=EmbeddingProviderApi)
        evaluator = KeywordEvaluator(embedding_service=mock_embedding)
        task = _make_task(required_terms=RequiredTerms(forbidden=("error",)))
        result = _make_result(sanitized_response="There was an error in this response.")

        evaluator.evaluate(task, result)

        mock_embedding.encode.assert_not_called()

    def test_first_forbidden_term_triggers_fail(self, mocker: MockerFixture) -> None:
        mock_embedding = mocker.Mock(spec=EmbeddingProviderApi)
        evaluator = KeywordEvaluator(embedding_service=mock_embedding)
        task = _make_task(required_terms=RequiredTerms(forbidden=("alpha", "beta", "gamma")))
        # "alpha" is the first term — it appears in the response
        result = _make_result(sanitized_response="The response mentions alpha here.")

        outcome = evaluator.evaluate(task, result)

        assert outcome.verdict is EvalVerdict.FAIL
        assert "alpha" in outcome.reasoning


class TestExactTermCheck:
    def test_missing_exact_term_returns_terminal_fail(self, mocker: MockerFixture) -> None:
        mock_embedding = mocker.Mock(spec=EmbeddingProviderApi)
        evaluator = KeywordEvaluator(embedding_service=mock_embedding)
        task = _make_task(required_terms=RequiredTerms(exact=("paris",)))
        result = _make_result(sanitized_response="The capital is a beautiful city.")

        outcome = evaluator.evaluate(task, result)

        assert outcome.verdict is EvalVerdict.FAIL
        assert outcome.is_terminal is True
        assert outcome.score == 0.0
        assert len(outcome.missing_exact_terms) > 0
        assert "paris" in outcome.missing_exact_terms

    def test_exact_term_check_is_case_insensitive(self, mocker: MockerFixture) -> None:
        mock_embedding = mocker.Mock(spec=EmbeddingProviderApi)
        evaluator = KeywordEvaluator(embedding_service=mock_embedding)
        task = _make_task(required_terms=RequiredTerms(exact=("PARIS",)))
        result = _make_result(sanitized_response="paris is the answer here.")

        outcome = evaluator.evaluate(task, result)

        # "PARIS".lower() == "paris" which is in the lowercased response
        assert outcome.verdict is not EvalVerdict.FAIL or "paris" not in outcome.reasoning.lower()

    def test_all_exact_terms_present_no_semantic_returns_unknown(self, mocker: MockerFixture) -> None:
        mock_embedding = mocker.Mock(spec=EmbeddingProviderApi)
        evaluator = KeywordEvaluator(embedding_service=mock_embedding)
        task = _make_task(required_terms=RequiredTerms(exact=("paris", "france"), semantic=()))
        result = _make_result(sanitized_response="Paris is the capital of France.")

        outcome = evaluator.evaluate(task, result)

        assert outcome.verdict is EvalVerdict.UNKNOWN
        assert outcome.is_terminal is False

    def test_missing_exact_does_not_call_embedding_service(self, mocker: MockerFixture) -> None:
        mock_embedding = mocker.Mock(spec=EmbeddingProviderApi)
        evaluator = KeywordEvaluator(embedding_service=mock_embedding)
        task = _make_task(required_terms=RequiredTerms(exact=("required_term",)))
        result = _make_result(sanitized_response="No relevant content here at all.")

        evaluator.evaluate(task, result)

        mock_embedding.encode.assert_not_called()

    def test_multiple_exact_terms_one_missing_reports_in_reasoning(self, mocker: MockerFixture) -> None:
        mock_embedding = mocker.Mock(spec=EmbeddingProviderApi)
        evaluator = KeywordEvaluator(embedding_service=mock_embedding)
        task = _make_task(required_terms=RequiredTerms(exact=("paris", "capital", "missing_term")))
        result = _make_result(sanitized_response="Paris is the capital of France.")

        outcome = evaluator.evaluate(task, result)

        assert outcome.verdict is EvalVerdict.FAIL
        assert "missing_term" in outcome.reasoning

    def test_exact_term_found_in_raw_response_when_sanitized_is_none(self, mocker: MockerFixture) -> None:
        mock_embedding = mocker.Mock(spec=EmbeddingProviderApi)
        evaluator = KeywordEvaluator(embedding_service=mock_embedding)
        task = _make_task(required_terms=RequiredTerms(exact=("paris", "france"), semantic=()))
        result = _make_result(
            sanitized_response=None,
            raw_response="Paris is the capital of France.",
        )

        outcome = evaluator.evaluate(task, result)

        assert outcome.verdict is EvalVerdict.UNKNOWN
        assert outcome.is_terminal is False


class TestSemanticCheck:
    def test_semantic_avg_above_pass_threshold_returns_pass_terminal(self, mocker: MockerFixture) -> None:
        mock_embedding = mocker.Mock(spec=EmbeddingProviderApi)
        # Two identical vectors → cosine similarity = 1.0 → avg = 1.0 ≥ 0.70
        mock_embedding.encode.return_value = [[1.0, 0.0], [1.0, 0.0]]
        evaluator = KeywordEvaluator(embedding_service=mock_embedding)
        task = _make_task(required_terms=RequiredTerms(semantic=("capital city",)))
        result = _make_result(sanitized_response="Paris is the capital city of France.")

        outcome = evaluator.evaluate(task, result)

        assert outcome.verdict is EvalVerdict.PASS
        assert outcome.is_terminal is True
        assert outcome.score >= _SEMANTIC_PASS_THRESHOLD
        assert outcome.layer is EvalLayer.KEYWORD
        assert len(outcome.semantic_term_scores) > 0
        assert all(isinstance(s, float) for s in outcome.semantic_term_scores)

    def test_semantic_avg_below_fail_threshold_returns_fail_terminal(self, mocker: MockerFixture) -> None:
        mock_embedding = mocker.Mock(spec=EmbeddingProviderApi)
        # Orthogonal vectors → cosine similarity = 0.0 < 0.40
        mock_embedding.encode.return_value = [[1.0, 0.0], [0.0, 1.0]]
        evaluator = KeywordEvaluator(embedding_service=mock_embedding)
        task = _make_task(required_terms=RequiredTerms(semantic=("capital city",)))
        result = _make_result(sanitized_response="Completely unrelated answer.")

        outcome = evaluator.evaluate(task, result)

        assert outcome.verdict is EvalVerdict.FAIL
        assert outcome.is_terminal is True
        assert outcome.score == 0.0
        assert len(outcome.semantic_term_scores) > 0
        assert all(isinstance(s, float) for s in outcome.semantic_term_scores)

    def test_semantic_between_thresholds_returns_unknown_non_terminal(self, mocker: MockerFixture) -> None:
        mock_embedding = mocker.Mock(spec=EmbeddingProviderApi)
        # avg_sim = 0.55 — between 0.40 and 0.70
        mock_embedding.encode.return_value = [[1.0, 0.0], [0.8, 0.6]]
        mocker.patch(
            "ollama_llm_bench.backend.services.evaluators.keyword_evaluator._cosine_similarity",
            return_value=0.55,
        )
        evaluator = KeywordEvaluator(embedding_service=mock_embedding)
        task = _make_task(required_terms=RequiredTerms(semantic=("some term",)))
        result = _make_result(sanitized_response="A moderately relevant response here.")

        outcome = evaluator.evaluate(task, result)

        assert outcome.verdict is EvalVerdict.UNKNOWN
        assert outcome.is_terminal is False
        assert "0.550" in outcome.reasoning
        assert len(outcome.semantic_term_scores) > 0
        assert all(isinstance(s, float) for s in outcome.semantic_term_scores)

    def test_semantic_encoding_error_logs_warning_and_returns_unknown(self, mocker: MockerFixture) -> None:
        mock_embedding = mocker.Mock(spec=EmbeddingProviderApi)
        mock_embedding.encode.side_effect = RuntimeError("connection refused")
        evaluator = KeywordEvaluator(embedding_service=mock_embedding)
        task = _make_task(required_terms=RequiredTerms(semantic=("capital city",)))
        result = _make_result(sanitized_response="Paris is the capital.")

        outcome = evaluator.evaluate(task, result)

        assert outcome.verdict is EvalVerdict.UNKNOWN
        assert outcome.is_terminal is False
        assert "embedding error" in outcome.reasoning.lower()

    def test_semantic_encodes_response_and_all_terms_in_one_call(self, mocker: MockerFixture) -> None:
        mock_embedding = mocker.Mock(spec=EmbeddingProviderApi)
        # Three embeddings: response + 2 terms → all identical → pass
        mock_embedding.encode.return_value = [
            [1.0, 0.0],
            [1.0, 0.0],
            [1.0, 0.0],
        ]
        evaluator = KeywordEvaluator(embedding_service=mock_embedding)
        terms = ("capital", "france")
        task = _make_task(required_terms=RequiredTerms(semantic=terms))
        response_text = "Paris is the capital of France."
        result = _make_result(sanitized_response=response_text)

        evaluator.evaluate(task, result)

        mock_embedding.encode.assert_called_once_with([response_text, "capital", "france"])


class TestCosineSimFunction:
    def test_identical_vectors_return_one(self) -> None:
        a = [1.0, 0.0, 0.0]
        result = _cosine_similarity(a, a)
        assert abs(result - 1.0) < 1e-9

    def test_orthogonal_vectors_return_zero(self) -> None:
        a = [1.0, 0.0]
        b = [0.0, 1.0]
        result = _cosine_similarity(a, b)
        assert abs(result - 0.0) < 1e-9

    def test_zero_norm_vector_returns_zero(self) -> None:
        a = [0.0, 0.0]
        b = [1.0, 0.5]
        result = _cosine_similarity(a, b)
        assert result == 0.0

    def test_both_zero_vectors_return_zero(self) -> None:
        a = [0.0, 0.0]
        b = [0.0, 0.0]
        result = _cosine_similarity(a, b)
        assert result == 0.0


class TestResponseTextFallback:
    def test_uses_sanitized_response_when_available(self, mocker: MockerFixture) -> None:
        mock_embedding = mocker.Mock(spec=EmbeddingProviderApi)
        mock_embedding.encode.return_value = [[1.0, 0.0], [1.0, 0.0]]
        evaluator = KeywordEvaluator(embedding_service=mock_embedding)
        task = _make_task(required_terms=RequiredTerms(semantic=("term",)))
        sanitized = "Clean sanitized response about Paris."
        result = _make_result(
            sanitized_response=sanitized,
            raw_response="Raw response with noise.",
        )

        evaluator.evaluate(task, result)

        # The first argument to encode should be the sanitized response
        call_args = mock_embedding.encode.call_args[0][0]
        assert call_args[0] == sanitized

    def test_falls_back_to_raw_response_when_sanitized_is_none(self, mocker: MockerFixture) -> None:
        mock_embedding = mocker.Mock(spec=EmbeddingProviderApi)
        mock_embedding.encode.return_value = [[1.0, 0.0], [1.0, 0.0]]
        evaluator = KeywordEvaluator(embedding_service=mock_embedding)
        task = _make_task(required_terms=RequiredTerms(semantic=("term",)))
        raw = "Raw response used as fallback for Paris."
        result = _make_result(sanitized_response=None, raw_response=raw)

        evaluator.evaluate(task, result)

        call_args = mock_embedding.encode.call_args[0][0]
        assert call_args[0] == raw

    def test_empty_response_with_exact_terms_returns_fail(self, mocker: MockerFixture) -> None:
        mock_embedding = mocker.Mock(spec=EmbeddingProviderApi)
        evaluator = KeywordEvaluator(embedding_service=mock_embedding)
        task = _make_task(required_terms=RequiredTerms(exact=("paris",)))
        result = _make_result(sanitized_response=None, raw_response=None)

        outcome = evaluator.evaluate(task, result)

        assert outcome.verdict is EvalVerdict.FAIL
        assert outcome.is_terminal is True


class TestThresholdConstants:
    def test_pass_threshold_value(self) -> None:
        assert pytest.approx(0.70) == _SEMANTIC_PASS_THRESHOLD

    def test_fail_threshold_value(self) -> None:
        assert pytest.approx(0.40) == _SEMANTIC_FAIL_THRESHOLD
