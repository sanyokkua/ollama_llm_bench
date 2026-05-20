import logging

from ollama_llm_bench.backend.core.interfaces import DataApi

logger = logging.getLogger(__name__)


def get_benchmark_runs(data_api: DataApi) -> list[tuple[int, str]]:
    """
    Retrieve and sort all benchmark runs by display name (or timestamp) in descending order.

    Args:
        data_api: Interface for accessing benchmark run data.

    Returns:
        List of (run_id, display_name) tuples where display_name is the run_name when set
        or the timestamp otherwise, sorted descending, or empty list if retrieval fails.
    """
    try:
        return sorted(
            [(run.run_id, run.run_name or run.timestamp) for run in data_api.retrieve_benchmark_runs()],
            key=lambda x: x[1],
            reverse=True,
        )
    except Exception:
        logger.warning("Failed to retrieve benchmark runs", exc_info=True)
        return []
