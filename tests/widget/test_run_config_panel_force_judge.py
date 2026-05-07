"""Tests for judge-section visibility policy integration with RunConfigPanel.

These tests exercise ModeVisibilityPolicy + VisibilityFeatureFlags directly,
verifying that the judge_run_analysis_enabled flag gates judge_section visibility
for PERFORMANCE mode while leaving other modes unaffected.

No QApplication is required — only policy logic is tested.
"""

import pytest

from ollama_llm_bench.backend.core.models import RunMode
from ollama_llm_bench.backend.services.mode_visibility_policy import (
    ModeVisibilityPolicy,
    VisibilityFeatureFlags,
)


@pytest.fixture
def policy() -> ModeVisibilityPolicy:
    return ModeVisibilityPolicy()


def test_performance_mode_hides_judge_section_when_flag_off(policy: ModeVisibilityPolicy) -> None:
    flags = VisibilityFeatureFlags(judge_run_analysis_enabled=False)
    visible = policy.get_visible_keys(RunMode.PERFORMANCE, flags)
    assert "judge_section" not in visible


def test_performance_mode_shows_judge_section_when_flag_on(policy: ModeVisibilityPolicy) -> None:
    flags = VisibilityFeatureFlags(judge_run_analysis_enabled=True)
    visible = policy.get_visible_keys(RunMode.PERFORMANCE, flags)
    assert "judge_section" in visible


def test_full_grading_always_shows_judge_section_regardless_of_flag(policy: ModeVisibilityPolicy) -> None:
    flags = VisibilityFeatureFlags(judge_run_analysis_enabled=False)
    visible = policy.get_visible_keys(RunMode.FULL_GRADING, flags)
    assert "judge_section" in visible


def test_speed_always_shows_judge_section_regardless_of_flag(policy: ModeVisibilityPolicy) -> None:
    flags = VisibilityFeatureFlags(judge_run_analysis_enabled=False)
    visible = policy.get_visible_keys(RunMode.SPEED, flags)
    assert "judge_section" in visible


def test_prompt_eval_always_shows_judge_section_regardless_of_flag(policy: ModeVisibilityPolicy) -> None:
    flags = VisibilityFeatureFlags(judge_run_analysis_enabled=False)
    visible = policy.get_visible_keys(RunMode.PROMPT_EVAL, flags)
    assert "judge_section" in visible


def test_flag_only_affects_judge_section_not_other_keys(policy: ModeVisibilityPolicy) -> None:
    flags_off = VisibilityFeatureFlags(judge_run_analysis_enabled=False)
    flags_on = VisibilityFeatureFlags(judge_run_analysis_enabled=True)
    for mode in RunMode:
        off_keys = policy.get_visible_keys(mode, flags_off) - {"judge_section"}
        on_keys = policy.get_visible_keys(mode, flags_on) - {"judge_section"}
        assert off_keys == on_keys, f"Flag changed non-judge keys for mode {mode}"
