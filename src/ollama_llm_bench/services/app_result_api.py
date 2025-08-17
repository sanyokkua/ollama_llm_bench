import logging
from collections import defaultdict
from typing import List, override

from ollama_llm_bench.core.interfaces import DataApi, ResultApi
from ollama_llm_bench.core.models import (AvgSummaryTableItem, SummaryTableItem)

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
    def retrieve_avg_benchmark_results_for_run(self, run_id: int) -> List[AvgSummaryTableItem]:
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
            total_time = sum(r.time_taken_ms or 0 for r in model_results_list)
            total_tokens = sum(r.tokens_generated or 0 for r in model_results_list)
            total_score = sum(r.evaluation_score or 0.0 for r in model_results_list)

            avg_time = total_time / count
            avg_score = total_score / count
            avg_tokens_per_second = (total_tokens / total_time) * 1000 if total_time > 0 else 0.0

            item = AvgSummaryTableItem(model_name=model_name,
                                       avg_time_ms=avg_time,
                                       avg_tokens_per_second=avg_tokens_per_second,
                                       avg_score=avg_score, )
            avg_results.append(item)

        logger.info("Calculated averages for %d models in run ID %d", len(avg_results), run_id)
        return avg_results

    @override
    def retrieve_detailed_benchmark_results_for_run(self, run_id: int) -> List[SummaryTableItem]:
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
            tokens_generated = result.tokens_generated or 0
            if result.time_taken_ms and result.time_taken_ms > 0:
                tokens_per_second = tokens_generated / result.time_taken_ms * 1000
            else:
                tokens_per_second = 0.0

            score_reason = result.evaluation_reason or ""

            item = SummaryTableItem(model_name=result.model_name,
                                    task_id=result.task_id,
                                    task_status=str(result.status),
                                    time_ms=result.time_taken_ms or 0,
                                    tokens=result.tokens_generated or 0,
                                    tokens_per_second=tokens_per_second or 0.0,
                                    score=result.evaluation_score or 0.0,
                                    score_reason=score_reason, )
            detailed_results.append(item)
            valid_results_count += 1

        if not valid_results_count:
            logger.warning("No valid completed results found for run ID %d", run_id)
        else:
            logger.info("Retrieved %d detailed results for run ID %d", valid_results_count, run_id)

        return detailed_results
