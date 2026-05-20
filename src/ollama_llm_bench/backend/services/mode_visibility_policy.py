"""Mode-aware widget visibility policy for the Left Panel."""

from dataclasses import dataclass

from ollama_llm_bench.backend.core.models import RunMode

_ALL_KEYS: frozenset[str] = frozenset(
    {
        "judge_section",
        "test_models_section",
        "task_files_section",
        "performance_matrix",
        "advanced_section",
        "prompt_variants_section",
    }
)

_BASE_POLICY: dict[RunMode, frozenset[str]] = {
    RunMode.PERFORMANCE: frozenset(
        {
            "test_models_section",
            "performance_matrix",
            "advanced_section",
        }
    ),
    RunMode.SPEED: frozenset(
        {
            "judge_section",
            "test_models_section",
            "task_files_section",
            "advanced_section",
        }
    ),
    RunMode.PROMPT_EVAL: frozenset(
        {
            "judge_section",
            "test_models_section",
            "task_files_section",
            "advanced_section",
            "prompt_variants_section",
        }
    ),
    RunMode.FULL_GRADING: frozenset(
        {
            "judge_section",
            "test_models_section",
            "task_files_section",
            "advanced_section",
        }
    ),
}


@dataclass(frozen=True, slots=True)
class VisibilityFeatureFlags:
    """Feature flags that modify the base visibility policy."""

    judge_run_analysis_enabled: bool = False


class ModeVisibilityPolicy:
    """Computes the set of widget keys that should be visible for a given mode + flags."""

    def get_visible_keys(self, mode: RunMode, flags: VisibilityFeatureFlags) -> frozenset[str]:
        """Return the set of widget keys that should be visible.

        Args:
            mode: The current run mode.
            flags: Active feature flags that may override base policy.

        Returns:
            Frozenset of widget key strings that should be visible.
        """
        base = _BASE_POLICY[mode]
        if flags.judge_run_analysis_enabled and mode == RunMode.PERFORMANCE:
            base = base | {"judge_section"}
        return base
