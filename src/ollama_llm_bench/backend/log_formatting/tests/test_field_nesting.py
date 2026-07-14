"""Proves: STORY-036-AC-1 — the per-verbosity field set is strictly nested (§6.2)."""

from ollama_llm_bench.backend.domain import RunLogVerbosity
from ollama_llm_bench.backend.log_formatting._internal.fields import resolve_verbosity_and_fields


def test_field_set_is_strictly_nested() -> None:
    """Proves: STORY-036-AC-1

    Covers LF-1, LF-2, LF-3, LF-4. Given the §6.2 field-selection matrix resolved for
    Short, Normal, and Verbose, then every field selected at Short is also selected at
    Normal, and every field selected at Normal is also selected at Verbose — the three
    sets are strictly nested (Short subseteq Normal subseteq Verbose), and Verbose
    selects strictly more fields than Short (TTFT/TPS/token-count fields are
    Verbose-only, per LF-3).
    """
    # Arrange / Act
    _, short_fields = resolve_verbosity_and_fields(RunLogVerbosity.SHORT)
    _, normal_fields = resolve_verbosity_and_fields(RunLogVerbosity.NORMAL)
    _, verbose_fields = resolve_verbosity_and_fields(RunLogVerbosity.VERBOSE)

    # Assert
    assert short_fields <= normal_fields <= verbose_fields
    assert short_fields < verbose_fields
