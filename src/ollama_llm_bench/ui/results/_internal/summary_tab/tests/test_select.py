"""Colocated unit tests (no Qt) for ``select.py``'s pure aggregation (STORY-062).

Covers STORY-062-AC-1, AC-3, AC-4 plus additional DoD-only coverage of every
public function in ``select.py`` -- see the story's Test plan section.
"""

import msgspec
import pytest

from ollama_llm_bench.backend.domain import (
    Difficulty,
    ResolutionLayer,
    ResultStatus,
    RunMode,
    Verdict,
)
from ollama_llm_bench.ui.results._internal.summary_tab.select import (
    ColumnFilterEntry,
    SummaryColumnKey,
    SummaryColumnLayout,
    SummarySort,
    SummaryViewState,
    aggregate_summary,
    chip_domains,
    column_filter_domain,
    column_label,
    decode_view_state,
    default_view_state,
    encode_view_state,
    offered_columns,
)
from ollama_llm_bench.ui.results._internal.summary_tab.tests.conftest import make_result, make_task

_EM_DASH = "—"

_GRADING_COLUMNS = frozenset(
    {
        SummaryColumnKey.PASS_RATE,
        SummaryColumnKey.COSINE_SCORE,
        SummaryColumnKey.JUDGE_PASS,
        SummaryColumnKey.JUDGE_FAIL,
        SummaryColumnKey.JUDGE_TIMEOUT_FAILURES,
        SummaryColumnKey.LAYER_MIX,
    }
)


def _column_index(columns: tuple[str, ...], column: SummaryColumnKey) -> int:
    """Locate ``column``'s position, tolerating an appended sort caret."""
    label = column_label(column)
    stripped = tuple(header.removesuffix(" ▼").removesuffix(" ▲") for header in columns)
    return stripped.index(label)


def _all_columns_visible_state(run_mode: RunMode) -> SummaryViewState:
    """A view state offering every mode-offered column visible (not just the
    mode's *default*-visible subset) -- lets a test assert on a
    non-default-visible column's aggregated value directly."""
    offered = offered_columns(run_mode)
    return msgspec.structs.replace(
        default_view_state(run_mode),
        layout=SummaryColumnLayout(visible=frozenset(offered), order=offered),
    )


# ---------------------------------------------------------------------------
# STORY-062-AC-1 / EC-RES-2
# ---------------------------------------------------------------------------


def test_same_model_two_providers_stay_distinct() -> None:
    """Proves: STORY-062-AC-1

    Covers EC-RES-2: two results sharing one ``model_name`` under two
    different ``provider_id`` values aggregate into two distinct rows, each
    labelled with its own snapshot ``provider_name`` -- never merged.
    """
    # Arrange
    task = make_task()
    results = (
        make_result(
            result_id=1,
            provider_id="provider-a",
            provider_name="Provider A",
            model_name="llama3.2:3b",
        ),
        make_result(
            result_id=2,
            provider_id="provider-b",
            provider_name="Provider B",
            model_name="llama3.2:3b",
        ),
    )
    view_state = default_view_state(RunMode.GRADED)
    # Act
    vm = aggregate_summary(
        results=results,
        tasks_by_id={task.task_id: task},
        run_mode=RunMode.GRADED,
        view_state=view_state,
        score_display_format=None,
    )
    # Assert
    expected_labels = {"Provider A / llama3.2:3b", "Provider B / llama3.2:3b"}
    label_index = _column_index(vm.columns, SummaryColumnKey.PROVIDER_MODEL)
    labels = {row[label_index] for row in vm.rows}
    assert len(vm.rows) == len(expected_labels)
    assert labels == expected_labels


# ---------------------------------------------------------------------------
# STORY-062-AC-3 / EC-RES-1
# ---------------------------------------------------------------------------


