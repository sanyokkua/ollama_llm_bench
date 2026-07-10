"""Integration tests for ``backend/persistence/results/``.

Exercises the real ``ResultsStore`` public surface — ``create_results_store`` and the
``SqliteResultsStore`` it returns — against a real ``tmp_path`` SQLite database file,
never ``:memory:``, per ``testing.md``'s integration-tier rule.

Source of truth: STORY-011 acceptance criteria AC-1, AC-2, AC-5, AC-6; EC-PERSIST-4.
"""

from pathlib import Path
import sqlite3

import pytest

from ollama_llm_bench.backend.domain import (
    AttemptOutcome,
    BenchmarkResult,
    BenchmarkResultAttempt,
    BenchmarkResultTerm,
    BenchmarkRun,
    BenchmarkRunModelEntry,
    BenchmarkTask,
    ModelRole,
    ResultPatch,
    ResultStatus,
    ResultTermKind,
    RunId,
    RunMode,
    RunStatus,
    TaskOrigin,
    Verdict,
)
from ollama_llm_bench.backend.infra.protocols import Clock
from ollama_llm_bench.backend.persistence.app_settings import (
    ensure_schema,
    open_read_connection,
    open_write_connection,
)
from ollama_llm_bench.backend.persistence.results import ResultsStore, create_results_store
from ollama_llm_bench.backend.persistence.runs import create_runs_store
from ollama_llm_bench.backend.persistence.tasks import create_tasks_store

_TEST_PROVIDER_ID = "11111111-1111-4111-8111-111111111111"
_EXPECTED_RESULT_COUNT = 2
_EXPECTED_TERM_COUNT = 2
_PRESERVED_TOTAL_TIME_MS = 1200


@pytest.fixture
def results_store(db_path: Path, clock: Clock) -> tuple[ResultsStore, sqlite3.Connection, RunId]:
    """A ``ResultsStore`` wired over a fresh ``tmp_path`` database, plus the write
    connection and a real parent run id with one parent task created via
    ``RunsStore``/``TasksStore``.
    """
    write_conn, lock = open_write_connection(db_path)
    ensure_schema(write_conn, lock, clock=clock)
    read_conn_factory = lambda: open_read_connection(db_path)  # noqa: E731  # local test helper
    runs_store = create_runs_store(write_conn, lock, read_conn_factory)
    run_id = runs_store.create_run(_make_run())
    tasks_store = create_tasks_store(write_conn, lock, read_conn_factory)
    tasks_store.create_tasks(run_id, (_make_task("task-1"), _make_task("task-2")))
    store = create_results_store(write_conn, lock, read_conn_factory)
    return store, write_conn, run_id


def _make_run() -> BenchmarkRun:
    """Build a placeholder ``BenchmarkRun`` sufficient to create a parent run row."""
    return BenchmarkRun(
        run_id=-1,
        run_name="parent-run",
        timestamp="2026-01-01T00:00:00+00:00",
        run_mode=RunMode.TASKS,
        status=RunStatus.INCOMPLETE,
        total_tasks=2,
        completed_tasks=0,
        total_elapsed_ms=0,
        schema_version=1,
        created_at="2026-01-01T00:00:00+00:00",
        models=(
            BenchmarkRunModelEntry(
                role=ModelRole.TEST, provider_id=_TEST_PROVIDER_ID, model_name="llama3"
            ),
        ),
    )


def _make_task(task_id: str) -> BenchmarkTask:
    """Build a minimal valid parent ``BenchmarkTask``."""
    return BenchmarkTask(
        task_id=task_id,
        task_origin=TaskOrigin.FILE,
        question="What is 2+2?",
    )


def _make_result(
    *,
    run_id: RunId,
    task_id: str = "task-1",
    status: ResultStatus = ResultStatus.PENDING,
    sanitized_response: str | None = None,
    children: tuple[tuple[BenchmarkResultTerm, ...], tuple[BenchmarkResultAttempt, ...]] = (
        (),
        (),
    ),
) -> BenchmarkResult:
    """Build a minimal valid ``BenchmarkResult`` for ``create_results`` calls.

    ``result_id`` is a caller-supplied placeholder ``create_results`` ignores.
    ``children`` bundles the optional term/attempt child-row tuples.
    """
    terms, attempts = children
    return BenchmarkResult(
        result_id=-1,
        run_id=run_id,
        task_id=task_id,
        provider_id=_TEST_PROVIDER_ID,
        provider_name="Local Ollama",
        model_name="llama3",
        status=status,
        sanitized_response=sanitized_response,
        created_at="2026-01-01T00:00:00+00:00",
        terms=terms,
        attempts=attempts,
    )


