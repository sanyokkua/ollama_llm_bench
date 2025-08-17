import logging
from typing import List, Tuple

from ollama_llm_bench.core.interfaces import DataApi

logger = logging.getLogger(__name__)


def get_benchmark_runs(data_api: DataApi) -> List[Tuple[int, str]]:
    """
    Retrieve and sort all benchmark runs by timestamp in descending order.

    Args:
        data_api: Interface for accessing benchmark run data.

    Returns:
        List of (run_id, timestamp) tuples sorted by timestamp (newest first),
        or empty list if retrieval fails.
    """
    try:
        # One-step list creation with sorting
        return sorted(
            [(run.run_id, run.timestamp) for run in data_api.retrieve_benchmark_runs()],
            key=lambda x: x[1],
            reverse=True,
        )
    except Exception as e:
        logger.warning("Failed to retrieve benchmark runs", exc_info=True)
        return []