def test_empty_aggregate_renders_em_dash() -> None:
    """Proves: STORY-062-AC-3

    Covers EC-RES-1: a column group with zero contributing completed rows
    renders the em dash, never ``0`` and never a blank string.
    """
    # Arrange
    task = make_task()
    results = (make_result(status=ResultStatus.PENDING),)
    view_state = default_view_state(RunMode.GRADED)
    # Act
    vm = aggregate_summary(
        results=results,
        tasks_by_id={task.task_id: task},
        run_mode=RunMode.GRADED,
        view_state=view_state,
        score_display_format=None,
    )
    # Assert
    avg_time_index = _column_index(vm.columns, SummaryColumnKey.AVG_TIME_S)
    assert vm.rows[0][avg_time_index] == _EM_DASH


# ---------------------------------------------------------------------------
# STORY-062-AC-4
# ---------------------------------------------------------------------------


def test_row_scoped_filter_reaggregates() -> None:
    """Proves: STORY-062-AC-4

    Given the Difficulty chip narrows to exclude a difficulty, when the tab
    re-aggregates, every visible column recomputes from the surviving
    contributing rows only.
    """
    # Arrange -- 5 "easy" + 5 "hard" rows so the surviving group never dips
    # below `eval.min_sample_size` and picks up the unrelated low-sample marker.
    easy_task = make_task(task_id="task-easy", difficulty=Difficulty.EASY)
    hard_task = make_task(task_id="task-hard", difficulty=Difficulty.HARD)
    tasks_by_id = {easy_task.task_id: easy_task, hard_task.task_id: hard_task}
    results = tuple(
        make_result(result_id=index, task_id="task-easy", total_time_ms=1000)
        for index in range(1, 6)
    ) + tuple(
        make_result(result_id=index, task_id="task-hard", total_time_ms=3000)
        for index in range(6, 11)
    )
    all_state = default_view_state(RunMode.GRADED)
    narrowed_state = msgspec.structs.replace(
        all_state,
        filters=msgspec.structs.replace(all_state.filters, difficulties=frozenset({"easy"})),
    )
    # Act
    vm_all = aggregate_summary(
        results=results,
        tasks_by_id=tasks_by_id,
        run_mode=RunMode.GRADED,
        view_state=all_state,
        score_display_format=None,
    )
    vm_narrowed = aggregate_summary(
        results=results,
        tasks_by_id=tasks_by_id,
        run_mode=RunMode.GRADED,
        view_state=narrowed_state,
        score_display_format=None,
    )
    # Assert
    avg_time_index = _column_index(vm_all.columns, SummaryColumnKey.AVG_TIME_S)
    assert vm_all.rows[0][avg_time_index] == "2.00"
    assert vm_narrowed.rows[0][avg_time_index] == "1.00"


def test_models_filter_removes_whole_rows_rather_than_reaggregating() -> None:
    """Proves: STORY-062-AC-4

    The Models chip is row-removing, not row-scoped: narrowing it drops an
    entire group's row rather than recomputing a shared row from a subset.
    """
    # Arrange
    task = make_task()
    results = (
        make_result(result_id=1, provider_id="provider-a", provider_name="A", model_name="m1"),
        make_result(result_id=2, provider_id="provider-b", provider_name="B", model_name="m2"),
    )
    base_state = default_view_state(RunMode.GRADED)
    narrowed_state = msgspec.structs.replace(
        base_state,
        filters=msgspec.structs.replace(base_state.filters, models=frozenset({"provider-a\x1fm1"})),
    )
    # Act
    vm = aggregate_summary(
        results=results,
        tasks_by_id={task.task_id: task},
        run_mode=RunMode.GRADED,
        view_state=narrowed_state,
        score_display_format=None,
    )
    # Assert
    assert len(vm.rows) == 1


