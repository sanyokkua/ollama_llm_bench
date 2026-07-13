"""Per-run parameter parsing from the frozen run snapshot (§4, §7)."""

from dataclasses import dataclass

from ollama_llm_bench.backend.domain import BenchmarkRunSettingEntry

_COSINE_THRESHOLD_KEY = "eval.cosine_threshold"
_CACHE_MAX_ENTRIES_KEY = "eval.embedding_cache_max_entries"
_CONSECUTIVE_FAILURES_TO_SKIP_KEY = "eval.embedding_consecutive_failures_to_skip"

REQUIRED_SETTING_KEYS: frozenset[str] = frozenset(
    {
        _COSINE_THRESHOLD_KEY,
        _CACHE_MAX_ENTRIES_KEY,
        _CONSECUTIVE_FAILURES_TO_SKIP_KEY,
    }
)


@dataclass(slots=True, frozen=True)
class _EmbeddingParameters:
    """The embedding service's per-run parameters, parsed once at construction (§7)."""

    cosine_threshold: float
    cache_max_entries: int
    consecutive_failures_to_skip: int


def parse_embedding_parameters(
    snapshot: tuple[BenchmarkRunSettingEntry, ...],
) -> _EmbeddingParameters:
    """Read the three embedding-service keys once from the frozen snapshot (§4, §7).

    Args:
        snapshot: The run's frozen per-run-overridable settings; must carry all
            three embedding-service keys (enforced by the ``api.py`` factory's
            icontract precondition, not here).

    Returns:
        The parsed ``_EmbeddingParameters`` for this run.
    """
    values = {entry.setting_key: entry.setting_value for entry in snapshot}
    return _EmbeddingParameters(
        cosine_threshold=float(values[_COSINE_THRESHOLD_KEY]),
        cache_max_entries=int(values[_CACHE_MAX_ENTRIES_KEY]),
        consecutive_failures_to_skip=int(values[_CONSECUTIVE_FAILURES_TO_SKIP_KEY]),
    )
