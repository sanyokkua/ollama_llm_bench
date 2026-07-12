"""ConfigSection and Visibility enums owned by the mode-visibility policy.

Source of truth: docs/v3_specification/11_Services_and_Algorithms/10_MODE_VISIBILITY_POLICY.md
§3 (the Visibility outputs) and §6.1 (the ConfigSection vocabulary). Neither enum is a
persisted-enum-catalog member — both are structural UI-layout types, not user-tunable or
persisted values.
"""

from enum import StrEnum


class ConfigSection(StrEnum):
    """The ten New Benchmark configuration sections the policy governs (§6.1).

    Declared in the same order as the §6.2 policy table's rows; `visible_sections`
    relies on this declaration order for its stable-order contract (STORY-024-AC-3).
    """

    RUN_MODE_SELECTOR = "run_mode_selector"
    TEST_MODELS_PICKER = "test_models_picker"
    INPUT_SIZES = "input_sizes"
    OUTPUT_SIZES = "output_sizes"
    REPEATS = "repeats"
    TASK_FILES = "task_files"
    JUDGE_MODEL_PICKER = "judge_model_picker"
    EMBEDDING_MODEL_INFO = "embedding_model_info"
    RUN_ANALYSIS_TOGGLE = "run_analysis_toggle"
    ADVANCED_OPTIONS = "advanced_options"


class Visibility(StrEnum):
    """The four visibility states a policy cell may resolve to (§3).

    VISIBLE, VISIBLE_REQUIRED, and VISIBLE_FORCED are all "shown" states; HIDDEN is
    the only "not shown" state.
    """

    VISIBLE = "visible"
    VISIBLE_REQUIRED = "visible_required"
    VISIBLE_FORCED = "visible_forced"
    HIDDEN = "hidden"