# ---------------------------------------------------------------------------
# offered_columns / default_view_state
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    ("run_mode", "expect_grading_columns"),
    [
        (RunMode.SYNTHETIC, False),
        (RunMode.TASKS, False),
        (RunMode.GRADED, True),
    ],
    ids=["synthetic", "tasks", "graded"],
)
def test_offered_columns_matches_mode_policy(
    *, run_mode: RunMode, expect_grading_columns: bool
) -> None:
    """Proves: STORY-062

    ``offered_columns`` offers the grading-only column group solely for
    ``GRADED`` and always offers the common Provider/Model/Tasks/timing/
    throughput group.
    """
    # Act
    offered = set(offered_columns(run_mode))
    # Assert
    assert _GRADING_COLUMNS.issubset(offered) is expect_grading_columns
    assert {
        SummaryColumnKey.PROVIDER_MODEL,
        SummaryColumnKey.TASKS,
        SummaryColumnKey.AVG_TPS,
    } <= offered


def test_default_view_state_visible_columns_subset_of_offered() -> None:
    """Proves: STORY-062

    ``default_view_state`` produces a layout whose visible set is a subset of
    the mode-offered columns and whose order is exactly the offered columns.
    """
    # Act
    state = default_view_state(RunMode.TASKS)
    # Assert
    assert state.layout.order == offered_columns(RunMode.TASKS)
    assert state.layout.visible <= set(state.layout.order)
    assert SummaryColumnKey.PASS_RATE not in state.layout.visible


def test_default_view_state_sort_defaults_avg_tps_descending() -> None:
    """Proves: STORY-062

    The built-in default sort is Avg-TPS-descending.
    """
    # Act
    state = default_view_state(RunMode.GRADED)
    # Assert
    assert state.sort == SummarySort(column=SummaryColumnKey.AVG_TPS, descending=True)


# ---------------------------------------------------------------------------
# encode_view_state / decode_view_state
# ---------------------------------------------------------------------------


def test_encode_decode_view_state_round_trips() -> None:
    """Proves: STORY-062

    A view state encoded and then decoded produces an equal value.
    """
    # Arrange
    state = default_view_state(RunMode.GRADED)
    narrowed = msgspec.structs.replace(
        state,
        column_filters=(
            ColumnFilterEntry(
                column=SummaryColumnKey.FAILED, selected_values=frozenset({"errored"})
            ),
        ),
    )
    # Act
    round_tripped = decode_view_state(encode_view_state(narrowed))
    # Assert
    assert round_tripped == narrowed


# ---------------------------------------------------------------------------
# chip_domains
# ---------------------------------------------------------------------------


def test_chip_domains_computed_from_full_unfiltered_results() -> None:
    """Proves: STORY-062

    ``chip_domains`` reflects every result passed to it, independent of any
    filter -- the domain a filter chip offers is always the run's full set.
    """
    # Arrange
    task_a = make_task(task_id="task-a", category="geography")
    task_b = make_task(task_id="task-b", category="history")
    results = (
        make_result(
            result_id=1,
            task_id="task-a",
            provider_id="provider-a",
            provider_name="Provider A",
            model_name="m1",
        ),
        make_result(
            result_id=2,
            task_id="task-b",
            provider_id="provider-b",
            provider_name="Provider B",
            model_name="m2",
        ),
    )
    tasks_by_id = {task_a.task_id: task_a, task_b.task_id: task_b}
    # Act
    domains = chip_domains(results=results, tasks_by_id=tasks_by_id)
    # Assert
    assert dict(domains.models) == {
        "provider-a\x1fm1": "Provider A / m1",
        "provider-b\x1fm2": "Provider B / m2",
    }
    assert set(domains.categories) == {"geography", "history"}
    assert domains.verdicts == ("pass", "fail", "ungraded")
    assert domains.difficulties == ("easy", "medium", "hard")


# ---------------------------------------------------------------------------
# column_filter_domain
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    ("column", "expect_domain"),
    [
        (SummaryColumnKey.FAILED, True),
        (SummaryColumnKey.INCOMPLETE, True),
        (SummaryColumnKey.LAYER_MIX, True),
        (SummaryColumnKey.AVG_TPS, False),
    ],
    ids=["failed", "incomplete", "layer_mix", "avg_tps_not_filterable"],
)
def test_column_filter_domain_only_for_filterable_columns(
    *, column: SummaryColumnKey, expect_domain: bool
) -> None:
    """Proves: STORY-062

    Only ``FAILED``/``INCOMPLETE``/``LAYER_MIX`` carry a per-column filter
    domain; every other column returns ``None`` (no per-column filter menu).
    """
    # Act
    domain = column_filter_domain(column)
    # Assert
    assert (domain is not None) is expect_domain


