"""Reusable QComboBox-backed models-of-a-provider dropdown (08-E §10)."""

from ollama_llm_bench.ui.shared.model_dropdown.api import ModelFetcher, make_model_dropdown

__all__: list[str] = ["ModelFetcher", "make_model_dropdown"]
