"""Per-run eval.* parameter parsing from the frozen settings snapshot (§7 of
04_EVALUATION_PIPELINE.md; §7, §9.2 of 08-P_judge_protocol.md)."""

from dataclasses import dataclass

from ollama_llm_bench.backend.domain import BenchmarkRunSettingEntry

_SANITY_MIN_CHARS_KEY = "eval.sanity_min_chars"
_SANITY_ERROR_MARKERS_KEY = "eval.sanity_error_markers"
_KEYWORD_SEMANTIC_PASS_THRESHOLD_KEY = "eval.keyword_semantic_pass_threshold"  # noqa: S105  # not a password
_JUDGE_MAX_COMPLETION_TOKENS_KEY = "eval.judge_max_completion_tokens"
_JUDGE_MAX_PARSE_RETRIES_KEY = "eval.judge_max_parse_retries"
_FORCE_JUDGE_ON_PRIOR_FAILURE_KEY = "eval.force_judge_on_prior_failure"

REQUIRED_EVALUATION_SETTING_KEYS: frozenset[str] = frozenset(
    {
        _SANITY_MIN_CHARS_KEY,
        _SANITY_ERROR_MARKERS_KEY,
        _KEYWORD_SEMANTIC_PASS_THRESHOLD_KEY,
        _JUDGE_MAX_COMPLETION_TOKENS_KEY,
        _JUDGE_MAX_PARSE_RETRIES_KEY,
        _FORCE_JUDGE_ON_PRIOR_FAILURE_KEY,
    }
)

_TRUE_LITERALS = frozenset({"true", "1", "yes"})


@dataclass(slots=True, frozen=True)
class _EvaluationParameters:
    """This module's per-run eval.* parameters, parsed once at construction (§7)."""

    sanity_min_chars: int
    sanity_error_markers: tuple[str, ...]
    keyword_semantic_pass_threshold: float
    judge_max_completion_tokens: int
    judge_max_parse_retries: int
    force_judge_on_prior_failure: bool


def parse_evaluation_parameters(
    snapshot: tuple[BenchmarkRunSettingEntry, ...],
) -> _EvaluationParameters:
    """Read this module's eval.* keys once from the frozen run snapshot (§7).

    Args:
        snapshot: The run's frozen per-run-overridable settings; must carry
            every key in ``REQUIRED_EVALUATION_SETTING_KEYS`` (enforced by
            each ``api.py`` factory's icontract precondition, not here).

    Returns:
        The parsed ``_EvaluationParameters`` for this run.
    """
    values = {entry.setting_key: entry.setting_value for entry in snapshot}
    markers = tuple(
        marker.strip() for marker in values[_SANITY_ERROR_MARKERS_KEY].split(",") if marker.strip()
    )
    return _EvaluationParameters(
        sanity_min_chars=int(values[_SANITY_MIN_CHARS_KEY]),
        sanity_error_markers=markers,
        keyword_semantic_pass_threshold=float(values[_KEYWORD_SEMANTIC_PASS_THRESHOLD_KEY]),
        judge_max_completion_tokens=int(values[_JUDGE_MAX_COMPLETION_TOKENS_KEY]),
        judge_max_parse_retries=int(values[_JUDGE_MAX_PARSE_RETRIES_KEY]),
        force_judge_on_prior_failure=(
            values[_FORCE_JUDGE_ON_PRIOR_FAILURE_KEY].strip().lower() in _TRUE_LITERALS
        ),
    )
