"""Stateless, task-type-aware prompt builder for V2 benchmark evaluation.

Implements JudgePromptServiceApi via structural typing (Protocol). Consumed by
LLMJudgeEvaluator (Layer 4) to build inference and judge prompts from benchmark tasks.
"""

import logging

from ollama_llm_bench.backend.core.models import BenchmarkResult, BenchmarkTask, TaskType

_logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# System-prompt constants — one per rubric group.
# Each constant contains:
#   1. A role declaration.
#   2. A task-type-specific rubric emphasis.
#   3. The V2 output-schema enforcement clause (identical across all constants).
# ---------------------------------------------------------------------------

_SCHEMA_ENFORCEMENT = (
    "Return ONLY a JSON object with this exact schema:\n"
    '{"verdict":"pass"|"fail","score":<float 0.00-1.00>,"reasoning":"<one sentence>"}\n'
    "No markdown, no code fences, no extra keys, no explanation outside the JSON object."
)

_CODE_JUDGE_SYSTEM_PROMPT: str = (
    "You are an objective evaluator of code quality.\n"
    "Evaluate based on:\n"
    "  (1) Correctness — does the submitted code solve the stated problem?\n"
    "  (2) API usage — does it use the required language, framework, or library correctly?\n"
    "  (3) Plausibility to compile or run without modification given the stated language version?\n"
    "Use the golden_answer as the reference implementation.\n"
    "Apply pass_criteria to grant a pass verdict; apply fail_criteria to grant a fail verdict.\n"
    f"{_SCHEMA_ENFORCEMENT}"
)

_REASONING_JUDGE_SYSTEM_PROMPT: str = (
    "You are an objective evaluator of reasoning quality.\n"
    "Evaluate based on:\n"
    "  (1) Logical soundness — are all reasoning steps valid and free of logical fallacies?\n"
    "  (2) Correct chain of thought — does each step follow necessarily from the previous?\n"
    "  (3) Correct final answer — does the conclusion match the golden_answer?\n"
    "Apply pass_criteria to grant a pass verdict; apply fail_criteria to grant a fail verdict.\n"
    f"{_SCHEMA_ENFORCEMENT}"
)

_TRANSLATION_JUDGE_SYSTEM_PROMPT: str = (
    "You are an objective evaluator of translation quality.\n"
    "Evaluate based on:\n"
    "  (1) Fidelity to meaning — does the translation accurately convey the source text?\n"
    "  (2) Preservation of all named entities, numbers, dates, and proper nouns.\n"
    "  (3) Appropriate register and style matching the golden_answer.\n"
    "Apply pass_criteria to grant a pass verdict; apply fail_criteria to grant a fail verdict.\n"
    f"{_SCHEMA_ENFORCEMENT}"
)

_FACTUAL_QA_JUDGE_SYSTEM_PROMPT: str = (
    "You are an objective evaluator of factual accuracy.\n"
    "Evaluate based on:\n"
    "  (1) Accuracy of all claimed facts against the golden_answer.\n"
    "  (2) Absence of fabricated, hallucinated, or contradictory information.\n"
    "Apply pass_criteria to grant a pass verdict; apply fail_criteria to grant a fail verdict.\n"
    f"{_SCHEMA_ENFORCEMENT}"
)

_REWRITE_SUMMARIZATION_JUDGE_SYSTEM_PROMPT: str = (
    "You are an objective evaluator of text rewriting and summarization quality.\n"
    "Evaluate based on:\n"
    "  (1) Correctness — does the response fulfill the requested transformation?\n"
    "  (2) Format adherence — does the output format match the golden_answer structure?\n"
    "  (3) Completeness — are all required points or sections covered?\n"
    "Apply pass_criteria to grant a pass verdict; apply fail_criteria to grant a fail verdict.\n"
    f"{_SCHEMA_ENFORCEMENT}"
)

_DATA_EXTRACTION_JUDGE_SYSTEM_PROMPT: str = (
    "You are an objective evaluator of data extraction quality.\n"
    "Evaluate based on:\n"
    "  (1) Correctness — are all extracted values accurate relative to the golden_answer?\n"
    "  (2) Strict format adherence — does the output exactly match the required format "
    "(field names, separators, order)?\n"
    "  (3) Completeness — are all required fields present with no omissions?\n"
    "Apply pass_criteria to grant a pass verdict; apply fail_criteria to grant a fail verdict.\n"
    f"{_SCHEMA_ENFORCEMENT}"
)

