import pytest

from ollama_llm_bench.backend.core.models import RunMode
from ollama_llm_bench.backend.services.mode_visibility_policy import (
    ModeVisibilityPolicy,
    VisibilityFeatureFlags,
)


@pytest.fixture
def policy() -> ModeVisibilityPolicy:
    return ModeVisibilityPolicy()


@pytest.fixture
def default_flags() -> VisibilityFeatureFlags:
    return VisibilityFeatureFlags()


@pytest.mark.parametrize(
    "mode,expected_visible,expected_hidden",
    [
        (
            RunMode.PERFORMANCE,
            {"test_models_section", "performance_matrix", "advanced_section"},
            {"judge_section", "prompt_variants_section", "task_files_section"},
        ),
        (
            RunMode.SPEED,
            {"judge_section", "test_models_section", "task_files_section", "advanced_section"},
            {"performance_matrix", "prompt_variants_section"},
        ),
        (
            RunMode.PROMPT_EVAL,
            {
                "judge_section",
                "test_models_section",
                "task_files_section",
                "advanced_section",
                "prompt_variants_section",
            },
            {"performance_matrix"},
        ),
        (
            RunMode.FULL_GRADING,
            {"judge_section", "test_models_section", "task_files_section", "advanced_section"},
            {"performance_matrix", "prompt_variants_section"},
        ),
    ],
    ids=["performance", "speed", "prompt_eval", "full_grading"],
)
def test_base_policy(
    policy: ModeVisibilityPolicy,
    default_flags: VisibilityFeatureFlags,
    mode: RunMode,
    expected_visible: set[str],
    expected_hidden: set[str],
) -> None:
    visible = policy.get_visible_keys(mode, default_flags)
    assert expected_visible.issubset(visible)
    assert not expected_hidden.intersection(visible)


def test_visibility_for_performance_excludes_task_files(
    policy: ModeVisibilityPolicy,
    default_flags: VisibilityFeatureFlags,
) -> None:
    visible = policy.get_visible_keys(RunMode.PERFORMANCE, default_flags)
    assert "task_files_section" not in visible


def test_visibility_for_speed_includes_task_files(
    policy: ModeVisibilityPolicy,
    default_flags: VisibilityFeatureFlags,
) -> None:
    visible = policy.get_visible_keys(RunMode.SPEED, default_flags)
    assert "task_files_section" in visible


def test_visibility_for_full_grading_includes_task_files(
    policy: ModeVisibilityPolicy,
    default_flags: VisibilityFeatureFlags,
) -> None:
    visible = policy.get_visible_keys(RunMode.FULL_GRADING, default_flags)
    assert "task_files_section" in visible


def test_visibility_for_prompt_eval_includes_task_files(
    policy: ModeVisibilityPolicy,
    default_flags: VisibilityFeatureFlags,
) -> None:
    visible = policy.get_visible_keys(RunMode.PROMPT_EVAL, default_flags)
    assert "task_files_section" in visible