# ---------------------------------------------------------------------------
# Sorting: numeric + em-dash-sorts-lowest
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    ("descending", "expected_order"),
    [
        (True, ("fast", "slow", "none")),
        (False, ("none", "slow", "fast")),
    ],
    ids=["descending_em_dash_last", "ascending_em_dash_first"],
)
def test_sort_by_avg_tps_places_em_dash_lowest(
    *, descending: bool, expected_order: tuple[str, ...]
) -> None:
    """Proves: STORY-062

    Sorting by a numeric column always treats the em-dash (no contributing
    rows) as the lowest value, regardless of sort direction.
    """
    # Arrange
    task = make_task()
    results = (
        make_result(
            result_id=1,
            provider_id="p-fast",
            provider_name="fast",
            model_name="m",
            tokens_per_second=20.0,
        ),
        make_result(
            result_id=2,
            provider_id="p-slow",
            provider_name="slow",
            model_name="m",
            tokens_per_second=5.0,
        ),
        make_result(
            result_id=3,
            provider_id="p-none",
            provider_name="none",
            model_name="m",
            status=ResultStatus.PENDING,
        ),
    )
    view_state = msgspec.structs.replace(
        default_view_state(RunMode.GRADED),
        sort=SummarySort(column=SummaryColumnKey.AVG_TPS, descending=descending),
    )
    # Act
    vm = aggregate_summary(
        results=results,
        tasks_by_id={task.task_id: task},
        run_mode=RunMode.GRADED,
        view_state=view_state,
        score_display_format=None,
    )
    # Assert
    label_index = _column_index(vm.columns, SummaryColumnKey.PROVIDER_MODEL)
    provider_order = tuple(row[label_index].split(" / ")[0] for row in vm.rows)
    assert provider_order == expected_order


def test_sort_column_none_leaves_groups_unsorted_by_insertion() -> None:
    """Proves: STORY-062

    A cleared sort (``column=None``) leaves the aggregated groups in their
    original dict-insertion order -- no numeric comparison is applied.
    """
    # Arrange
    task = make_task()
    results = (
        make_result(
            result_id=1, provider_id="p-a", provider_name="A", model_name="m", tokens_per_second=1.0
        ),
        make_result(
            result_id=2,
            provider_id="p-b",
            provider_name="B",
            model_name="m",
            tokens_per_second=99.0,
        ),
    )
    view_state = msgspec.structs.replace(
        default_view_state(RunMode.GRADED), sort=SummarySort(column=None, descending=True)
    )
    # Act
    vm = aggregate_summary(
        results=results,
        tasks_by_id={task.task_id: task},
        run_mode=RunMode.GRADED,
        view_state=view_state,
        score_display_format=None,
    )
    # Assert
    label_index = _column_index(vm.columns, SummaryColumnKey.PROVIDER_MODEL)
    assert vm.rows[0][label_index] == "A / m"
    assert vm.rows[1][label_index] == "B / m"


# ---------------------------------------------------------------------------
# Empty-state message variants
# ---------------------------------------------------------------------------


def test_empty_state_message_no_results_at_all() -> None:
    """Proves: STORY-062

    A run with zero results shows the "no results yet" message.
    """
    # Act
    vm = aggregate_summary(
        results=(),
        tasks_by_id={},
        run_mode=RunMode.GRADED,
        view_state=default_view_state(RunMode.GRADED),
        score_display_format=None,
    )
    # Assert
    assert vm.empty_state_message == "This run has no results yet."
    assert vm.rows == ()


