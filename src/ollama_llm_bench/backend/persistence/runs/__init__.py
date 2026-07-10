"""RunsStore (BenchmarkRun aggregate)."""

from ollama_llm_bench.backend.persistence.runs.api import RunsStore, create_runs_store

__all__: list[str] = [
    "RunsStore",
    "create_runs_store",
]