@pytest.mark.parametrize(
    "mode,key,expect_visible",
    [
        # PERFORMANCE: task_files hidden, test_models + perf_matrix + advanced visible
        (RunMode.PERFORMANCE, "test_models_section", True),
        (RunMode.PERFORMANCE, "performance_matrix", True),
        (RunMode.PERFORMANCE, "advanced_section", True),
        (RunMode.PERFORMANCE, "task_files_section", False),
        (RunMode.PERFORMANCE, "judge_section", False),
        (RunMode.PERFORMANCE, "prompt_variants_section", False),
        # SPEED: task_files + test_models + judge + advanced visible
        (RunMode.SPEED, "task_files_section", True),
        (RunMode.SPEED, "test_models_section", True),
        (RunMode.SPEED, "judge_section", True),
        (RunMode.SPEED, "advanced_section", True),
        (RunMode.SPEED, "performance_matrix", False),
        (RunMode.SPEED, "prompt_variants_section", False),
        # FULL_GRADING: task_files + test_models + judge + advanced visible
        (RunMode.FULL_GRADING, "task_files_section", True),
        (RunMode.FULL_GRADING, "test_models_section", True),
        (RunMode.FULL_GRADING, "judge_section", True),
        (RunMode.FULL_GRADING, "advanced_section", True),
        (RunMode.FULL_GRADING, "performance_matrix", False),
        (RunMode.FULL_GRADING, "prompt_variants_section", False),
        # PROMPT_EVAL: task_files + judge + test_models + advanced + prompt_variants visible
        (RunMode.PROMPT_EVAL, "task_files_section", True),
        (RunMode.PROMPT_EVAL, "judge_section", True),
        (RunMode.PROMPT_EVAL, "advanced_section", True),
        (RunMode.PROMPT_EVAL, "prompt_variants_section", True),
        (RunMode.PROMPT_EVAL, "test_models_section", True),
        (RunMode.PROMPT_EVAL, "performance_matrix", False),
    ],
    ids=[
        "perf_test_models_visible",
        "perf_perf_matrix_visible",
        "perf_advanced_visible",
        "perf_task_files_hidden",
        "perf_judge_hidden",
        "perf_prompt_variants_hidden",
        "speed_task_files_visible",
        "speed_test_models_visible",
        "speed_judge_visible",
        "speed_advanced_visible",
        "speed_perf_matrix_hidden",
        "speed_prompt_variants_hidden",
        "full_grading_task_files_visible",
        "full_grading_test_models_visible",
        "full_grading_judge_visible",
        "full_grading_advanced_visible",
        "full_grading_perf_matrix_hidden",
        "full_grading_prompt_variants_hidden",
        "prompt_eval_task_files_visible",
        "prompt_eval_judge_visible",
        "prompt_eval_advanced_visible",
        "prompt_eval_prompt_variants_visible",
        "prompt_eval_test_models_visible",
        "prompt_eval_perf_matrix_hidden",
    ],
)
def test_visibility_table_canonical(
    policy: ModeVisibilityPolicy,
    default_flags: VisibilityFeatureFlags,
    mode: RunMode,
    key: str,
    expect_visible: bool,
) -> None:
    visible = policy.get_visible_keys(mode, default_flags)
    if expect_visible:
        assert key in visible, f"Expected {key!r} visible for {mode}"
    else:
        assert key not in visible, f"Expected {key!r} hidden for {mode}"


def test_judge_run_analysis_enabled_shows_judge_for_performance(
    policy: ModeVisibilityPolicy,
) -> None:
    flags = VisibilityFeatureFlags(judge_run_analysis_enabled=True)
    visible = policy.get_visible_keys(RunMode.PERFORMANCE, flags)
    assert "judge_section" in visible


def test_judge_run_analysis_flag_does_not_affect_other_keys(
    policy: ModeVisibilityPolicy,
) -> None:
    flags_off = VisibilityFeatureFlags(judge_run_analysis_enabled=False)
    flags_on = VisibilityFeatureFlags(judge_run_analysis_enabled=True)
    for mode in RunMode:
        off_keys = policy.get_visible_keys(mode, flags_off) - {"judge_section"}
        on_keys = policy.get_visible_keys(mode, flags_on) - {"judge_section"}
        assert off_keys == on_keys, f"Flag changed non-judge keys for mode {mode}"


@pytest.mark.parametrize(
    "mode,flag,expect_judge",
    [
        (RunMode.PERFORMANCE, False, False),
        (RunMode.PERFORMANCE, True, True),
        (RunMode.SPEED, False, True),  # SPEED always has judge_section in base
        (RunMode.SPEED, True, True),
        (RunMode.FULL_GRADING, False, True),
        (RunMode.FULL_GRADING, True, True),
        (RunMode.PROMPT_EVAL, False, True),
        (RunMode.PROMPT_EVAL, True, True),
    ],
    ids=[
        "perf_flag_off",
        "perf_flag_on",
        "speed_flag_off",
        "speed_flag_on",
        "full_grading_flag_off",
        "full_grading_flag_on",
        "prompt_eval_flag_off",
        "prompt_eval_flag_on",
    ],
)
def test_judge_section_visibility_all_modes_and_flags(
    policy: ModeVisibilityPolicy,
    mode: RunMode,
    flag: bool,
    expect_judge: bool,
) -> None:
    flags = VisibilityFeatureFlags(judge_run_analysis_enabled=flag)
    visible = policy.get_visible_keys(mode, flags)
    if expect_judge:
        assert "judge_section" in visible, f"Expected judge_section for mode={mode} flag={flag}"
    else:
        assert "judge_section" not in visible, f"Unexpected judge_section for mode={mode} flag={flag}"
