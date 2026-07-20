"""Unit tests for the Details tab's pure select.py — no Qt import."""

import pytest

from ollama_llm_bench.backend.domain import (
    AttemptOutcome,
    BenchmarkResultAttempt,
    ResolutionLayer,
    ResultStatus,
    RunMode,
    Verdict,
)
from ollama_llm_bench.ui.results._internal.details_tab.select import (
    DetailsColumnKey,
    badge_role_for_layer,
    badge_role_for_status,
    badge_role_for_verdict,
    build_detail_panel,
    chip_domains,
    decode_view_state,
    default_view_state,
    encode_view_state,
    map_details_rows,
    offered_columns,
)
from ollama_llm_bench.ui.results._internal.details_tab.tests.conftest import make_result, make_task

_GRADED_ONLY_COUNT = 8
_TOTAL_COLUMNS = 24
_TWO_DISTINCT_MODEL_KEYS = 2
_TWO_ROWS = 2
_ATTEMPT_DURATION_MS = 1200


def test_graded_mode_offers_all_twenty_four_columns() -> None:
    """Proves: STORY-063

    §4 says GRADED offers all 24 columns of the §3 master list.
    """
    # Arrange / Act
    columns = offered_columns(RunMode.GRADED)
    # Assert
    assert len(columns) == _TOTAL_COLUMNS


def test_synthetic_mode_hides_the_eight_grading_columns() -> None:
    """Proves: STORY-063

    §4: SYNTHETIC and TASKS drop Sanity check, Keyword, Cosine Score, Cosine
    verdict, Judge, Layer, Verdict, Reason.
    """
    # Arrange / Act
    columns = offered_columns(RunMode.SYNTHETIC)
    # Assert
    assert len(columns) == _TOTAL_COLUMNS - _GRADED_ONLY_COUNT
    assert DetailsColumnKey.VERDICT not in columns
    assert DetailsColumnKey.PROVIDER_MODEL in columns


def test_chip_domains_lists_two_providers_of_the_same_model_separately() -> None:
    """Proves: STORY-063-AC-1

    Covers EC-RES-2. Two results share model_name "llama3" under two distinct
    provider_ids; the Models chip domain must list them as two separate entries.
    """
    # Arrange
    result_a = make_result(provider_id="prov-a", provider_name="Ollama Local", model_name="llama3")
    result_b = make_result(provider_id="prov-b", provider_name="Ollama Remote", model_name="llama3")
    # Act
    domains = chip_domains(results=(result_a, result_b), tasks_by_id={})
    # Assert
    assert len(domains.models) == _TWO_DISTINCT_MODEL_KEYS


@pytest.mark.parametrize(
    ("verdict", "expected_role"),
    [
        (Verdict.PASS, "success"),
        (Verdict.FAIL, "error"),
        (None, "muted"),
    ],
)
def test_badge_role_for_verdict(verdict: Verdict | None, expected_role: str) -> None:
    """Proves: STORY-063-AC-2"""
    assert badge_role_for_verdict(verdict) == expected_role


@pytest.mark.parametrize(
    ("status", "expected_role"),
    [
        (ResultStatus.COMPLETED, "success"),
        (ResultStatus.FAILED_INFERENCE, "error"),
        (ResultStatus.FAILED_PROVIDER, "error"),
        (ResultStatus.FAILED_TIMEOUT, "error"),
        (ResultStatus.FAILED_JUDGE_TIMEOUT, "error"),
        (ResultStatus.ERRORED, "error"),
        (ResultStatus.PENDING, "info"),
        (ResultStatus.RUNNING_INFERENCE, "info"),
        (ResultStatus.AWAITING_KEYWORD_CHECK, "info"),
        (ResultStatus.AWAITING_COSINE_CHECK, "info"),
        (ResultStatus.AWAITING_JUDGE_CHECK, "info"),
    ],
)
def test_badge_role_for_status(status: ResultStatus, expected_role: str) -> None:
    """Proves: STORY-063-AC-2"""
    assert badge_role_for_status(status) == expected_role


@pytest.mark.parametrize(
    ("layer", "expected_role"),
    [
        (ResolutionLayer.KEYWORD, "info"),
        (ResolutionLayer.COSINE, "info"),
        (ResolutionLayer.JUDGE, "info"),
        (ResolutionLayer.SKIP, "muted"),
        (None, "muted"),
    ],
)
def test_badge_role_for_layer(layer: ResolutionLayer | None, expected_role: str) -> None:
    """Proves: STORY-063-AC-2"""
    assert badge_role_for_layer(layer) == expected_role


def test_default_view_state_selects_time_descending_sort() -> None:
    """Proves: STORY-063"""
    # Arrange / Act
    state = default_view_state(RunMode.GRADED)
    # Assert
    assert state.sort.column == DetailsColumnKey.TIME_MS
    assert state.sort.descending is True


def test_encode_decode_view_state_round_trips() -> None:
    """Proves: STORY-063"""
    # Arrange
    state = default_view_state(RunMode.GRADED)
    # Act
    restored = decode_view_state(encode_view_state(state))
    # Assert
    assert restored == state


def test_composite_key_keeps_rows_distinct() -> None:
    """Proves: STORY-063-AC-1

    Covers EC-RES-2. Two results share model_name "llama3" under two distinct
    provider_ids; both rows must appear distinctly and the Models chip domain
    (already proven separately in Task 2) must not merge them.
    """
    # Arrange
    result_a = make_result(
        result_id=1, provider_id="prov-a", provider_name="Ollama Local", model_name="llama3"
    )
    result_b = make_result(
        result_id=2, provider_id="prov-b", provider_name="Ollama Remote", model_name="llama3"
    )
    task = make_task(task_id="task-1")
    view_state = default_view_state(RunMode.GRADED)
    # Act
    vm = map_details_rows(
        results=(result_a, result_b),
        tasks_by_id={"task-1": task},
        run_mode=RunMode.GRADED,
        view_state=view_state,
        score_display_format="decimal",
    )
    # Assert
    assert len(vm.rows) == _TWO_ROWS
    assert {row.result_id for row in vm.rows} == {1, 2}