def test_create_and_list_results_with_child_rows(
    results_store: tuple[ResultsStore, sqlite3.Connection, RunId],
) -> None:
    """Proves: STORY-011-AC-1

    Given a tuple of initial BenchmarkResult rows for a run, when
    create_results is called, then all rows are inserted in one transaction,
    and list_results returns every result of the run, each assembled with
    its benchmark_result_terms and benchmark_result_attempts child rows.
    """
    store, _write_conn, run_id = results_store
    result_with_children = _make_result(
        run_id=run_id,
        task_id="task-1",
        children=(
            (
                BenchmarkResultTerm(
                    term_kind=ResultTermKind.EXACT_MISSING, term_order=0, term_text="four"
                ),
                BenchmarkResultTerm(
                    term_kind=ResultTermKind.SEMANTIC, term_order=0, term_text="arithmetic"
                ),
            ),
            (
                BenchmarkResultAttempt(
                    attempt_index=1, timeout_ms=30000, outcome=AttemptOutcome.SUCCESS
                ),
            ),
        ),
    )
    result_without_children = _make_result(run_id=run_id, task_id="task-2")

    # Act
    store.create_results((result_with_children, result_without_children))
    listed = store.list_results(run_id)

    # Assert — both results exist.
    assert len(listed) == _EXPECTED_RESULT_COUNT
    listed_by_task = {result.task_id: result for result in listed}

    # Assert — the result with children is assembled with its term/attempt rows.
    assembled_with_children = listed_by_task["task-1"]
    assert len(assembled_with_children.terms) == _EXPECTED_TERM_COUNT
    assert assembled_with_children.terms[0].term_text == "four"
    assert len(assembled_with_children.attempts) == 1
    assert assembled_with_children.attempts[0].outcome == AttemptOutcome.SUCCESS

    # Assert — the result without children has no term/attempt rows.
    assembled_without_children = listed_by_task["task-2"]
    assert assembled_without_children.terms == ()
    assert assembled_without_children.attempts == ()


def test_update_result_replaces_term_and_attempt_children_wholesale(
    results_store: tuple[ResultsStore, sqlite3.Connection, RunId],
) -> None:
    """Proves: STORY-011-AC-2

    Given a persisted result, when update_result applies a ResultPatch
    carrying terms and attempts, then that result's existing term and
    attempt child rows are replaced wholesale in one transaction and its
    identity columns are unchanged.
    """
    store, _write_conn, run_id = results_store
    original = _make_result(
        run_id=run_id,
        task_id="task-1",
        children=(
            (
                BenchmarkResultTerm(
                    term_kind=ResultTermKind.EXACT_MISSING, term_order=0, term_text="old"
                ),
            ),
            (
                BenchmarkResultAttempt(
                    attempt_index=1, timeout_ms=30000, outcome=AttemptOutcome.TIMEOUT
                ),
            ),
        ),
    )
    store.create_results((original,))
    result_id = store.list_results(run_id)[0].result_id

    # Act
    store.update_result(
        result_id,
        ResultPatch(
            status=ResultStatus.COMPLETED,
            verdict=Verdict.PASS,
            terms=(
                BenchmarkResultTerm(
                    term_kind=ResultTermKind.SEMANTIC, term_order=0, term_text="new-a"
                ),
                BenchmarkResultTerm(
                    term_kind=ResultTermKind.SEMANTIC, term_order=1, term_text="new-b"
                ),
            ),
            attempts=(
                BenchmarkResultAttempt(
                    attempt_index=1, timeout_ms=30000, outcome=AttemptOutcome.SUCCESS
                ),
            ),
        ),
    )
    updated = store.list_results(run_id)[0]

    # Assert — the child rows were replaced wholesale, not appended to.
    assert [term.term_text for term in updated.terms] == ["new-a", "new-b"]
    assert len(updated.attempts) == 1
    assert updated.attempts[0].outcome == AttemptOutcome.SUCCESS

    # Assert — the patched header fields applied.
    assert updated.status == ResultStatus.COMPLETED
    assert updated.verdict == Verdict.PASS

    # Assert — identity columns are unchanged.
    assert updated.result_id == result_id
    assert updated.run_id == run_id
    assert updated.task_id == "task-1"
    assert updated.provider_id == _TEST_PROVIDER_ID
    assert updated.model_name == "llama3"


