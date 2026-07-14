"""The shared, verbatim-reused live-inference-progress emission helper (§6.9).

Consumed by the benchmark pipeline's per-task inference and judge calls, the Run
Analysis Service's generation call, and (in a later story) `LLMClient.test_inference`.
"""

from ollama_llm_bench.backend.inference_progress.api import emit_progress_during

__all__: list[str] = ["emit_progress_during"]
