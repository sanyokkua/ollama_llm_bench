"""LLM judge evaluator (Layer 4) — calls a judge LLM to score the model response."""

import logging

from ollama_llm_bench.backend.core.interfaces import JudgePromptServiceApi, ProviderRegistryApi
from ollama_llm_bench.backend.core.models import (
    BenchmarkResult,
    BenchmarkTask,
    EvalLayer,
    EvaluationResult,
    EvalVerdict,
)
from ollama_llm_bench.backend.utils.text_utils import parse_v2_judge_response

logger = logging.getLogger(__name__)

_MAX_JUDGE_TOKENS = 256
_JUDGE_TEMPERATURE = 0.0


class LLMJudgeEvaluator:
    """Layer 4 evaluator that calls a judge LLM to produce a verdict and score.

    Builds task-type-specific prompts via ``JudgePromptService``, calls the judge
    model through ``ProviderRegistry``, and parses the structured JSON response.

    On any error (provider unavailable, inference failure, parse failure) the
    pipeline receives a non-terminal UNKNOWN result so later stages or callers
    can decide how to proceed. Errors are logged at WARNING level and never
    propagate as exceptions.
    """

    def __init__(
        self,
        *,
        provider_registry: ProviderRegistryApi,
        judge_prompt_service: JudgePromptServiceApi,
    ) -> None:
        self._provider_registry = provider_registry
        self._judge_prompt_service = judge_prompt_service

    @property
    def layer(self) -> EvalLayer:
        """Return the evaluation layer identifier."""
        return EvalLayer.LLM_JUDGE

    @property
    def provider_registry(self) -> ProviderRegistryApi:
        """Return the injected provider registry."""
        return self._provider_registry

    def evaluate(
        self,
        task: BenchmarkTask,
        result: BenchmarkResult,
        *,
        judge_provider_id: str,
        judge_model: str,
    ) -> EvaluationResult:
        """Call the judge LLM and return a terminal verdict or non-terminal UNKNOWN.

        Args:
            task: Benchmark task supplying the question and grading criteria.
            result: Benchmark result containing the model's response to evaluate.
            judge_provider_id: ID of the provider to use for the judge call.
            judge_model: Model name to use for the judge call.

        Returns:
            Terminal ``EvaluationResult`` on successful parse; non-terminal UNKNOWN
            when the provider is unavailable, inference fails, or response is unparseable.
        """
        user_prompt, system_prompt = self._judge_prompt_service.build_judge_prompt(task, result)
        messages: list[dict[str, str]] = [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_prompt},
        ]

        try:
            provider = self._provider_registry.get_provider(judge_provider_id)
        except Exception:
            logger.warning(
                "llm_judge_provider_not_found",
                extra={"provider_id": judge_provider_id},
            )
            return self._unknown(f"Provider not found: {judge_provider_id}")

        supports_json = provider.supports_structured_output()
        logger.debug(
            "llm_judge_provider_capability",
            extra={"provider_id": judge_provider_id, "supports_structured_output": supports_json},
        )

        try:
            inference_response = provider.inference_sync(
                model=judge_model,
                messages=messages,
                temperature=_JUDGE_TEMPERATURE,
                max_tokens=_MAX_JUDGE_TOKENS,
            )
        except Exception:
            logger.warning(
                "llm_judge_inference_failed",
                extra={"provider_id": judge_provider_id, "model": judge_model},
            )
            return self._unknown(f"Inference failed for model: {judge_model}")

        if inference_response.has_error:
            logger.warning(
                "llm_judge_inference_error",
                extra={"error": inference_response.error_message, "model": judge_model},
            )
            return self._unknown(f"Inference error: {inference_response.error_message}")

        has_error, verdict, score, reasoning = parse_v2_judge_response(inference_response.llm_response)
        if has_error:
            logger.warning(
                "llm_judge_parse_failed",
                extra={"model": judge_model, "reasoning": reasoning},
            )
            return self._unknown(reasoning)

        return EvaluationResult(
            verdict=verdict,
            score=score,
            reasoning=reasoning,
            is_terminal=True,
            layer=self.layer,
            judge_time_ms=inference_response.total_time_ms,
            judge_completion_tokens=inference_response.completion_tokens,
            judge_prompt_template=str(task.task_type.value),
        )

    def _unknown(self, reasoning: str) -> EvaluationResult:
        return EvaluationResult(
            verdict=EvalVerdict.UNKNOWN,
            score=0.5,
            reasoning=reasoning,
            is_terminal=False,
            layer=self.layer,
        )
