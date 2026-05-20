"""Unit tests for RetrySelectionDialog — retryable task selection logic."""

from __future__ import annotations

import pytest
from PySide6.QtWidgets import QApplication

from ollama_llm_bench.backend.core.models import BenchmarkResult, BenchmarkResultStatus
from ollama_llm_bench.ui.widgets.panels.retry_selection_dialog import RetrySelectionDialog


@pytest.fixture(scope="module")
def qapp() -> QApplication:
    instance = QApplication.instance()
    if isinstance(instance, QApplication):
        return instance
    return QApplication([])


def _make_result(
    result_id: int,
    status: BenchmarkResultStatus,
    task_id: str = "t1",
) -> BenchmarkResult:
    return BenchmarkResult(
        run_id=1,
        result_id=result_id,
        task_id=task_id,
        provider_id="p1",
        model_name="m1",
        status=status,
    )


def test_retry_selection_dialog_shows_failed_results(qapp: QApplication) -> None:
    results = [
        _make_result(1, BenchmarkResultStatus.COMPLETED),
        _make_result(2, BenchmarkResultStatus.FAILED),
        _make_result(3, BenchmarkResultStatus.NOT_COMPLETED),
    ]
    dlg = RetrySelectionDialog(run_id=1, results=results)

    shown_ids = {rid for _, rid in dlg._checkboxes}
    assert 2 in shown_ids, "FAILED result must appear in the dialog"
    assert 3 in shown_ids, "NOT_COMPLETED result must appear in the dialog"
    assert 1 not in shown_ids, "clean COMPLETED result must NOT appear in the dialog"


def test_retry_selection_dialog_excludes_clean_completed(qapp: QApplication) -> None:
    results = [
        _make_result(1, BenchmarkResultStatus.COMPLETED),
        _make_result(2, BenchmarkResultStatus.COMPLETED),
    ]
    dlg = RetrySelectionDialog(run_id=1, results=results)

    assert dlg._checkboxes == [], "No checkboxes should be shown when all results are cleanly COMPLETED"


def test_retry_selection_dialog_shows_waiting_for_judge(qapp: QApplication) -> None:
    results = [_make_result(1, BenchmarkResultStatus.WAITING_FOR_JUDGE)]
    dlg = RetrySelectionDialog(run_id=1, results=results)

    shown_ids = {rid for _, rid in dlg._checkboxes}
    assert 1 in shown_ids


def test_retry_selection_dialog_all_checkboxes_checked_by_default(qapp: QApplication) -> None:
    results = [
        _make_result(1, BenchmarkResultStatus.FAILED),
        _make_result(2, BenchmarkResultStatus.NOT_COMPLETED),
    ]
    dlg = RetrySelectionDialog(run_id=1, results=results)

    assert all(cb.isChecked() for cb, _ in dlg._checkboxes)