def test_empty_state_message_results_but_none_completed() -> None:
    """Proves: STORY-062

    A run with results but none ``COMPLETED`` yet shows the "aggregates will
    fill in" message, distinct from the "no results at all" message.
    """
    # Arrange
    task = make_task()
    results = (make_result(status=ResultStatus.RUNNING_INFERENCE),)
    # Act
    vm = aggregate_summary(
        results=results,
        tasks_by_id={task.task_id: task},
        run_mode=RunMode.GRADED,
        view_state=default_view_state(RunMode.GRADED),
        score_display_format=None,
    )
    # Assert
    assert (
        vm.empty_state_message
        == "No completed results yet — aggregates will fill in as tasks finish."
    )


def test_empty_state_message_filtered_to_zero_groups() -> None:
    """Proves: STORY-062

    A run with completed results, all excluded by the active filters, shows
    the "no rows match" message rather than either no-results message.
    """
    # Arrange
    task = make_task(difficulty=Difficulty.HARD)
    results = (make_result(status=ResultStatus.COMPLETED),)
    view_state = msgspec.structs.replace(
        default_view_state(RunMode.GRADED),
        filters=msgspec.structs.replace(
            default_view_state(RunMode.GRADED).filters, difficulties=frozenset({"easy"})
        ),
    )
    # Act
    vm = aggregate_summary(
        results=results,
        tasks_by_id={task.task_id: task},
        run_mode=RunMode.GRADED,
        view_state=view_state,
        score_display_format=None,
    )
    # Assert
    assert vm.empty_state_message == "No rows match the current filters."


def test_empty_state_message_none_when_rows_present() -> None:
    """Proves: STORY-062

    A run with at least one surviving, completed row has no empty-state
    message.
    """
    # Arrange
    task = make_task()
    results = (make_result(status=ResultStatus.COMPLETED),)
    # Act
    vm = aggregate_summary(
        results=results,
        tasks_by_id={task.task_id: task},
        run_mode=RunMode.GRADED,
        view_state=default_view_state(RunMode.GRADED),
        score_display_format=None,
    )
    # Assert
    assert vm.empty_state_message is None


# ---------------------------------------------------------------------------
# Per-column aggregation correctness
# ---------------------------------------------------------------------------


def test_completed_failed_incomplete_counts() -> None:
    """Proves: STORY-062

    ``Completed``/``Failed``/``Incomplete`` each count their own disjoint
    status family; ``Tasks`` counts every contributing row.
    """
    # Arrange
    task = make_task()
    results = (
        make_result(result_id=1, status=ResultStatus.COMPLETED),
        make_result(result_id=2, status=ResultStatus.COMPLETED),
        make_result(result_id=3, status=ResultStatus.FAILED_INFERENCE),
        make_result(result_id=4, status=ResultStatus.PENDING),
    )
    # Act
    vm = aggregate_summary(
        results=results,
        tasks_by_id={task.task_id: task},
        run_mode=RunMode.GRADED,
        view_state=default_view_state(RunMode.GRADED),
        score_display_format=None,
    )
    # Assert
    row = vm.rows[0]
    assert row[_column_index(vm.columns, SummaryColumnKey.TASKS)] == "4"
    assert row[_column_index(vm.columns, SummaryColumnKey.FAILED)] == "1"


def test_avg_tokens_rounds_to_nearest_integer() -> None:
    """Proves: STORY-062

    ``Avg Tokens`` is the mean of ``completion_tokens`` across completed
    rows, rounded to the nearest whole token.
    """
    # Arrange -- 5 rows (>= eval.min_sample_size) so the low-sample marker
    # never gets appended to this unrelated column's value.
    task = make_task()
    results = tuple(make_result(result_id=index, completion_tokens=50) for index in range(1, 6))
    # Act
    vm = aggregate_summary(
        results=results,
        tasks_by_id={task.task_id: task},
        run_mode=RunMode.GRADED,
        view_state=default_view_state(RunMode.GRADED),
        score_display_format=None,
    )
    # Assert
    assert vm.rows[0][_column_index(vm.columns, SummaryColumnKey.AVG_TOKENS)] == "50"


