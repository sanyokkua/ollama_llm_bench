"""Shared test helpers for backend/embedding/tests/."""

from collections.abc import Callable
from typing import TYPE_CHECKING

from ollama_llm_bench.backend.concurrency import CancellationToken
from ollama_llm_bench.backend.domain import (
    BenchmarkRunSettingEntry,
    ChatRequest,
    ChatResponse,
    InferenceTestResult,
    ModelName,
    ProviderHealth,
)

if TYPE_CHECKING:
    from ollama_llm_bench.backend.provider_registry import ChatStream

__all__ = ["FakeLLMClient", "make_snapshot"]


def make_snapshot(
    *,
    cosine_threshold: float = 0.85,
    cache_max_entries: int = 4096,
    consecutive_failures_to_skip: int = 3,
) -> tuple[BenchmarkRunSettingEntry, ...]:
    """Build a valid 3-key embedding-service snapshot (defaults per spec §7).

    Args:
        cosine_threshold: ``eval.cosine_threshold`` override.
        cache_max_entries: ``eval.embedding_cache_max_entries`` override.
        consecutive_failures_to_skip: ``eval.embedding_consecutive_failures_to_skip``
            override.

    Returns:
        A tuple of 3 ``BenchmarkRunSettingEntry`` rows, one per embedding-service key.
    """
    values: dict[str, str] = {
        "eval.cosine_threshold": str(cosine_threshold),
        "eval.embedding_cache_max_entries": str(cache_max_entries),
        "eval.embedding_consecutive_failures_to_skip": str(consecutive_failures_to_skip),
    }
    return tuple(
        BenchmarkRunSettingEntry(setting_key=key, setting_value=value)
        for key, value in values.items()
    )


class FakeLLMClient:
    """A minimal ``LLMClient`` test double exercising only ``embed`` (§6.2, §9).

    Every other ``LLMClient`` member is present (for structural-typing
    compatibility with the Protocol) but raises ``NotImplementedError`` — the
    embedding service under test never calls chat/list/probe surfaces.

    Args:
        embed_fn: Called for every ``embed(text)`` invocation; defaults to a
            deterministic hash-derived vector so identical texts always embed
            identically and distinct texts (almost always) embed distinctly.
    """

    def __init__(self, *, embed_fn: Callable[[str], tuple[float, ...]] | None = None) -> None:
        self._embed_fn = embed_fn if embed_fn is not None else _default_embed
        self.calls: list[str] = []

    def embed(self, text: str) -> tuple[float, ...]:
        """Record the call and delegate to the configured ``embed_fn``."""
        self.calls.append(text)
        return self._embed_fn(text)

    def list_models(self) -> tuple[ModelName, ...]:
        """Not exercised by embedding-service tests."""
        raise NotImplementedError

    def probe_health(self) -> ProviderHealth:
        """Not exercised by embedding-service tests."""
        raise NotImplementedError

    def test_inference(self, model_name: ModelName) -> InferenceTestResult:
        """Not exercised by embedding-service tests."""
        raise NotImplementedError

    def chat(self, request: ChatRequest, *, token: CancellationToken) -> ChatResponse:
        """Not exercised by embedding-service tests."""
        raise NotImplementedError

    def chat_stream(self, request: ChatRequest, *, token: CancellationToken) -> "ChatStream":
        """Not exercised by embedding-service tests."""
        raise NotImplementedError

    def supports_streaming(self) -> bool:
        """Not exercised by embedding-service tests."""
        raise NotImplementedError

    def supports_reasoning_effort(self) -> bool:
        """Not exercised by embedding-service tests."""
        raise NotImplementedError

    def supports_thinking(self) -> bool:
        """Not exercised by embedding-service tests."""
        raise NotImplementedError

    def supports_embedding(self) -> bool:
        """Not exercised by embedding-service tests."""
        raise NotImplementedError

    def supports_discovery(self) -> bool:
        """Not exercised by embedding-service tests."""
        raise NotImplementedError

    def close(self) -> None:
        """Not exercised by embedding-service tests."""
        raise NotImplementedError


def _default_embed(text: str) -> tuple[float, ...]:
    """A deterministic, cheap stand-in vector derived from ``text``'s hash."""
    seed = abs(hash(text))
    return (float(seed % 97) + 1.0, float(seed % 53) + 1.0, float(seed % 17) + 1.0)
