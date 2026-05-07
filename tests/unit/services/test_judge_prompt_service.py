"""Unit tests for JudgePromptService — prompt building, task-type routing, and Protocol conformance."""

import pytest

from ollama_llm_bench.backend.core.models import (
    BenchmarkResult,
    BenchmarkTask,
    TaskType,
)
from ollama_llm_bench.backend.services.judge_prompt_service import (
    _CODE_JUDGE_SYSTEM_PROMPT,
    _DATA_EXTRACTION_JUDGE_SYSTEM_PROMPT,
    _DEFAULT_JUDGE_SYSTEM_PROMPT,
    _FACTUAL_QA_JUDGE_SYSTEM_PROMPT,
    _REASONING_JUDGE_SYSTEM_PROMPT,
    _REWRITE_SUMMARIZATION_JUDGE_SYSTEM_PROMPT,
    _TRANSLATION_JUDGE_SYSTEM_PROMPT,
    JudgePromptService,
)

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


@pytest.fixture
def service() -> JudgePromptService:
    return JudgePromptService()


def _make_task(task_type: TaskType = TaskType.FACTUAL_QA, **overrides: object) -> BenchmarkTask:
    """Build a minimal valid BenchmarkTask for the given task type."""
    from typing import Any

    defaults: dict[str, Any] = {
        "task_id": "test_task_001",
        "category": "test",
        "sub_category": "unit",
        "task_type": task_type,
        "question": "What is 2 + 2?",
        "golden_answer": "4",
        "pass_criteria": "Answer is exactly 4",
        "fail_criteria": "Answer is not 4",
    }
    defaults.update(overrides)
    return BenchmarkTask(**defaults)


def _make_result(
    sanitized_response: str | None = "The answer is 4.",
    raw_response: str | None = None,
) -> BenchmarkResult:
    """Build a minimal BenchmarkResult with controllable response fields."""
    return BenchmarkResult(
        sanitized_response=sanitized_response,
        raw_response=raw_response,
    )


# ---------------------------------------------------------------------------
# TestBuildInferencePrompt
# ---------------------------------------------------------------------------


class TestBuildInferencePrompt:
    def test_returns_question_as_user_prompt(self, service: JudgePromptService) -> None:
        # Arrange
        task = _make_task(question="What is the capital of France?")

        # Act
        user, _ = service.build_inference_prompt(task)

        # Assert
        assert user == "What is the capital of France?"

    def test_returns_empty_string_as_system_prompt(self, service: JudgePromptService) -> None:
        # Arrange
        task = _make_task()

        # Act
        _, system = service.build_inference_prompt(task)

        # Assert
        assert system == ""

    def test_returns_question_unchanged_for_multiline_question(self, service: JudgePromptService) -> None:
        # Arrange
        multiline = "Line one.\nLine two.\nLine three."
        task = _make_task(question=multiline)

        # Act
        user, _ = service.build_inference_prompt(task)

        # Assert
        assert user == multiline

    def test_return_value_is_tuple_of_two_strings(self, service: JudgePromptService) -> None:
        # Arrange
        task = _make_task()

        # Act
        result = service.build_inference_prompt(task)

        # Assert
        assert isinstance(result, tuple)
        assert len(result) == 2
        assert all(isinstance(item, str) for item in result)


# ---------------------------------------------------------------------------
# TestBuildJudgePromptUserPromptContent
# ---------------------------------------------------------------------------


