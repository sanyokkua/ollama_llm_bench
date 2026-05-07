"""Tests for RunSummaryDialog task-files section visibility.

Verifies that the Task Files collapsible is hidden for RunMode.PERFORMANCE
and visible for all other modes, and that the Start button is enabled for
Performance mode even when no task files are provided.

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
    task_file_paths: list | None = None,
    selected_models: list | None = None,
) -> RunSummary:
    return RunSummary(
        run_mode=run_mode,
        judge_provider_id=None,
        judge_model_name=None,
        selected_models=selected_models if selected_models is not None else [],
        task_file_paths=task_file_paths if task_file_paths is not None else [],
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
        judge_run_analysis_enabled=False,
    )


def test_dialog_hides_task_files_for_performance_mode(qapp: QApplication) -> None:
    summary = _make_summary(run_mode=RunMode.PERFORMANCE)
    dialog = RunSummaryDialog(summary=summary)
    assert dialog._task_files_section.isHidden()
    dialog.close()


@pytest.mark.parametrize(
    "mode",
    [RunMode.SPEED, RunMode.FULL_GRADING, RunMode.PROMPT_EVAL],
    ids=["speed", "full_grading", "prompt_eval"],
)
def test_dialog_shows_task_files_for_non_performance_modes(qapp: QApplication, mode: RunMode) -> None:
    summary = _make_summary(run_mode=mode)
    dialog = RunSummaryDialog(summary=summary)
    assert not dialog._task_files_section.isHidden()
    dialog.close()


def test_start_enabled_for_performance_without_task_files(qapp: QApplication) -> None:
    from ollama_llm_bench.backend.core.models import ModelSelectionKey

    models = [ModelSelectionKey(provider_id="ollama", model_name="llama3.2:3b")]
    summary = _make_summary(run_mode=RunMode.PERFORMANCE, task_file_paths=[], selected_models=models)
    dialog = RunSummaryDialog(summary=summary)
    assert dialog._start_btn.isEnabled() is True
    dialog.close()