def test_ttft_none_renders_em_dash_not_zero() -> None:
    """Proves: STORY-063

    §3.2: a None cell renders an em dash, never 0. Covers DT-EC-1.
    """
    # Arrange
    result = make_result(result_id=1, ttft_ms=None)
    view_state = default_view_state(RunMode.GRADED)
    # Act
    vm = map_details_rows(
        results=(result,),
        tasks_by_id={},
        run_mode=RunMode.GRADED,
        view_state=view_state,
        score_display_format="decimal",
    )
    visible_order = [c for c in view_state.columns.order if c in view_state.columns.visible]
    ttft_index = visible_order.index(DetailsColumnKey.TTFT_MS)
    # Assert
    assert vm.rows[0].cells[ttft_index] == "—"


def test_build_detail_panel_renders_ordered_sections_with_em_dashes() -> None:
    """Proves: STORY-063-AC-3"""
    # Arrange
    attempt = BenchmarkResultAttempt(
        attempt_index=1,
        timeout_ms=5000,
        duration_ms=_ATTEMPT_DURATION_MS,
        outcome=AttemptOutcome.SUCCESS,
        error_kind=None,
        error_message=None,
    )
    result = make_result(
        result_id=1,
        status=ResultStatus.COMPLETED,
        verdict=Verdict.PASS,
        keyword_verdict=Verdict.PASS,
        judge_verdict=Verdict.PASS,
        resolution_layer=ResolutionLayer.JUDGE,
        judge_reasoning="The response correctly answers the question.",
        cosine_similarity=None,
        attempts=(attempt,),
    )
    task = make_task(task_id="task-1", golden_answer="The answer is 42.")
    # Act
    panel = build_detail_panel(result=result, task=task, run_mode=RunMode.GRADED)
    # Assert
    assert panel.result_id == 1
    assert panel.golden_answer == "The answer is 42."
    assert panel.judge_reasoning == "The response correctly answers the question."
    assert panel.error_message == "(none)"
    identity_labels = [label for label, _value in panel.identity_fields]
    assert "provider_name" not in identity_labels  # human labels, not raw field names
    assert identity_labels == [
        "Provider",
        "Model",
        "Run mode",
        "Task ID",
        "Category",
        "Sub-category",
        "Difficulty",
        "Cosine enabled",
        "Total time (ms)",
        "TTFT (ms)",
        "Tokens per second",
        "Prompt tokens",
        "Completion tokens",
        "Status",
        "Verdict",
        "Resolution layer",
        "Cosine Score",
        "Attempts",
        "Started at",
        "Finished at",
    ]


def test_build_detail_panel_renders_em_dash_value_for_none_cosine_score() -> None:
    """Proves: STORY-063-AC-3

    The fixture's ``cosine_similarity=None`` must render as the em dash on the
    identity grid's "Cosine Score" value, not merely appear as a labelled row.
    """
    # Arrange
    result = make_result(result_id=1, cosine_similarity=None)
    task = make_task(task_id="task-1")
    # Act
    panel = build_detail_panel(result=result, task=task, run_mode=RunMode.GRADED)
    identity_by_label = dict(panel.identity_fields)
    # Assert
    assert identity_by_label["Cosine Score"] == "—"


def test_build_detail_panel_phase_evaluations_include_keyword_and_judge_rows() -> None:
    """Proves: STORY-063-AC-3

    Covers ``_phase_evaluations``'s gated-row logic and ``_judge_phase_row``'s
    PASS/FAIL sub-case: a fixture with ``keyword_verdict=PASS`` and
    ``judge_verdict=PASS`` (no sanity check, no cosine score) must produce
    exactly a Keyword row followed by a Judge row, in that order.
    """
    # Arrange
    result = make_result(
        result_id=1,
        keyword_verdict=Verdict.PASS,
        judge_verdict=Verdict.PASS,
        resolution_layer=ResolutionLayer.JUDGE,
        cosine_similarity=None,
    )
    task = make_task(task_id="task-1")
    # Act
    panel = build_detail_panel(result=result, task=task, run_mode=RunMode.GRADED)
    # Assert
    assert [row.phase_name for row in panel.phase_evaluations] == ["Keyword", "Judge"]
    assert panel.phase_evaluations[1].outcome == "PASS"


def test_build_detail_panel_maps_attempt_history_rows() -> None:
    """Proves: STORY-063-AC-3

    Covers ``_attempt_rows``'s field-by-field mapping from
    ``BenchmarkResultAttempt`` to ``AttemptRow``.
    """
    # Arrange
    attempt = BenchmarkResultAttempt(
        attempt_index=1,
        timeout_ms=5000,
        duration_ms=_ATTEMPT_DURATION_MS,
        outcome=AttemptOutcome.SUCCESS,
        error_kind=None,
        error_message=None,
    )
    result = make_result(result_id=1, attempts=(attempt,))
    task = make_task(task_id="task-1")
    # Act
    panel = build_detail_panel(result=result, task=task, run_mode=RunMode.GRADED)
    # Assert
    assert len(panel.attempts) == 1
    assert panel.attempts[0].duration_ms == _ATTEMPT_DURATION_MS
