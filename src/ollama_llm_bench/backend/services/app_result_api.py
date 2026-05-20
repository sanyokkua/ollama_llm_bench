import logging
from collections import defaultdict
from typing import override

from ollama_llm_bench.backend.core.interfaces import DataApi, ResultApi
from ollama_llm_bench.backend.core.models import (
    AvgSummaryTableItem,
    BenchmarkResultStatus,
    EvalLayer,
    EvalVerdict,
    SummaryTableItem,
)

_LAYER_LABELS: dict[str, str] = {
    EvalLayer.RULE_BASED.value: "L1:rules",
    EvalLayer.KEYWORD.value: "L2:keywords",
    EvalLayer.COSINE.value: "L3:cosine",
    EvalLayer.LLM_JUDGE.value: "L4:judge",
}

logger = logging.getLogger(__name__)


class AppResultApi(ResultApi):
    """
    Concrete implementation of ResultApi for computing benchmark summaries.
    Calculates aggregated and detailed performance metrics from stored results.
    """

    def __init__(self, *, data_api: DataApi):
        """
        Initialize the result processor.

        Args:
            data_api: Interface for retrieving benchmark results.
        """
        super().__init__(data_api=data_api)
        logger.debug("Initialized AppResultApi")

    @override
    def retrieve_avg_benchmark_results_for_run(self, run_id: int) -> list[AvgSummaryTableItem]:
        """
        Calculate averaged performance metrics across all tasks for each model in a run.

        Args:
            run_id: Identifier of the benchmark run.

        Returns:
            List of averaged summary items, one per model.
        """
        logger.debug("Calculating average benchmark results for run ID %d", run_id)

        if run_id <= 0:
            logger.warning("Invalid run ID %d for average results calculation", run_id)
            return []

        results = self._data_api.retrieve_benchmark_results_for_run(run_id)
        logger.debug("Retrieved %d total results for run ID %d", len(results), run_id)

        model_results = defaultdict(list)
        valid_results_count = 0
        for result in results:
            model_results[result.model_name].append(result)
            valid_results_count += 1

        if not valid_results_count:
            logger.warning("No valid completed results found for run ID %d", run_id)
            return []

        logger.debug("Processing %d valid completed results for run ID %d", valid_results_count, run_id)

        avg_results = []
        for model_name, model_results_list in model_results.items():
            count = len(model_results_list)
            total_time = sum(r.total_time_ms or 0 for r in model_results_list)
            total_tokens = sum(r.completion_tokens or 0 for r in model_results_list)
            total_score = sum(r.judge_score or 0.0 for r in model_results_list)

            avg_time = total_time / count
            avg_score = total_score / count
            avg_tokens_per_second = (total_tokens / total_time) * 1000 if total_time > 0 else 0.0

            pass_count = sum(1 for r in model_results_list if r.final_verdict == EvalVerdict.PASS)
            pass_rate = pass_count / count
            ttft_values = [r.ttft_ms for r in model_results_list if r.ttft_ms is not None]
            avg_ttft_ms: float | None = sum(ttft_values) / len(ttft_values) if ttft_values else None
            failed_count = sum(
                1 for r in model_results_list if r.status == BenchmarkResultStatus.FAILED or r.has_inference_error
            )

            item = AvgSummaryTableItem(
                model_name=model_name,
                avg_time_ms=avg_time,
                avg_tokens_per_second=avg_tokens_per_second,
                avg_score=avg_score,
                avg_ttft_ms=avg_ttft_ms,
                pass_rate=pass_rate,
                failed_count=failed_count,
            )
            avg_results.append(item)

        logger.info("Calculated averages for %d models in run ID %d", len(avg_results), run_id)
        return avg_results

    @override
    def retrieve_detailed_benchmark_results_for_run(self, run_id: int) -> list[SummaryTableItem]:
        """
        Retrieve detailed per-task performance metrics for all models in a run.

        Args:
            run_id: Identifier of the benchmark run.

        Returns:
            List of detailed summary items for each task-model combination.
        """
        logger.debug("Retrieving detailed benchmark results for run ID %d", run_id)

        if run_id <= 0:
            logger.warning("Invalid run ID %d for detailed results retrieval", run_id)
            return []

        results = self._data_api.retrieve_benchmark_results_for_run(run_id)
        logger.debug("Retrieved %d total results for run ID %d", len(results), run_id)

        detailed_results = []
        valid_results_count = 0
        for result in results:
            tokens_generated = result.completion_tokens or 0
            if result.total_time_ms and result.total_time_ms > 0:
                tokens_per_second = tokens_generated / result.total_time_ms * 1000
            else:
                tokens_per_second = 0.0

            score_reason = result.judge_reasoning or ""

            cosine_sim: float | None = result.cosine_similarity
            resolution = _LAYER_LABELS.get(result.resolution_layer, "") if result.resolution_layer else ""
            error_message = result.inference_error_message or result.judge_error_message or ""

            if result.judge_score is not None:
                effective_score = result.judge_score
            elif result.final_verdict and str(result.final_verdict).lower() == "pass":
                effective_score = 1.0
            else:
                effective_score = 0.0

            item = SummaryTableItem(
                model_name=result.model_name,
                task_id=result.task_id,
                task_category=result.task_category,
                task_status=str(result.status),
                time_ms=result.total_time_ms or 0,
                tokens=result.completion_tokens or 0,
                tokens_per_second=tokens_per_second or 0.0,
                score=effective_score,
                score_reason=score_reason,
                cosine_similarity=cosine_sim,
                resolution_layer=resolution,
                error_message=error_message,
                prompt_version=result.prompt_version,
            )
            detailed_results.append(item)
            valid_results_count += 1

        if not valid_results_count:
            logger.warning("No valid completed results found for run ID %d", run_id)
        else:
            logger.info("Retrieved %d detailed results for run ID %d", valid_results_count, run_id)

        return detailed_results
