"""Proves STORY-026-AC-3 — the embedding-model classifier (§4.9)."""

import pytest

from ollama_llm_bench.backend.model_helpers import is_embedding_model


@pytest.mark.parametrize(
    ("model_name", "expected"),
    [
        ("nomic-embed-text", True),
        ("mxbai-embed-large", True),
        ("bge-m3:567m", True),
        ("bge-m3", True),
        ("text-embedding-3-small", True),
        ("all-minilm", True),
        ("gte-large", True),
        ("e5-large-v2", True),
        ("llama3.2:3b", False),
        ("mistral:7b", False),
        ("gpt-4o-mini", False),
        ("gpt-4o", False),
        ("qwen3:8b-q4_K_M", False),
        ("claude-3-5-sonnet", False),
        ("gemini-1.5-pro", False),
        ("phi3:14b", False),
        ("", False),
    ],
)
def test_is_embedding_model_classifies_name(
    model_name: str,
    expected: bool,  # noqa: FBT001  # pytest.mark.parametrize table column, not a call-site flag
) -> None:
    """Proves: STORY-026-AC-3

    is_embedding_model returns True for a known embedding-only model name pattern
    and False for a known chat-model name pattern, never raising.
    """
    assert is_embedding_model(model_name) is expected