class TestBuildJudgePromptUserPromptContent:
    def test_user_prompt_contains_task_type_value(self, service: JudgePromptService) -> None:
        # Arrange
        task = _make_task(task_type=TaskType.FACTUAL_QA)
        result = _make_result()

        # Act
        user, _ = service.build_judge_prompt(task, result)

        # Assert
        assert "factual_qa" in user

    def test_user_prompt_contains_question(self, service: JudgePromptService) -> None:
        # Arrange
        task = _make_task(question="What is the boiling point of water?")
        result = _make_result()

        # Act
        user, _ = service.build_judge_prompt(task, result)

        # Assert
        assert "What is the boiling point of water?" in user

    def test_user_prompt_contains_golden_answer(self, service: JudgePromptService) -> None:
        # Arrange
        task = _make_task(golden_answer="100 degrees Celsius at sea level")
        result = _make_result()

        # Act
        user, _ = service.build_judge_prompt(task, result)

        # Assert
        assert "100 degrees Celsius at sea level" in user

    def test_user_prompt_contains_pass_criteria(self, service: JudgePromptService) -> None:
        # Arrange
        task = _make_task(pass_criteria="Response mentions 100 degrees")  # noqa: S106  # false positive: evaluation criterion, not a password
        result = _make_result()

        # Act
        user, _ = service.build_judge_prompt(task, result)

        # Assert
        assert "Response mentions 100 degrees" in user

    def test_user_prompt_contains_fail_criteria(self, service: JudgePromptService) -> None:
        # Arrange
        task = _make_task(fail_criteria="Response is incorrect or missing temperature")
        result = _make_result()

        # Act
        user, _ = service.build_judge_prompt(task, result)

        # Assert
        assert "Response is incorrect or missing temperature" in user

    def test_user_prompt_contains_sanitized_response_when_present(self, service: JudgePromptService) -> None:
        # Arrange
        task = _make_task()
        result = _make_result(sanitized_response="sanitized text", raw_response="raw text")

        # Act
        user, _ = service.build_judge_prompt(task, result)

        # Assert
        assert "sanitized text" in user
        assert "raw text" not in user

    def test_user_prompt_falls_back_to_raw_response_when_sanitized_is_none(self, service: JudgePromptService) -> None:
        # Arrange
        task = _make_task()
        result = _make_result(sanitized_response=None, raw_response="raw fallback text")

        # Act
        user, _ = service.build_judge_prompt(task, result)

        # Assert
        assert "raw fallback text" in user

    def test_user_prompt_falls_back_to_raw_response_when_sanitized_is_empty_string(
        self, service: JudgePromptService
    ) -> None:
        # Arrange
        task = _make_task()
        result = _make_result(sanitized_response="", raw_response="raw fallback text")

        # Act
        user, _ = service.build_judge_prompt(task, result)

        # Assert
        assert "raw fallback text" in user

    def test_user_prompt_uses_empty_string_when_both_responses_are_none(self, service: JudgePromptService) -> None:
        # Arrange
        task = _make_task()
        result = _make_result(sanitized_response=None, raw_response=None)

        # Act — must not raise
        user, _ = service.build_judge_prompt(task, result)

        # Assert — submitted_answer label is present even with empty value
        assert "submitted_answer:" in user

    def test_return_value_is_tuple_of_two_strings(self, service: JudgePromptService) -> None:
        # Arrange
        task = _make_task()
        result = _make_result()

        # Act
        output = service.build_judge_prompt(task, result)

        # Assert
        assert isinstance(output, tuple)
        assert len(output) == 2
        assert all(isinstance(item, str) for item in output)


# ---------------------------------------------------------------------------
# TestBuildJudgePromptSystemPromptPerTaskType
# ---------------------------------------------------------------------------


class TestBuildJudgePromptSystemPromptPerTaskType:
    @pytest.mark.parametrize(
        "task_type",
        list(TaskType),
        ids=[t.value for t in TaskType],
    )
    def test_all_task_types_return_non_empty_system_prompt_with_schema(
        self, service: JudgePromptService, task_type: TaskType
    ) -> None:
        # Arrange
        task = _make_task(task_type=task_type)
        result = _make_result()

        # Act
        _, system = service.build_judge_prompt(task, result)

        # Assert — non-empty and contains V2 schema enforcement keywords
        assert len(system) > 0
        assert '"verdict"' in system
        assert '"score"' in system
        assert '"reasoning"' in system

    def test_code_generation_returns_code_specific_system_prompt(self, service: JudgePromptService) -> None:
        # Arrange
        task = _make_task(task_type=TaskType.CODE_GENERATION)
        result = _make_result()

        # Act
        _, system = service.build_judge_prompt(task, result)

        # Assert — rubric keywords unique to code evaluation
        assert "compile" in system or "API usage" in system

    def test_code_review_returns_same_system_prompt_as_code_generation(self, service: JudgePromptService) -> None:
        # Arrange
        gen_task = _make_task(task_type=TaskType.CODE_GENERATION)
        rev_task = _make_task(task_type=TaskType.CODE_REVIEW)
        result = _make_result()

        # Act
        _, gen_system = service.build_judge_prompt(gen_task, result)
        _, rev_system = service.build_judge_prompt(rev_task, result)

        # Assert
        assert gen_system == rev_system

    def test_text_rewrite_returns_same_system_prompt_as_summarization(self, service: JudgePromptService) -> None:
        # Arrange
        rewrite_task = _make_task(task_type=TaskType.TEXT_REWRITE)
        summarize_task = _make_task(task_type=TaskType.SUMMARIZATION)
        result = _make_result()

        # Act
        _, rewrite_system = service.build_judge_prompt(rewrite_task, result)
        _, summarize_system = service.build_judge_prompt(summarize_task, result)

        # Assert
        assert rewrite_system == summarize_system

    def test_reasoning_returns_reasoning_specific_system_prompt(self, service: JudgePromptService) -> None:
        # Arrange
        task = _make_task(task_type=TaskType.REASONING)
        result = _make_result()

        # Act
        _, system = service.build_judge_prompt(task, result)

        # Assert
        assert "chain of thought" in system or "logical" in system.lower()

    def test_translation_returns_translation_specific_system_prompt(self, service: JudgePromptService) -> None:
        # Arrange
        task = _make_task(task_type=TaskType.TRANSLATION)
        result = _make_result()

        # Act
        _, system = service.build_judge_prompt(task, result)

        # Assert
        assert "fidelity" in system or "entities" in system.lower()

    def test_factual_qa_returns_factual_specific_system_prompt(self, service: JudgePromptService) -> None:
        # Arrange
        task = _make_task(task_type=TaskType.FACTUAL_QA)
        result = _make_result()

        # Act
        _, system = service.build_judge_prompt(task, result)

        # Assert
        assert "factual" in system.lower() or "accuracy" in system.lower()

    def test_data_extraction_returns_extraction_specific_system_prompt(self, service: JudgePromptService) -> None:
        # Arrange
        task = _make_task(task_type=TaskType.DATA_EXTRACTION)
        result = _make_result()

        # Act
        _, system = service.build_judge_prompt(task, result)

        # Assert
        assert "extraction" in system.lower() or "format" in system.lower()

    def test_all_8_task_types_have_distinct_prompts_except_known_shared_pairs(
        self, service: JudgePromptService
    ) -> None:
        # Arrange — collect system prompts for all 8 TaskType values
        result = _make_result()
        system_prompts: dict[TaskType, str] = {
            tt: service.build_judge_prompt(_make_task(task_type=tt), result)[1] for tt in TaskType
        }

        # Assert known shared pairs
        assert system_prompts[TaskType.CODE_GENERATION] == system_prompts[TaskType.CODE_REVIEW]
        assert system_prompts[TaskType.TEXT_REWRITE] == system_prompts[TaskType.SUMMARIZATION]

        # Assert distinct groups: code, reasoning, translation, factual_qa, rewrite/summarization, data_extraction
        distinct_prompts = {
            system_prompts[TaskType.CODE_GENERATION],
            system_prompts[TaskType.REASONING],
            system_prompts[TaskType.TRANSLATION],
            system_prompts[TaskType.FACTUAL_QA],
            system_prompts[TaskType.TEXT_REWRITE],
            system_prompts[TaskType.DATA_EXTRACTION],
        }
        assert len(distinct_prompts) == 6  # 6 unique rubric constants


