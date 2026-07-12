"""Read the three snapshot flags that gate Check 3 / Check 4 (spec §7).

Follows the exact literal-key + ``_coerce_bool`` convention used by
``backend/circuit_breaker/_internal/parameters.py``. A missing key defaults to
``False`` (the flag/phase is treated as not needed) — this function never raises.
"""

from ollama_llm_bench.backend.domain import BenchmarkRunSettingEntry

__all__: list[str] = ["needs_cosine_phase", "needs_judge"]

_PHASE_JUDGE_ENABLED_KEY = "eval.phase_judge_enabled"
_JUDGE_RUN_ANALYSIS_ENABLED_KEY = "feature.judge_run_analysis_enabled"
_PHASE_COSINE_ENABLED_KEY = "eval.phase_cosine_enabled"


def needs_judge(snapshot: tuple[BenchmarkRunSettingEntry, ...]) -> bool:
    """Whether the run's frozen snapshot needs the judge (spec §6.3, §7)."""
    values = _index(snapshot)
    return _coerce_bool(values.get(_PHASE_JUDGE_ENABLED_KEY, "")) or _coerce_bool(
        values.get(_JUDGE_RUN_ANALYSIS_ENABLED_KEY, "")
    )


def needs_cosine_phase(snapshot: tuple[BenchmarkRunSettingEntry, ...]) -> bool:
    """Whether the run's frozen snapshot runs the cosine phase (spec §6.4, §7)."""
    values = _index(snapshot)
    return _coerce_bool(values.get(_PHASE_COSINE_ENABLED_KEY, ""))


def _index(snapshot: tuple[BenchmarkRunSettingEntry, ...]) -> dict[str, str]:
    return {entry.setting_key: entry.setting_value for entry in snapshot}


def _coerce_bool(raw: str) -> bool:
    """Coerce a registry-storage-form boolean string to ``bool``."""
    return raw.strip().lower() == "true"