def test_list_resumable_returns_pending_and_retryable_failures(
    results_store: tuple[ResultsStore, sqlite3.Connection, RunId],
) -> None:
    """Proves: STORY-011-AC-5

    Given a run's persisted results, list_resumable_results returns exactly
    the PENDING rows and the rows in a retryable terminal-failure status,
    and excludes every COMPLETED row and every mid-flight row. Covers
    EC-PERSIST-4: a retryable-failure row remains available for the user to
    resume/retry rather than being silently dropped.
    """
    store, write_conn, run_id = results_store
    store.create_results(
        (
            _make_result(run_id=run_id, task_id="task-1", status=ResultStatus.PENDING),
            _make_result(run_id=run_id, task_id="task-2", status=ResultStatus.COMPLETED),
        )
    )
    all_results = store.list_results(run_id)
    pending_id = next(r.result_id for r in all_results if r.task_id == "task-1")
    completed_id = next(r.result_id for r in all_results if r.task_id == "task-2")

    # Arrange — set additional rows directly via raw SQL to cover every
    # non-pending status without needing a create_results call per status.
    write_conn.execute(
        "UPDATE benchmark_results SET status = 'failed_inference' WHERE result_id = ?",
        (completed_id,),
    )
    write_conn.commit()

    # Act
    resumable = store.list_resumable_results(run_id)

    # Assert — the pending row and the now-retryable-failure row are both present;
    # no completed/mid-flight row survives (there is none of the latter here).
    resumable_ids = {result.result_id for result in resumable}
    assert resumable_ids == {pending_id, completed_id}


def test_reset_full_vs_stage_preserving_retry(
    results_store: tuple[ResultsStore, sqlite3.Connection, RunId],
) -> None:
    """Proves: STORY-011-AC-6

    Given rows in retryable statuses, reset_results resets each named row
    fully to PENDING (clearing verdicts, metrics, responses, and child
    rows), while reset_results_for_retry resets a FAILED_JUDGE_TIMEOUT row
    (or an ERRORED row with a non-null sanitized_response) to
    AWAITING_JUDGE_CHECK preserving the inference response, timing,
    keyword, and cosine outcomes, and resets every other retryable status
    fully to PENDING.
    """
    store, _write_conn, run_id = results_store

    # --- reset_results: full reset ---
    full_reset_source = _make_result(
        run_id=run_id,
        task_id="task-1",
        status=ResultStatus.FAILED_INFERENCE,
        children=(
            (
                BenchmarkResultTerm(
                    term_kind=ResultTermKind.EXACT_MISSING, term_order=0, term_text="missing"
                ),
            ),
            (),
        ),
    )
    store.create_results((full_reset_source,))
    full_reset_id = store.list_results(run_id)[0].result_id

    reset_count = store.reset_results((full_reset_id,))

    assert reset_count == 1
    reset_result = next(r for r in store.list_results(run_id) if r.result_id == full_reset_id)
    assert reset_result.status == ResultStatus.PENDING
    assert reset_result.verdict is None
    assert reset_result.terms == ()

    # --- reset_results_for_retry: judge-only preserving reset ---
    judge_timeout_source = _make_result(
        run_id=run_id,
        task_id="task-2",
        status=ResultStatus.FAILED_JUDGE_TIMEOUT,
        sanitized_response="the preserved response",
        children=(
            (
                BenchmarkResultTerm(
                    term_kind=ResultTermKind.SEMANTIC, term_order=0, term_text="preserved-term"
                ),
            ),
            (),
        ),
    )
    store.create_results((judge_timeout_source,))
    judge_timeout_id = next(
        r.result_id for r in store.list_results(run_id) if r.task_id == "task-2"
    )
    store.update_result(
        judge_timeout_id,
        ResultPatch(
            total_time_ms=_PRESERVED_TOTAL_TIME_MS,
            keyword_verdict=Verdict.PASS,
        ),
    )

    retry_count = store.reset_results_for_retry((judge_timeout_id,))

    assert retry_count == 1
    judge_retried = next(r for r in store.list_results(run_id) if r.result_id == judge_timeout_id)
    assert judge_retried.status == ResultStatus.AWAITING_JUDGE_CHECK
    assert judge_retried.judge_verdict is None
    assert judge_retried.verdict is None
    # Preserved: response, timing, keyword outcome, and term child rows.
    assert judge_retried.sanitized_response == "the preserved response"
    assert judge_retried.total_time_ms == _PRESERVED_TOTAL_TIME_MS
    assert judge_retried.keyword_verdict == Verdict.PASS
    assert len(judge_retried.terms) == 1

    # --- reset_results_for_retry: every other retryable status fully resets ---
    # task-1's prior result was already reset to pending above; this second
    # result row (also under task-1) exercises the full-reset branch independently.
    inference_failure_source = _make_result(
        run_id=run_id, task_id="task-1", status=ResultStatus.FAILED_TIMEOUT
    )
    store.create_results((inference_failure_source,))
    non_judge_failure_id = next(
        r.result_id for r in store.list_results(run_id) if r.status == ResultStatus.FAILED_TIMEOUT
    )

    other_retry_count = store.reset_results_for_retry((non_judge_failure_id,))

    assert other_retry_count == 1
    fully_reset = next(r for r in store.list_results(run_id) if r.result_id == non_judge_failure_id)
    assert fully_reset.status == ResultStatus.PENDING
    assert fully_reset.sanitized_response is None