def test_judge_pass_fail_counts() -> None:
    """Proves: STORY-062

    ``Judge PASS``/``Judge FAIL`` count completed rows by their strictly
    binary ``judge_verdict``.
    """
    # Arrange
    task = make_task()
    results = (
        make_result(result_id=1, judge_verdict=Verdict.PASS),
        make_result(result_id=2, judge_verdict=Verdict.FAIL),
        make_result(result_id=3, judge_verdict=Verdict.PASS),
    )
    # Act -- JUDGE_PASS/JUDGE_FAIL are not default-visible; force them visible.
    vm = aggregate_summary(
        results=results,
        tasks_by_id={task.task_id: task},
        run_mode=RunMode.GRADED,
        view_state=_all_columns_visible_state(RunMode.GRADED),
        score_display_format=None,
    )
    # Assert
    row = vm.rows[0]
    assert row[_column_index(vm.columns, SummaryColumnKey.JUDGE_PASS)] == "2"
    assert row[_column_index(vm.columns, SummaryColumnKey.JUDGE_FAIL)] == "1"


def test_timeout_failures_family_counted_independently() -> None:
    """Proves: STORY-062

    ``Timeout failures``/``Judge-timeout failures``/``Provider failures``
    each count their own single, distinct ``ResultStatus`` leaf.
    """
    # Arrange
    task = make_task()
    results = (
        make_result(result_id=1, status=ResultStatus.FAILED_TIMEOUT),
        make_result(result_id=2, status=ResultStatus.FAILED_JUDGE_TIMEOUT),
        make_result(result_id=3, status=ResultStatus.FAILED_PROVIDER),
    )
    view_state = _all_columns_visible_state(RunMode.GRADED)
    # Act
    vm = aggregate_summary(
        results=results,
        tasks_by_id={task.task_id: task},
        run_mode=RunMode.GRADED,
        view_state=view_state,
        score_display_format=None,
    )
    # Assert
    row = vm.rows[0]
    assert row[_column_index(vm.columns, SummaryColumnKey.TIMEOUT_FAILURES)] == "1"
    assert row[_column_index(vm.columns, SummaryColumnKey.JUDGE_TIMEOUT_FAILURES)] == "1"
    assert row[_column_index(vm.columns, SummaryColumnKey.PROVIDER_FAILURES)] == "1"


def test_layer_mix_cell_formats_per_layer_counts() -> None:
    """Proves: STORY-062

    ``Layer mix`` renders one ``K``/``C``/``J``/``S`` count per resolution
    layer among completed rows.
    """
    # Arrange
    task = make_task()
    results = (
        make_result(result_id=1, resolution_layer=ResolutionLayer.KEYWORD),
        make_result(result_id=2, resolution_layer=ResolutionLayer.COSINE),
        make_result(result_id=3, resolution_layer=ResolutionLayer.JUDGE),
        make_result(result_id=4, resolution_layer=ResolutionLayer.SKIP),
        make_result(result_id=5, resolution_layer=ResolutionLayer.SKIP),
    )
    # Act -- LAYER_MIX is not default-visible; force it visible.
    vm = aggregate_summary(
        results=results,
        tasks_by_id={task.task_id: task},
        run_mode=RunMode.GRADED,
        view_state=_all_columns_visible_state(RunMode.GRADED),
        score_display_format=None,
    )
    # Assert
    assert vm.rows[0][_column_index(vm.columns, SummaryColumnKey.LAYER_MIX)] == "K1 C1 J1 S2"


def test_avg_attempts_means_over_every_contributing_row() -> None:
    """Proves: STORY-062

    ``Avg attempts`` is the mean attempt-list length across every
    contributing row of the group, not just completed rows.
    """
    # Arrange
    task = make_task()
    results = (
        make_result(result_id=1, attempts_count=1),
        make_result(result_id=2, attempts_count=3),
    )
    # Act -- AVG_ATTEMPTS is not default-visible; force it visible.
    vm = aggregate_summary(
        results=results,
        tasks_by_id={task.task_id: task},
        run_mode=RunMode.GRADED,
        view_state=_all_columns_visible_state(RunMode.GRADED),
        score_display_format=None,
    )
    # Assert
    assert vm.rows[0][_column_index(vm.columns, SummaryColumnKey.AVG_ATTEMPTS)] == "2.0"