_DEFAULT_JUDGE_SYSTEM_PROMPT: str = (
    "You are an objective evaluator.\n"
    "Evaluate based on a balanced rubric:\n"
    "  (1) Correctness — does the response answer the question accurately?\n"
    "  (2) Completeness — does it cover all required points from the golden_answer?\n"
    "  (3) Format adherence — does it match any explicit format requirements?\n"
    "Apply pass_criteria to grant a pass verdict; apply fail_criteria to grant a fail verdict.\n"
    f"{_SCHEMA_ENFORCEMENT}"
)

# ---------------------------------------------------------------------------
# User-prompt template — shared across all task types.
# ---------------------------------------------------------------------------

_USER_PROMPT_TEMPLATE: str = (
    "task_type: {task_type}\n"
    "question: {question}\n"
    "golden_answer: {golden_answer}\n"
    "pass_criteria: {pass_criteria}\n"
    "fail_criteria: {fail_criteria}\n"
    "submitted_answer: {submitted_answer}"
)

# ---------------------------------------------------------------------------
# Dispatch table — maps each TaskType to its system-prompt constant.
# All 8 TaskType values are covered. _DEFAULT_JUDGE_SYSTEM_PROMPT is a safety
# net for TaskType additions that predate a service update.
# ---------------------------------------------------------------------------

_JUDGE_SYSTEM_PROMPTS: dict[TaskType, str] = {
    TaskType.CODE_GENERATION: _CODE_JUDGE_SYSTEM_PROMPT,
    TaskType.CODE_REVIEW: _CODE_JUDGE_SYSTEM_PROMPT,
    TaskType.REASONING: _REASONING_JUDGE_SYSTEM_PROMPT,
    TaskType.TRANSLATION: _TRANSLATION_JUDGE_SYSTEM_PROMPT,
    TaskType.FACTUAL_QA: _FACTUAL_QA_JUDGE_SYSTEM_PROMPT,
    TaskType.TEXT_REWRITE: _REWRITE_SUMMARIZATION_JUDGE_SYSTEM_PROMPT,
    TaskType.SUMMARIZATION: _REWRITE_SUMMARIZATION_JUDGE_SYSTEM_PROMPT,
    TaskType.DATA_EXTRACTION: _DATA_EXTRACTION_JUDGE_SYSTEM_PROMPT,
}


class JudgePromptService:
    """Stateless, task-type-aware prompt builder for V2 benchmark evaluation.

    Implements JudgePromptServiceApi structurally (Protocol duck typing). No constructor
    dependencies — all rubric constants are module-level. Consumed exclusively by
    LLMJudgeEvaluator (Layer 4).
    """

    def __init__(self) -> None:
        pass

    def build_inference_prompt(self, task: BenchmarkTask) -> tuple[str, str]:
        """Return the task question as user prompt with an empty system prompt.

        Args:
            task: The benchmark task to build a prompt for.

        Returns:
            A tuple of (user_prompt, system_prompt) where system_prompt is always "".
        """
        return task.question, ""

    def build_judge_prompt(self, task: BenchmarkTask, result: BenchmarkResult) -> tuple[str, str]:
        """Build a task-type-specific judge prompt from the task definition and inference result.

        Selects the system prompt from _JUDGE_SYSTEM_PROMPTS keyed on task.task_type,
        falling back to _DEFAULT_JUDGE_SYSTEM_PROMPT for unmapped types. Uses
        result.sanitized_response when non-empty, otherwise result.raw_response.

        Args:
            task: The benchmark task with grading criteria and golden answer.
            result: The inference result containing the submitted answer.

        Returns:
            A tuple of (user_prompt, system_prompt) ready for submission to a judge model.
        """
        submitted_answer: str = result.sanitized_response or result.raw_response or ""
        system_prompt: str = _JUDGE_SYSTEM_PROMPTS.get(task.task_type, _DEFAULT_JUDGE_SYSTEM_PROMPT)
        user_prompt: str = _USER_PROMPT_TEMPLATE.format(
            task_type=task.task_type.value,
            question=task.question,
            golden_answer=task.golden_answer,
            pass_criteria=task.pass_criteria,
            fail_criteria=task.fail_criteria,
            submitted_answer=submitted_answer,
        )
        _logger.debug("judge_prompt_built task_id=%s task_type=%s", task.task_id, task.task_type.value)
        return user_prompt, system_prompt