# ---------------------------------------------------------------------------
# TestBuildJudgePromptSystemPromptDefault
# ---------------------------------------------------------------------------


class TestBuildJudgePromptSystemPromptDefault:
    def test_default_prompt_is_distinct_from_all_specific_prompts(self) -> None:
        specific_constants = {
            _CODE_JUDGE_SYSTEM_PROMPT,
            _REASONING_JUDGE_SYSTEM_PROMPT,
            _TRANSLATION_JUDGE_SYSTEM_PROMPT,
            _FACTUAL_QA_JUDGE_SYSTEM_PROMPT,
            _REWRITE_SUMMARIZATION_JUDGE_SYSTEM_PROMPT,
            _DATA_EXTRACTION_JUDGE_SYSTEM_PROMPT,
        }
        assert _DEFAULT_JUDGE_SYSTEM_PROMPT not in specific_constants

    def test_default_prompt_contains_schema_enforcement(self) -> None:
        assert '"verdict"' in _DEFAULT_JUDGE_SYSTEM_PROMPT
        assert '"score"' in _DEFAULT_JUDGE_SYSTEM_PROMPT
        assert '"reasoning"' in _DEFAULT_JUDGE_SYSTEM_PROMPT

    def test_default_prompt_is_non_empty(self) -> None:
        assert len(_DEFAULT_JUDGE_SYSTEM_PROMPT) > 0


# ---------------------------------------------------------------------------
# TestProtocolConformance
# ---------------------------------------------------------------------------


class TestProtocolConformance:
    def test_isinstance_check_passes_against_judge_prompt_service_api(self) -> None:
        from ollama_llm_bench.backend.core.interfaces import JudgePromptServiceApi

        svc = JudgePromptService()
        assert isinstance(svc, JudgePromptServiceApi)

    def test_build_inference_prompt_return_type_is_tuple_of_two_strings(self) -> None:
        svc = JudgePromptService()
        task = _make_task()

        result = svc.build_inference_prompt(task)

        assert isinstance(result, tuple)
        assert len(result) == 2
        assert isinstance(result[0], str)
        assert isinstance(result[1], str)

    def test_build_judge_prompt_return_type_is_tuple_of_two_strings(self) -> None:
        svc = JudgePromptService()
        task = _make_task()
        bench_result = _make_result()

        output = svc.build_judge_prompt(task, bench_result)

        assert isinstance(output, tuple)
        assert len(output) == 2
        assert isinstance(output[0], str)
        assert isinstance(output[1], str)