# ---------------------------------------------------------------------------
# Cosine-Score partial-coverage marker (⚠)
# ---------------------------------------------------------------------------


def test_cosine_score_flags_partial_coverage_group_when_a_peer_meets_threshold() -> None:
    """Proves: STORY-062

    A group whose cosine-eligible completed rows fall below the
    ``eval.min_cosine_coverage`` threshold is flagged with ``⚠`` only when at
    least one other group in the run meets that threshold.
    """
    # Arrange
    task = make_task(golden_answer="Paris", cosine_enabled=True)
    tasks_by_id = {task.task_id: task}
    full_coverage_results = tuple(
        make_result(
            result_id=index, provider_id="p-full", provider_name="Full", cosine_similarity=0.9
        )
        for index in range(1, 6)
    )
    partial_coverage_results = (
        make_result(
            result_id=10, provider_id="p-partial", provider_name="Partial", cosine_similarity=0.9
        ),
        make_result(
            result_id=11, provider_id="p-partial", provider_name="Partial", cosine_similarity=None
        ),
        make_result(
            result_id=12, provider_id="p-partial", provider_name="Partial", cosine_similarity=None
        ),
        make_result(
            result_id=13, provider_id="p-partial", provider_name="Partial", cosine_similarity=None
        ),
        make_result(
            result_id=14, provider_id="p-partial", provider_name="Partial", cosine_similarity=None
        ),
    )
    results = full_coverage_results + partial_coverage_results
    # Act
    vm = aggregate_summary(
        results=results,
        tasks_by_id=tasks_by_id,
        run_mode=RunMode.GRADED,
        view_state=default_view_state(RunMode.GRADED),
        score_display_format=None,
    )
    # Assert
    label_index = _column_index(vm.columns, SummaryColumnKey.PROVIDER_MODEL)
    score_index = _column_index(vm.columns, SummaryColumnKey.COSINE_SCORE)
    rows_by_provider = {row[label_index].split(" / ")[0]: row for row in vm.rows}
    assert rows_by_provider["Partial"][score_index].endswith("⚠")
    assert not rows_by_provider["Full"][score_index].endswith("⚠")


def test_cosine_score_unflagged_when_no_group_meets_coverage_threshold() -> None:
    """Proves: STORY-062

    When no group in the run meets the coverage threshold, no group is
    flagged partial -- the marker is relative to the run's best coverage.
    """
    # Arrange
    task = make_task(golden_answer="Paris", cosine_enabled=True)
    results = (
        make_result(result_id=1, cosine_similarity=0.9),
        make_result(result_id=2, cosine_similarity=None),
    )
    # Act
    vm = aggregate_summary(
        results=results,
        tasks_by_id={task.task_id: task},
        run_mode=RunMode.GRADED,
        view_state=default_view_state(RunMode.GRADED),
        score_display_format=None,
    )
    # Assert
    score_index = _column_index(vm.columns, SummaryColumnKey.COSINE_SCORE)
    assert not vm.rows[0][score_index].endswith("⚠")


# ---------------------------------------------------------------------------
# Low-sample marker (†)
# ---------------------------------------------------------------------------


def test_low_sample_marker_appended_when_below_minimum_sample_size() -> None:
    """Proves: STORY-062

    A group with fewer than ``eval.min_sample_size`` (default 5) completed
    rows has the low-sample marker appended to its low-sample-eligible
    columns, but never to a column already showing the em dash.
    """
    # Arrange
    task = make_task()
    results = (
        make_result(result_id=1, verdict=Verdict.PASS),
        make_result(result_id=2, verdict=Verdict.PASS),
    )
    # Act -- LAYER_MIX is not default-visible; force it visible too.
    vm = aggregate_summary(
        results=results,
        tasks_by_id={task.task_id: task},
        run_mode=RunMode.GRADED,
        view_state=_all_columns_visible_state(RunMode.GRADED),
        score_display_format=None,
    )
    # Assert
    pass_rate_index = _column_index(vm.columns, SummaryColumnKey.PASS_RATE)
    layer_mix_index = _column_index(vm.columns, SummaryColumnKey.LAYER_MIX)
    assert vm.rows[0][pass_rate_index] == "1.00 †"
    assert vm.rows[0][layer_mix_index] == _EM_DASH  # never marked when already em dash


