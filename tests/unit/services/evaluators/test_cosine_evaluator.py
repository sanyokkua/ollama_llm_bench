"""Unit tests for CosineSimilarityEvaluator — Layer 3 cosine similarity checks."""

import logging

import pytest
from pytest_mock import MockerFixture

from ollama_llm_bench.backend.core.interfaces import EmbeddingProviderApi, EvaluatorApi
from ollama_llm_bench.backend.core.models import (
    BenchmarkResult,
    BenchmarkTask,
    Difficulty,
    EvalLayer,
    EvalVerdict,
    ResponseScope,
    TaskType,
)
from ollama_llm_bench.backend.services.evaluators.cosine_evaluator import (
    _SCOPE_THRESHOLDS,
    _SKIP_TASK_TYPES,
    CosineSimilarityEvaluator,
    _cosine_similarity,
)

# ---------------------------------------------------------------------------
# Helper factories
# ---------------------------------------------------------------------------


def _make_task(
    *,
    task_type: TaskType = TaskType.FACTUAL_QA,
    response_scope: ResponseScope | None = ResponseScope.CONTAINS,
    golden_answer: str = "Paris",
) -> BenchmarkTask:
    return BenchmarkTask(
        task_id="t1",
        category="geography",
        sub_category="capitals",
        task_type=task_type,
        question="What is the capital of France?",
        golden_answer=golden_answer,
        pass_criteria="",
        fail_criteria="",
        difficulty=Difficulty.EASY,
        response_scope=response_scope,
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
    def test_layer_returns_cosine(self, mocker: MockerFixture) -> None:
        mock_embedding = mocker.Mock(spec=EmbeddingProviderApi)
        evaluator = CosineSimilarityEvaluator(embedding_service=mock_embedding)
        assert evaluator.layer is EvalLayer.COSINE


class TestInterfaceConformance:
    def test_isinstance_check_passes(self, mocker: MockerFixture) -> None:
        mock_embedding = mocker.Mock(spec=EmbeddingProviderApi)
        evaluator = CosineSimilarityEvaluator(embedding_service=mock_embedding)
        assert isinstance(evaluator, EvaluatorApi)


class TestSkippedTaskTypes:
    def test_code_generation_returns_unknown_non_terminal(self, mocker: MockerFixture) -> None:
        mock_embedding = mocker.Mock(spec=EmbeddingProviderApi)
        evaluator = CosineSimilarityEvaluator(embedding_service=mock_embedding)
        task = _make_task(task_type=TaskType.CODE_GENERATION)
        result = _make_result(sanitized_response="some code")
        outcome = evaluator.evaluate(task, result)
        assert outcome.verdict is EvalVerdict.UNKNOWN
        assert outcome.is_terminal is False
        assert outcome.layer is EvalLayer.COSINE

    def test_code_review_returns_unknown_non_terminal(self, mocker: MockerFixture) -> None:
        mock_embedding = mocker.Mock(spec=EmbeddingProviderApi)
        evaluator = CosineSimilarityEvaluator(embedding_service=mock_embedding)
        task = _make_task(task_type=TaskType.CODE_REVIEW)
        result = _make_result(sanitized_response="looks good")
        outcome = evaluator.evaluate(task, result)
        assert outcome.verdict is EvalVerdict.UNKNOWN
        assert outcome.is_terminal is False

    def test_reasoning_returns_unknown_non_terminal(self, mocker: MockerFixture) -> None:
        mock_embedding = mocker.Mock(spec=EmbeddingProviderApi)
        evaluator = CosineSimilarityEvaluator(embedding_service=mock_embedding)
        task = _make_task(task_type=TaskType.REASONING)
        result = _make_result(sanitized_response="step by step")
        outcome = evaluator.evaluate(task, result)
        assert outcome.verdict is EvalVerdict.UNKNOWN
        assert outcome.is_terminal is False

    def test_skipped_type_does_not_call_embedding_service(self, mocker: MockerFixture) -> None:
        mock_embedding = mocker.Mock(spec=EmbeddingProviderApi)
        evaluator = CosineSimilarityEvaluator(embedding_service=mock_embedding)
        task = _make_task(task_type=TaskType.CODE_GENERATION)
        result = _make_result(sanitized_response="some code")
        evaluator.evaluate(task, result)
        mock_embedding.encode.assert_not_called()

    def test_skipped_type_reasoning_contains_task_type_name(self, mocker: MockerFixture) -> None:
        mock_embedding = mocker.Mock(spec=EmbeddingProviderApi)
        evaluator = CosineSimilarityEvaluator(embedding_service=mock_embedding)
        task = _make_task(task_type=TaskType.CODE_GENERATION)
        result = _make_result(sanitized_response="x = 1")
        outcome = evaluator.evaluate(task, result)
        assert "code_generation" in outcome.reasoning


class TestNonSkippedTaskTypes:
    def test_factual_qa_proceeds_to_embedding(self, mocker: MockerFixture) -> None:
        mock_embedding = mocker.Mock(spec=EmbeddingProviderApi)
        mock_embedding.encode.return_value = [[1.0, 0.0], [1.0, 0.0]]
        evaluator = CosineSimilarityEvaluator(embedding_service=mock_embedding)
        task = _make_task(task_type=TaskType.FACTUAL_QA)
        result = _make_result(sanitized_response="Paris")
        evaluator.evaluate(task, result)
        mock_embedding.encode.assert_called_once()

    def test_translation_proceeds_to_embedding(self, mocker: MockerFixture) -> None:
        mock_embedding = mocker.Mock(spec=EmbeddingProviderApi)
        mock_embedding.encode.return_value = [[1.0, 0.0], [1.0, 0.0]]
        evaluator = CosineSimilarityEvaluator(embedding_service=mock_embedding)
        task = _make_task(task_type=TaskType.TRANSLATION)
        result = _make_result(sanitized_response="Bonjour")
        evaluator.evaluate(task, result)
        mock_embedding.encode.assert_called_once()

    def test_summarization_proceeds_to_embedding(self, mocker: MockerFixture) -> None:
        mock_embedding = mocker.Mock(spec=EmbeddingProviderApi)
        mock_embedding.encode.return_value = [[1.0, 0.0], [1.0, 0.0]]
        evaluator = CosineSimilarityEvaluator(embedding_service=mock_embedding)
        task = _make_task(task_type=TaskType.SUMMARIZATION)
        result = _make_result(sanitized_response="summary text")
        evaluator.evaluate(task, result)
        mock_embedding.encode.assert_called_once()


class TestResponseScopeExact:
    def test_exact_scope_above_pass_threshold_returns_pass_terminal(self, mocker: MockerFixture) -> None:
        mock_embedding = mocker.Mock(spec=EmbeddingProviderApi)
        mock_embedding.encode.return_value = [[1.0, 0.0], [1.0, 0.0]]  # cosine = 1.0 >= 0.92
        evaluator = CosineSimilarityEvaluator(embedding_service=mock_embedding)
        task = _make_task(response_scope=ResponseScope.EXACT)
        result = _make_result(sanitized_response="Paris")
        outcome = evaluator.evaluate(task, result)
        assert outcome.verdict is EvalVerdict.PASS
        assert outcome.is_terminal is True
        assert outcome.score >= 0.92
        assert outcome.layer is EvalLayer.COSINE

    def test_exact_scope_below_fail_threshold_returns_fail_terminal(self, mocker: MockerFixture) -> None:
        mock_embedding = mocker.Mock(spec=EmbeddingProviderApi)
        mock_embedding.encode.return_value = [[1.0, 0.0], [0.0, 1.0]]  # cosine = 0.0 < 0.30
        evaluator = CosineSimilarityEvaluator(embedding_service=mock_embedding)
        task = _make_task(response_scope=ResponseScope.EXACT)
        result = _make_result(sanitized_response="London")
        outcome = evaluator.evaluate(task, result)
        assert outcome.verdict is EvalVerdict.FAIL
        assert outcome.is_terminal is True
        assert outcome.score == 0.0

    def test_exact_scope_between_thresholds_returns_unknown_non_terminal(self, mocker: MockerFixture) -> None:
        mock_embedding = mocker.Mock(spec=EmbeddingProviderApi)
        mock_embedding.encode.return_value = [[1.0, 0.0], [0.8, 0.6]]
        mocker.patch(
            "ollama_llm_bench.backend.services.evaluators.cosine_evaluator._cosine_similarity",
            return_value=0.80,  # between 0.30 and 0.92
        )
        evaluator = CosineSimilarityEvaluator(embedding_service=mock_embedding)
        task = _make_task(response_scope=ResponseScope.EXACT)
        result = _make_result(sanitized_response="Paris, France")
        outcome = evaluator.evaluate(task, result)
        assert outcome.verdict is EvalVerdict.UNKNOWN
        assert outcome.is_terminal is False


class TestResponseScopeContains:
    def test_contains_scope_above_pass_threshold_returns_pass_terminal(self, mocker: MockerFixture) -> None:
        mock_embedding = mocker.Mock(spec=EmbeddingProviderApi)
        mock_embedding.encode.return_value = [[1.0, 0.0], [1.0, 0.0]]  # cosine = 1.0 >= 0.85
        evaluator = CosineSimilarityEvaluator(embedding_service=mock_embedding)
        task = _make_task(response_scope=ResponseScope.CONTAINS)
        result = _make_result(sanitized_response="Paris")
        outcome = evaluator.evaluate(task, result)
        assert outcome.verdict is EvalVerdict.PASS
        assert outcome.is_terminal is True

    def test_contains_scope_below_fail_threshold_returns_fail_terminal(self, mocker: MockerFixture) -> None:
        mock_embedding = mocker.Mock(spec=EmbeddingProviderApi)
        mock_embedding.encode.return_value = [[1.0, 0.0], [0.0, 1.0]]  # cosine = 0.0 < 0.25
        evaluator = CosineSimilarityEvaluator(embedding_service=mock_embedding)
        task = _make_task(response_scope=ResponseScope.CONTAINS)
        result = _make_result(sanitized_response="London")
        outcome = evaluator.evaluate(task, result)
        assert outcome.verdict is EvalVerdict.FAIL
        assert outcome.is_terminal is True

    def test_contains_scope_between_thresholds_returns_unknown_non_terminal(self, mocker: MockerFixture) -> None:
        mock_embedding = mocker.Mock(spec=EmbeddingProviderApi)
        mock_embedding.encode.return_value = [[1.0, 0.0], [0.8, 0.6]]
        mocker.patch(
            "ollama_llm_bench.backend.services.evaluators.cosine_evaluator._cosine_similarity",
            return_value=0.60,  # between 0.25 and 0.85
        )
        evaluator = CosineSimilarityEvaluator(embedding_service=mock_embedding)
        task = _make_task(response_scope=ResponseScope.CONTAINS)
        result = _make_result(sanitized_response="Paris area")
        outcome = evaluator.evaluate(task, result)
        assert outcome.verdict is EvalVerdict.UNKNOWN
        assert outcome.is_terminal is False


class TestResponseScopeCovers:
    def test_covers_scope_above_pass_threshold_returns_pass_terminal(self, mocker: MockerFixture) -> None:
        mock_embedding = mocker.Mock(spec=EmbeddingProviderApi)
        mock_embedding.encode.return_value = [[1.0, 0.0], [1.0, 0.0]]  # cosine = 1.0 >= 0.75
        evaluator = CosineSimilarityEvaluator(embedding_service=mock_embedding)
        task = _make_task(response_scope=ResponseScope.COVERS)
        result = _make_result(sanitized_response="Paris")
        outcome = evaluator.evaluate(task, result)
        assert outcome.verdict is EvalVerdict.PASS
        assert outcome.is_terminal is True

    def test_covers_scope_below_fail_threshold_returns_fail_terminal(self, mocker: MockerFixture) -> None:
        mock_embedding = mocker.Mock(spec=EmbeddingProviderApi)
        mock_embedding.encode.return_value = [[1.0, 0.0], [0.0, 1.0]]  # cosine = 0.0 < 0.20
        evaluator = CosineSimilarityEvaluator(embedding_service=mock_embedding)
        task = _make_task(response_scope=ResponseScope.COVERS)
        result = _make_result(sanitized_response="Berlin")
        outcome = evaluator.evaluate(task, result)
        assert outcome.verdict is EvalVerdict.FAIL
        assert outcome.is_terminal is True

    def test_covers_scope_between_thresholds_returns_unknown_non_terminal(self, mocker: MockerFixture) -> None:
        mock_embedding = mocker.Mock(spec=EmbeddingProviderApi)
        mock_embedding.encode.return_value = [[1.0, 0.0], [0.8, 0.6]]
        mocker.patch(
            "ollama_llm_bench.backend.services.evaluators.cosine_evaluator._cosine_similarity",
            return_value=0.50,  # between 0.20 and 0.75
        )
        evaluator = CosineSimilarityEvaluator(embedding_service=mock_embedding)
        task = _make_task(response_scope=ResponseScope.COVERS)
        result = _make_result(sanitized_response="French city")
        outcome = evaluator.evaluate(task, result)
        assert outcome.verdict is EvalVerdict.UNKNOWN
        assert outcome.is_terminal is False


class TestNoneResponseScope:
    def test_none_scope_defaults_to_contains_thresholds_pass(self, mocker: MockerFixture) -> None:
        mock_embedding = mocker.Mock(spec=EmbeddingProviderApi)
        mock_embedding.encode.return_value = [[1.0, 0.0], [1.0, 0.0]]  # cosine = 1.0 >= 0.85 (CONTAINS)
        evaluator = CosineSimilarityEvaluator(embedding_service=mock_embedding)
        task = _make_task(response_scope=None)
        result = _make_result(sanitized_response="Paris")
        outcome = evaluator.evaluate(task, result)
        assert outcome.verdict is EvalVerdict.PASS
        assert outcome.layer is EvalLayer.COSINE

    def test_none_scope_defaults_to_contains_thresholds_fail(self, mocker: MockerFixture) -> None:
        mock_embedding = mocker.Mock(spec=EmbeddingProviderApi)
        mock_embedding.encode.return_value = [[1.0, 0.0], [0.8, 0.6]]
        mocker.patch(
            "ollama_llm_bench.backend.services.evaluators.cosine_evaluator._cosine_similarity",
            return_value=0.20,  # < 0.25 (CONTAINS fail threshold)
        )
        evaluator = CosineSimilarityEvaluator(embedding_service=mock_embedding)
        task = _make_task(response_scope=None)
        result = _make_result(sanitized_response="Rome")
        outcome = evaluator.evaluate(task, result)
        assert outcome.verdict is EvalVerdict.FAIL
        assert outcome.is_terminal is True

    def test_none_scope_defaults_to_contains_thresholds_unknown(self, mocker: MockerFixture) -> None:
        mock_embedding = mocker.Mock(spec=EmbeddingProviderApi)
        mock_embedding.encode.return_value = [[1.0, 0.0], [0.8, 0.6]]
        mocker.patch(
            "ollama_llm_bench.backend.services.evaluators.cosine_evaluator._cosine_similarity",
            return_value=0.60,  # between 0.25-0.85 (CONTAINS thresholds)
        )
        evaluator = CosineSimilarityEvaluator(embedding_service=mock_embedding)
        task = _make_task(response_scope=None)
        result = _make_result(sanitized_response="French capital")
        outcome = evaluator.evaluate(task, result)
        assert outcome.verdict is EvalVerdict.UNKNOWN
        assert outcome.is_terminal is False


class TestEmbeddingErrorFallback:
    def test_embedding_error_returns_unknown_non_terminal(self, mocker: MockerFixture) -> None:
        mock_embedding = mocker.Mock(spec=EmbeddingProviderApi)
        mock_embedding.encode.side_effect = RuntimeError("timeout")
        evaluator = CosineSimilarityEvaluator(embedding_service=mock_embedding)
        task = _make_task()
        result = _make_result(sanitized_response="Paris")
        outcome = evaluator.evaluate(task, result)
        assert outcome.verdict is EvalVerdict.UNKNOWN
        assert outcome.is_terminal is False

    def test_embedding_error_does_not_raise(self, mocker: MockerFixture) -> None:
        mock_embedding = mocker.Mock(spec=EmbeddingProviderApi)
        mock_embedding.encode.side_effect = Exception("any error")
        evaluator = CosineSimilarityEvaluator(embedding_service=mock_embedding)
        task = _make_task()
        result = _make_result(sanitized_response="Paris")
        # Should not raise
        outcome = evaluator.evaluate(task, result)
        assert outcome is not None

    def test_embedding_error_logs_warning(self, mocker: MockerFixture, caplog: pytest.LogCaptureFixture) -> None:
        mock_embedding = mocker.Mock(spec=EmbeddingProviderApi)
        mock_embedding.encode.side_effect = RuntimeError("connection refused")
        evaluator = CosineSimilarityEvaluator(embedding_service=mock_embedding)
        task = _make_task()
        result = _make_result(sanitized_response="Paris")
        with caplog.at_level(
            logging.WARNING,
            logger="ollama_llm_bench.backend.services.evaluators.cosine_evaluator",
        ):
            evaluator.evaluate(task, result)
        assert any(r.levelno >= logging.WARNING for r in caplog.records)


class TestResponseTextFallback:
    def test_uses_sanitized_response_when_available(self, mocker: MockerFixture) -> None:
        mock_embedding = mocker.Mock(spec=EmbeddingProviderApi)
        mock_embedding.encode.return_value = [[1.0, 0.0], [1.0, 0.0]]
        evaluator = CosineSimilarityEvaluator(embedding_service=mock_embedding)
        task = _make_task(golden_answer="Paris")
        result = _make_result(sanitized_response="sanitized", raw_response="raw")
        evaluator.evaluate(task, result)
        mock_embedding.encode.assert_called_once_with(["Paris", "sanitized"])

    def test_falls_back_to_raw_response_when_sanitized_is_none(self, mocker: MockerFixture) -> None:
        mock_embedding = mocker.Mock(spec=EmbeddingProviderApi)
        mock_embedding.encode.return_value = [[1.0, 0.0], [1.0, 0.0]]
        evaluator = CosineSimilarityEvaluator(embedding_service=mock_embedding)
        task = _make_task(golden_answer="Paris")
        result = _make_result(sanitized_response=None, raw_response="raw")
        evaluator.evaluate(task, result)
        mock_embedding.encode.assert_called_once_with(["Paris", "raw"])

    def test_uses_empty_string_when_both_responses_are_none(self, mocker: MockerFixture) -> None:
        mock_embedding = mocker.Mock(spec=EmbeddingProviderApi)
        mock_embedding.encode.return_value = [[1.0, 0.0], [1.0, 0.0]]
        evaluator = CosineSimilarityEvaluator(embedding_service=mock_embedding)
        task = _make_task(golden_answer="Paris")
        result = _make_result(sanitized_response=None, raw_response=None)
        evaluator.evaluate(task, result)
        mock_embedding.encode.assert_called_once_with(["Paris", ""])


class TestEncodeCallStructure:
    def test_encode_called_with_golden_and_response_in_single_call(self, mocker: MockerFixture) -> None:
        mock_embedding = mocker.Mock(spec=EmbeddingProviderApi)
        mock_embedding.encode.return_value = [[1.0, 0.0], [1.0, 0.0]]
        evaluator = CosineSimilarityEvaluator(embedding_service=mock_embedding)
        task = _make_task(golden_answer="Paris")
        result = _make_result(sanitized_response="sanitized answer")
        evaluator.evaluate(task, result)
        mock_embedding.encode.assert_called_once_with(["Paris", "sanitized answer"])

    def test_uses_index_zero_for_golden_and_index_one_for_response(self, mocker: MockerFixture) -> None:
        mock_embedding = mocker.Mock(spec=EmbeddingProviderApi)
        golden_vec = [1.0, 0.0]
        response_vec = [0.8, 0.6]
        mock_embedding.encode.return_value = [golden_vec, response_vec]
        captured: list[tuple[list[float], list[float]]] = []
        original_cosine = _cosine_similarity

        def capturing_cosine(a: list[float], b: list[float]) -> float:
            captured.append((a, b))
            return original_cosine(a, b)

        mocker.patch(
            "ollama_llm_bench.backend.services.evaluators.cosine_evaluator._cosine_similarity",
            side_effect=capturing_cosine,
        )
        evaluator = CosineSimilarityEvaluator(embedding_service=mock_embedding)
        task = _make_task(golden_answer="Paris")
        result = _make_result(sanitized_response="Paris is the capital")
        evaluator.evaluate(task, result)
        assert len(captured) == 1
        assert captured[0][0] == golden_vec
        assert captured[0][1] == response_vec


class TestCosineSimFunction:
    def test_identical_vectors_return_one(self) -> None:
        a = [1.0, 0.0, 0.0]
        result = _cosine_similarity(a, a)
        assert abs(result - 1.0) < 1e-9

    def test_orthogonal_vectors_return_zero(self) -> None:
        result = _cosine_similarity([1.0, 0.0], [0.0, 1.0])
        assert abs(result) < 1e-9

    def test_zero_norm_vector_returns_zero(self) -> None:
        result = _cosine_similarity([0.0, 0.0], [1.0, 0.5])
        assert result == 0.0

    def test_both_zero_vectors_return_zero(self) -> None:
        result = _cosine_similarity([0.0, 0.0], [0.0, 0.0])
        assert result == 0.0

    def test_known_angle_returns_expected_value(self) -> None:
        result = _cosine_similarity([1.0, 1.0], [1.0, 0.0])
        assert abs(result - 0.7071) < 1e-4


class TestConstants:
    def test_skip_task_types_contains_code_generation(self) -> None:
        assert TaskType.CODE_GENERATION in _SKIP_TASK_TYPES

    def test_skip_task_types_contains_code_review(self) -> None:
        assert TaskType.CODE_REVIEW in _SKIP_TASK_TYPES

    def test_skip_task_types_contains_reasoning(self) -> None:
        assert TaskType.REASONING in _SKIP_TASK_TYPES

    def test_skip_task_types_does_not_contain_factual_qa(self) -> None:
        assert TaskType.FACTUAL_QA not in _SKIP_TASK_TYPES

    def test_scope_thresholds_has_all_three_scopes(self) -> None:
        assert ResponseScope.EXACT in _SCOPE_THRESHOLDS
        assert ResponseScope.CONTAINS in _SCOPE_THRESHOLDS
        assert ResponseScope.COVERS in _SCOPE_THRESHOLDS

    def test_exact_scope_thresholds_values(self) -> None:
        assert _SCOPE_THRESHOLDS[ResponseScope.EXACT] == (0.92, 0.30)

    def test_contains_scope_thresholds_values(self) -> None:
        assert _SCOPE_THRESHOLDS[ResponseScope.CONTAINS] == (0.85, 0.25)

    def test_covers_scope_thresholds_values(self) -> None:
        assert _SCOPE_THRESHOLDS[ResponseScope.COVERS] == (0.75, 0.20)

    def test_pass_threshold_greater_than_fail_threshold_for_all_scopes(self) -> None:
        for scope, (pass_t, fail_t) in _SCOPE_THRESHOLDS.items():
            assert pass_t > fail_t, f"pass_t={pass_t} <= fail_t={fail_t} for {scope}"
