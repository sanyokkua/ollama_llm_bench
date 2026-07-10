"""ResultsStore (BenchmarkResult aggregate + recovery sweep)."""

from ollama_llm_bench.backend.persistence.results.api import ResultsStore, create_results_store

__all__: list[str] = [
    "ResultsStore",
    "create_results_store",
]
