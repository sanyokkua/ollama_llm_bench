"""Unit tests for backend/embedding/_internal/parameters.py's snapshot parsing."""

from ollama_llm_bench.backend.embedding._internal.parameters import (
    REQUIRED_SETTING_KEYS,
    parse_embedding_parameters,
)
from ollama_llm_bench.backend.embedding.tests.conftest import make_snapshot

_DEFAULT_COSINE_THRESHOLD = 0.85
_DEFAULT_CACHE_MAX_ENTRIES = 4096
_DEFAULT_CONSECUTIVE_FAILURES_TO_SKIP = 3

_OVERRIDE_COSINE_THRESHOLD = 0.5
_OVERRIDE_CACHE_MAX_ENTRIES = 10
_OVERRIDE_CONSECUTIVE_FAILURES_TO_SKIP = 1

_EXPECTED_REQUIRED_KEYS = frozenset(
    {
        "eval.cosine_threshold",
        "eval.embedding_cache_max_entries",
        "eval.embedding_consecutive_failures_to_skip",
    }
)


def test_required_setting_keys_has_exactly_three_keys() -> None:
    """REQUIRED_SETTING_KEYS names exactly the three embedding-service settings."""
    assert REQUIRED_SETTING_KEYS == _EXPECTED_REQUIRED_KEYS


def test_parse_embedding_parameters_reads_default_snapshot() -> None:
    """Default snapshot values parse to the spec §7 defaults."""
    snapshot = make_snapshot()

    parameters = parse_embedding_parameters(snapshot)

    assert parameters.cosine_threshold == _DEFAULT_COSINE_THRESHOLD
    assert parameters.cache_max_entries == _DEFAULT_CACHE_MAX_ENTRIES
    assert parameters.consecutive_failures_to_skip == _DEFAULT_CONSECUTIVE_FAILURES_TO_SKIP


def test_parse_embedding_parameters_reads_overridden_snapshot() -> None:
    """Per-run-overridden snapshot values are parsed and typed correctly."""
    snapshot = make_snapshot(
        cosine_threshold=_OVERRIDE_COSINE_THRESHOLD,
        cache_max_entries=_OVERRIDE_CACHE_MAX_ENTRIES,
        consecutive_failures_to_skip=_OVERRIDE_CONSECUTIVE_FAILURES_TO_SKIP,
    )

    parameters = parse_embedding_parameters(snapshot)

    assert parameters.cosine_threshold == _OVERRIDE_COSINE_THRESHOLD
    assert parameters.cache_max_entries == _OVERRIDE_CACHE_MAX_ENTRIES
    assert parameters.consecutive_failures_to_skip == _OVERRIDE_CONSECUTIVE_FAILURES_TO_SKIP