# ---------------------------------------------------------------------------
# Avg TPS estimated (≈) / thinking-block (⧉) markers
# ---------------------------------------------------------------------------


def test_avg_tps_estimated_and_thinking_markers_prefix_the_value() -> None:
    """Proves: STORY-062

    ``Avg TPS`` prefixes ``≈`` when any contributing row's tokens were
    estimated and ``⧉`` when any contributing row had a thinking block,
    in that order.
    """
    # Arrange
    task = make_task()
    results = tuple(
        make_result(result_id=index, tokens_estimated=True, has_thinking_block=True)
        for index in range(1, 6)
    )
    # Act
    vm = aggregate_summary(
        results=results,
        tasks_by_id={task.task_id: task},
        run_mode=RunMode.GRADED,
        view_state=default_view_state(RunMode.GRADED),
        score_display_format=None,
    )
    # Assert
    tps_index = _column_index(vm.columns, SummaryColumnKey.AVG_TPS)
    assert vm.rows[0][tps_index].startswith("≈⧉")


# ---------------------------------------------------------------------------
# score_display_format
# ---------------------------------------------------------------------------


def test_score_display_format_percent_renders_percentage() -> None:
    """Proves: STORY-062

    ``ui.score_display_format == "percent"`` renders the Pass Rate as a
    percentage rather than a 0.00-1.00 decimal.
    """
    # Arrange
    task = make_task()
    results = (
        make_result(result_id=1, verdict=Verdict.PASS),
        make_result(result_id=2, verdict=Verdict.PASS),
        make_result(result_id=3, verdict=Verdict.PASS),
        make_result(result_id=4, verdict=Verdict.FAIL),
    )
    # Act
    vm = aggregate_summary(
        results=results,
        tasks_by_id={task.task_id: task},
        run_mode=RunMode.GRADED,
        view_state=default_view_state(RunMode.GRADED),
        score_display_format="percent",
    )
    # Assert
    pass_rate_index = _column_index(vm.columns, SummaryColumnKey.PASS_RATE)
    assert vm.rows[0][pass_rate_index].startswith("75%")


def test_score_display_format_letter_renders_identically_to_decimal() -> None:
    """Proves: STORY-062

    The un-spec'd ``letter`` format renders identically to ``decimal`` (a
    documented, reported simplification -- no letter-grade boundary table
    exists anywhere in the vendored spec).
    """
    # Arrange
    task = make_task()
    results = (
        make_result(result_id=1, verdict=Verdict.PASS),
        make_result(result_id=2, verdict=Verdict.PASS),
        make_result(result_id=3, verdict=Verdict.PASS),
        make_result(result_id=4, verdict=Verdict.FAIL),
    )
    pass_rate_index_state = default_view_state(RunMode.GRADED)
    # Act
    vm_letter = aggregate_summary(
        results=results,
        tasks_by_id={task.task_id: task},
        run_mode=RunMode.GRADED,
        view_state=pass_rate_index_state,
        score_display_format="letter",
    )
    vm_decimal = aggregate_summary(
        results=results,
        tasks_by_id={task.task_id: task},
        run_mode=RunMode.GRADED,
        view_state=pass_rate_index_state,
        score_display_format="decimal",
    )
    # Assert
    pass_rate_index = _column_index(vm_letter.columns, SummaryColumnKey.PASS_RATE)
    assert vm_letter.rows[0][pass_rate_index] == vm_decimal.rows[0][pass_rate_index]
