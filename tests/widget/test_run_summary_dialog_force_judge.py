"""Tests for RunSummaryDialog judge-section visibility.

These tests verify that the judge section is shown/hidden correctly based on
run_mode and judge_run_analysis_enabled in the RunSummary snapshot.

Requires QApplication — skipped in headless CI without a display server.
"""

import pytest

pytest.importorskip("PySide6.QtWidgets", reason="PySide6 not available")


from PySide6.QtWidgets import QApplication

from ollama_llm_bench.backend.core.models import (
    AdvancedRunOptions,
    RunMode,
    RunSummary,
)
from ollama_llm_bench.ui.widgets.panels.run_summary_dialog import RunSummaryDialog


@pytest.fixture(scope="module")
def qapp() -> QApplication:
    existing = QApplication.instance()
    if existing is not None:
        return existing  # type: ignore[return-value]
    return QApplication([])


def _make_summary(
    *,
    run_mode: RunMode,
    judge_run_analysis_enabled: bool,
    judge_provider_id: str | None = None,
    judge_model_name: str | None = None,
) -> RunSummary:
    return RunSummary(
        run_mode=run_mode,
        judge_provider_id=judge_provider_id,
        judge_model_name=judge_model_name,
        selected_models=[],
        task_file_paths=[],
        advanced_options=AdvancedRunOptions(
            streaming_enabled=True,
            warmup_enabled=True,
            reasoning_effort="default",
            streaming_is_override=False,
            warmup_is_override=False,
            reasoning_is_override=False,
        ),
        performance_input_sizes=[],
        performance_output_sizes=[],
        performance_repeats=1,
        judge_run_analysis_enabled=judge_run_analysis_enabled,
    )


def test_performance_flag_off_hides_judge_section(qapp: QApplication) -> None:
    summary = _make_summary(run_mode=RunMode.PERFORMANCE, judge_run_analysis_enabled=False)
    dialog = RunSummaryDialog(summary=summary)
    assert dialog._judge_section.isHidden()
    dialog.close()


def test_performance_flag_on_no_judge_shows_section_with_warning(qapp: QApplication) -> None:
    summary = _make_summary(
        run_mode=RunMode.PERFORMANCE,
        judge_run_analysis_enabled=True,
        judge_provider_id=None,
        judge_model_name=None,
    )
    dialog = RunSummaryDialog(summary=summary)
    assert not dialog._judge_section.isHidden()
    assert dialog._no_judge_warning is not None
    dialog.close()


def test_performance_flag_on_with_judge_shows_section_no_warning(qapp: QApplication) -> None:
    summary = _make_summary(
        run_mode=RunMode.PERFORMANCE,
        judge_run_analysis_enabled=True,
        judge_provider_id="ollama",
        judge_model_name="qwen3:8b",
    )
    dialog = RunSummaryDialog(summary=summary)
    assert not dialog._judge_section.isHidden()
    assert dialog._no_judge_warning is None
    dialog.close()


def test_full_grading_always_shows_judge_section(qapp: QApplication) -> None:
    summary = _make_summary(run_mode=RunMode.FULL_GRADING, judge_run_analysis_enabled=False)
    dialog = RunSummaryDialog(summary=summary)
    assert not dialog._judge_section.isHidden()
    dialog.close()


def test_prompt_eval_always_shows_judge_section(qapp: QApplication) -> None:
    summary = _make_summary(run_mode=RunMode.PROMPT_EVAL, judge_run_analysis_enabled=False)
    dialog = RunSummaryDialog(summary=summary)
    assert not dialog._judge_section.isHidden()
    dialog.close()
