"""Application-wide single-inference gate store."""

from ollama_llm_bench.backend.stores.inference_activity.api import (
    InferenceActivityStore,
    make_inference_activity_store,
)

__all__: list[str] = [
    "InferenceActivityStore",
    "make_inference_activity_store",
]
